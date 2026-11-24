import hashlib
import json
import secrets
from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, logout
from django.core.exceptions import PermissionDenied
from django.db import connection, transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiTypes, OpenApiParameter
from invoices.models import Customer, Invoice, Term, Payment, OpeningBalance, UserSystem
from . import models as m, serializers as s, services
from .api_errors import Conflict
from .permissions import ModelPermissions
from .renderers import InvoicePDFRenderer, DecimalJSONRenderer


class HealthView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return Response({"status": "ok", "version": "1.0.0", "api": "v1"})


class VersionView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(
            {
                "version": "1.0.0",
                "api": "v1",
                "django": __import__("django").get_version(),
            }
        )


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    @extend_schema(request=s.LoginSerializer, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        serializer = s.LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(request, **serializer.validated_data)
        if not user:
            return Response({"detail": "Invalid username or password."}, status=401)
        raw = secrets.token_urlsafe(48)
        expires = timezone.now() + timedelta(hours=settings.API_TOKEN_HOURS)
        m.AccessToken.objects.filter(user=user, expires_at__lte=timezone.now()).delete()
        m.AccessToken.objects.create(
            user=user,
            digest=hashlib.sha256(raw.encode()).hexdigest(),
            expires_at=expires,
        )
        return Response({"token": raw, "expires_at": expires, "user": user_data(user)})


def user_data(user):
    return {
        "id": user.pk,
        "username": user.username,
        "name": user.get_full_name(),
        "is_superuser": user.is_superuser,
        "permissions": sorted(user.get_all_permissions()),
    }


class MeView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        return Response(user_data(request.user))


class LogoutView(APIView):
    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    def post(self, request):
        if isinstance(request.auth, m.AccessToken):
            request.auth.delete()
        else:
            logout(request)
        return Response({"detail": "Signed out."})


class BootstrapView(APIView):
    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        data = {
            "company": settings.SITE_NAME,
            "currency": "NPR",
            "date": timezone.localdate(),
            "units": ["piece", "kg", "m3", "m", "litre"],
            "default_vat_rate": "13.00",
            "user": user_data(request.user),
        }
        if request.user.has_perm("invoices.view_term"):
            data["fiscal_years"] = s.TermSerializer(
                Term.objects.order_by("-start_date"), many=True
            ).data
            profile = UserSystem.objects.filter(user=request.user).first()
            data["default_fiscal_year"] = profile.billing_term_id if profile else None
        data["units"].append("mm")
        return Response(data)


class BaseViewSet(viewsets.ModelViewSet):
    permission_classes = [ModelPermissions]
    http_method_names = ["get", "post", "patch", "put", "head", "options"]
    filter_fields = {}

    def get_queryset(self):
        queryset = super().get_queryset().order_by("pk")
        if getattr(self, "swagger_fake_view", False):
            return queryset.none()
        for param, field in self.filter_fields.items():
            value = self.request.query_params.get(param)
            if value is not None:
                if field.endswith("_id"):
                    value = serializers.IntegerField(min_value=1).run_validation(value)
                queryset = queryset.filter(**{field: value})
        if any(f.name == "date" for f in queryset.model._meta.fields):
            for param, lookup in [("from", "date__gte"), ("to", "date__lte")]:
                if param in self.request.query_params:
                    queryset = queryset.filter(
                        **{
                            lookup: serializers.DateField().run_validation(
                                self.request.query_params[param]
                            )
                        }
                    )
        return queryset

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        key = request.headers.get("Idempotency-Key")
        if not key:
            return super().create(request, *args, **kwargs)
        if len(key) > 100:
            raise ValidationError("Idempotency keys must be at most 100 characters.")
        m.PostingLock.objects.get_or_create(pk=1)
        m.PostingLock.objects.select_for_update().get(pk=1)
        fingerprint = hashlib.sha256(
            json.dumps(
                {"path": request.path, "data": request.data},
                sort_keys=True,
                default=str,
            ).encode()
        ).hexdigest()
        prior = m.IdempotencyRecord.objects.filter(user=request.user, key=key).first()
        if prior:
            if prior.request_hash != fingerprint:
                raise Conflict("This idempotency key was used for another request.")
            return Response(prior.response, status=201)
        response = super().create(request, *args, **kwargs)
        body = json.loads(JSONRenderer().render(response.data))
        m.IdempotencyRecord.objects.create(
            user=request.user, key=key, request_hash=fingerprint, response=body
        )
        return response

    def perform_create(self, serializer):
        obj = serializer.save()
        services.audit(
            self.request.user,
            obj,
            "create",
            json.loads(JSONRenderer().render(serializer.data)),
        )

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        self.locked_object = get_object_or_404(
            self.get_queryset().select_for_update(of=("self",)), pk=kwargs["pk"]
        )
        self.check_object_permissions(request, self.locked_object)
        return super().update(request, *args, **kwargs)

    def get_object(self):
        return getattr(self, "locked_object", None) or super().get_object()

    def perform_update(self, serializer):
        obj = serializer.save()
        services.audit(
            self.request.user,
            obj,
            "update",
            json.loads(JSONRenderer().render(serializer.data)),
        )


class MasterViewSet(BaseViewSet):
    def perform_update(self, serializer):
        obj = serializer.instance
        if (
            isinstance(obj, m.PaymentAccount)
            and obj.movements.exists()
            and "kind" in serializer.validated_data
        ):
            if obj.kind != serializer.validated_data["kind"]:
                raise ValidationError("Account type is locked after movements exist.")
        if (
            isinstance(obj, m.PaymentAccount)
            and obj.movements.exists()
            and "opening_balance" in serializer.validated_data
        ):
            if obj.opening_balance != serializer.validated_data["opening_balance"]:
                raise ValidationError(
                    "Opening balance is locked after account movements exist."
                )
        if (
            isinstance(obj, m.Supplier)
            and (
                m.PurchaseBill.objects.filter(supplier=obj, status="posted").exists()
                or m.SupplierPayment.objects.filter(
                    supplier=obj, status="posted"
                ).exists()
            )
            and "opening_balance" in serializer.validated_data
        ):
            if obj.opening_balance != serializer.validated_data["opening_balance"]:
                raise ValidationError(
                    "Supplier opening balance is locked after posting transactions."
                )
        if isinstance(obj, m.StockItem) and (
            m.StockMovement.objects.filter(item=obj).exists()
            or m.PurchaseLine.objects.filter(item=obj).exists()
            or m.SalesLineStock.objects.filter(item=obj).exists()
        ):
            for field in ("unit", "density", "kind"):
                if (
                    field in serializer.validated_data
                    and getattr(obj, field) != serializer.validated_data[field]
                ):
                    raise ValidationError(
                        "Item unit, density and kind are locked after use."
                    )
        if isinstance(obj, Term) and obj.invoice_set.exists():
            for field in ("start_date", "end_date"):
                if (
                    field in serializer.validated_data
                    and getattr(obj, field) != serializer.validated_data[field]
                ):
                    raise ValidationError(
                        "Fiscal-year dates are locked after invoices exist."
                    )
        super().perform_update(serializer)


class DocumentViewSet(BaseViewSet):
    filter_fields = {"status": "status"}

    def perform_update(self, serializer):
        services.check_revision(serializer.instance, self.request.data.get("revision"))
        super().perform_update(serializer)

    @transaction.atomic
    def run_action(self, request, operation):
        key = request.headers.get("Idempotency-Key", "")
        if not key or len(key) > 100:
            raise ValidationError(
                {
                    "Idempotency-Key": "Supply a unique retry key of at most 100 characters."
                }
            )
        # One company shares stock, cash, allocations and payroll. Take the same
        # lock before every posting/reversal to prevent cross-document races.
        m.PostingLock.objects.get_or_create(pk=1)
        m.PostingLock.objects.select_for_update().get(pk=1)
        get_user_model().objects.select_for_update().get(pk=request.user.pk)
        fingerprint = hashlib.sha256(
            json.dumps(
                {"path": request.path, "data": request.data},
                sort_keys=True,
                default=str,
            ).encode()
        ).hexdigest()
        prior = m.IdempotencyRecord.objects.filter(user=request.user, key=key).first()
        if prior:
            if prior.request_hash != fingerprint:
                raise Conflict("This idempotency key was used for another request.")
            return Response(prior.response)
        obj = get_object_or_404(
            self.get_queryset().select_for_update(of=("self",)), pk=self.kwargs["pk"]
        )
        self.check_object_permissions(request, obj)
        services.check_revision(obj, request.data.get("revision"))
        operation(obj)
        obj.refresh_from_db()
        body = json.loads(JSONRenderer().render(self.get_serializer(obj).data))
        services.audit(
            request.user,
            obj,
            self.action,
            {"request": dict(request.data), "after": body},
        )
        m.IdempotencyRecord.objects.create(
            user=request.user, key=key, request_hash=fingerprint, response=body
        )
        return Response(body)

    @extend_schema(request=s.RevisionSerializer)
    @action(detail=True, methods=["post"])
    def post(self, request, pk=None):
        return self.run_action(request, lambda obj: services.POSTERS[type(obj)](obj))

    @extend_schema(request=s.CancellationSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        reason = serializers.CharField().run_validation(request.data.get("reason"))
        date = serializers.DateField().run_validation(
            request.data.get("date", timezone.localdate())
        )
        return self.run_action(
            request, lambda obj: services.cancel_document(obj, reason, date)
        )


class InvoiceViewSet(DocumentViewSet):
    queryset = (
        Invoice.objects.all()
        .select_related("issued_for", "fiscal_year")
        .prefetch_related("items_set", "density_groups", "allocations")
    )
    serializer_class = s.InvoiceSerializer
    filter_fields = {
        "status": "status",
        "customer": "issued_for_id",
        "fiscal_year": "fiscal_year_id",
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        if "is_vat" in self.request.query_params:
            queryset = queryset.filter(
                is_vat=serializers.BooleanField().run_validation(
                    self.request.query_params["is_vat"]
                )
            )
        return queryset

    @extend_schema(request=s.RevisionSerializer)
    @action(detail=True, methods=["post"])
    def group(self, request, pk=None):
        return self.run_action(request, services.group_invoice)

    @extend_schema(
        request=s.RateSerializer,
        parameters=[OpenApiParameter("group_id", int, OpenApiParameter.PATH)],
    )
    @action(detail=True, methods=["patch"], url_path="groups/(?P<group_id>[^/.]+)")
    @transaction.atomic
    def groups(self, request, pk=None, group_id=None):
        invoice = get_object_or_404(
            self.get_queryset().select_for_update(of=("self",)), pk=pk
        )
        if invoice.source != "api" or invoice.status != "grouped":
            raise ValidationError("Rates can only be entered on grouped API drafts.")
        services.check_revision(invoice, request.data.get("revision"))
        if set(request.data) - {"rate", "revision"}:
            raise ValidationError("Only rate and revision are accepted.")
        group = get_object_or_404(invoice.density_groups.all(), pk=group_id)
        group.rate = serializers.DecimalField(
            max_digits=18, decimal_places=4, min_value=Decimal("0")
        ).run_validation(request.data.get("rate"))
        group.save()
        services.touch(invoice)
        services.audit(request.user, invoice, "set_rate", {"group": group.pk})
        invoice.refresh_from_db()
        return Response(self.get_serializer(invoice).data)

    @extend_schema(request=None, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"])
    def preview(self, request, pk=None):
        return Response(services.invoice_totals(self.get_object()))

    @extend_schema(request=s.RevisionSerializer)
    @action(detail=True, methods=["post"])
    def post(self, request, pk=None):
        return self.run_action(request, services.post_invoice)

    @extend_schema(request=s.CancellationSerializer)
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return self.run_action(
            request,
            lambda obj: services.cancel_invoice(
                obj,
                serializers.CharField().run_validation(request.data.get("reason")),
                serializers.DateField().run_validation(
                    request.data.get("date", timezone.localdate())
                ),
            ),
        )

    @extend_schema(responses=OpenApiTypes.BINARY)
    @action(
        detail=True,
        methods=["get"],
        renderer_classes=[InvoicePDFRenderer, DecimalJSONRenderer],
    )
    def pdf(self, request, pk=None):
        from reportlab.pdfgen import canvas

        invoice = self.get_object()
        if invoice.status != "posted":
            raise ValidationError("Only posted invoices can be exported.")
        output = BytesIO()
        pdf = canvas.Canvas(output, pagesize=(595, 842))

        def heading():
            pdf.setFont("Helvetica-Bold", 18)
            pdf.drawString(40, 795, settings.SITE_NAME)
            pdf.setFont("Helvetica", 11)
            pdf.drawString(
                40,
                770,
                f"{invoice.number or invoice.vat_bill_no or invoice.pk} | {invoice.date}",
            )
            pdf.drawString(
                40,
                750,
                f"Customer: {invoice.issued_for.name if invoice.issued_for else ''}",
            )

        heading()
        y = 710
        pdf.setFont("Helvetica", 10)
        rows = invoice.density_groups.all()
        for group in rows:
            if y < 100:
                pdf.showPage()
                heading()
                pdf.setFont("Helvetica", 10)
                y = 710
            pdf.drawString(
                40,
                y,
                f"Density {group.density} | {group.quantity} {group.unit} x {group.rate} = NPR {group.amount}",
            )
            y -= 22
        if not rows:
            for line in invoice.items_set.all():
                if y < 100:
                    pdf.showPage()
                    heading()
                    pdf.setFont("Helvetica", 10)
                    y = 710
                pdf.drawString(
                    40,
                    y,
                    f"{(line.description or '')[:50]} | {line.qty} x {line.calculated_rate} = NPR {line.price}",
                )
                y -= 22
        if y < 150:
            pdf.showPage()
            heading()
            y = 710
        pdf.drawString(
            40,
            y - 20,
            f"Discount: NPR {invoice.discount or 0} | Tax: NPR {invoice.tax or 0}",
        )
        pdf.setFont("Helvetica-Bold", 12)
        pdf.drawString(
            40,
            y - 45,
            f"Total: NPR {invoice.total} | Outstanding: NPR {services.invoice_outstanding(invoice)}",
        )
        pdf.save()
        response = HttpResponse(output.getvalue(), content_type="application/pdf")
        response["Content-Disposition"] = (
            f'attachment; filename="invoice-{invoice.pk}.pdf"'
        )
        return response


class CustomerViewSet(MasterViewSet):
    queryset = Customer.objects.all()
    serializer_class = s.CustomerSerializer

    def get_queryset(self):
        queryset = super().get_queryset().order_by("name", "pk")
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(address__icontains=search)
                | Q(phone__icontains=search)
                | Q(pan__icontains=search)
            )
        return queryset

    @action(detail=True, methods=["get"])
    def statement(self, request, pk=None):
        if not request.user.has_perms(
            [
                "invoices.view_invoice",
                "invoices.view_payment",
                "invoices.view_openingbalance",
            ]
        ):
            raise PermissionDenied
        customer = self.get_object()
        year_id = request.query_params.get("fiscal_year")
        invoices = customer.invoice_set.filter(status="posted")
        payments = customer.payment_set.all()
        opening = (
            customer.openingbalance_set.select_related("term")
            .order_by("-term__start_date")
            .first()
        )
        if year_id:
            year = get_object_or_404(
                Term, pk=serializers.IntegerField().run_validation(year_id)
            )
            opening = customer.openingbalance_set.filter(term=year).first()
            invoices = invoices.filter(date__range=(year.start_date, year.end_date))
            payments = payments.filter(date__range=(year.start_date, year.end_date))
        elif opening:
            invoices = invoices.filter(date__gte=opening.term.start_date)
            payments = payments.filter(date__gte=opening.term.start_date)
        opening_amount = opening.amount if opening else Decimal("0")
        return Response(
            {
                "customer": customer.pk,
                "opening_balance": opening_amount,
                "invoiced": services.total(invoices, "to_pay"),
                "received": services.total(payments, "amount"),
                "balance": opening_amount
                + services.total(invoices, "to_pay")
                - services.total(payments, "amount"),
                "invoice_count": invoices.count(),
                "payment_count": payments.count(),
                "invoices": s.InvoiceSerializer(
                    invoices.order_by("-date", "-pk")[:20], many=True
                ).data,
                "payments": list(
                    payments.order_by("-date", "-pk").values(
                        "id", "amount", "date", "payment_mode"
                    )[:20]
                ),
            }
        )


class ReceiptViewSet(DocumentViewSet):
    queryset = m.CustomerReceipt.objects.all()
    serializer_class = s.ReceiptSerializer
    filter_fields = {"status": "status", "customer": "customer_id"}

    @extend_schema(request=s.ReceiptPostingSerializer)
    @action(detail=True, methods=["post"])
    def post(self, request, pk=None):
        allocations = s.AllocationInputSerializer(
            data=request.data.get("allocations", []), many=True
        )
        allocations.is_valid(raise_exception=True)

        def operation(receipt):
            services.post_receipt(receipt)
            if allocations.validated_data:
                services.allocate_receipt(receipt, allocations.validated_data)

        return self.run_action(request, operation)

    @extend_schema(request=s.AllocationBatchSerializer)
    @action(detail=True, methods=["post"])
    def allocate(self, request, pk=None):
        serializer = s.AllocationInputSerializer(
            data=request.data.get("allocations", []), many=True
        )
        serializer.is_valid(raise_exception=True)
        return self.run_action(
            request,
            lambda obj: services.allocate_receipt(obj, serializer.validated_data),
        )

    @extend_schema(request=s.ChequeActionSerializer)
    @action(detail=True, methods=["post"])
    def clear(self, request, pk=None):
        return self.run_action(
            request,
            lambda obj: services.cheque_action(
                obj,
                "clear",
                serializers.DateField().run_validation(request.data.get("date")),
            ),
        )

    @extend_schema(request=s.ChequeActionSerializer)
    @action(detail=True, methods=["post"])
    def bounce(self, request, pk=None):
        return self.run_action(
            request,
            lambda obj: services.cheque_action(
                obj,
                "bounce",
                serializers.DateField().run_validation(request.data.get("date")),
            ),
        )

    @extend_schema(request=s.AllocationReversalSerializer)
    @action(detail=True, methods=["post"], url_path="reverse-allocations")
    def reverse_allocations(self, request, pk=None):
        ids = serializers.ListField(
            child=serializers.IntegerField(min_value=1), allow_empty=False
        ).run_validation(request.data.get("allocation_ids"))
        reason = serializers.CharField().run_validation(request.data.get("reason"))
        return self.run_action(
            request, lambda obj: services.reverse_allocations(obj, ids, reason)
        )


class ChequeViewSet(ReceiptViewSet):
    queryset = m.CustomerReceipt.objects.filter(method="cheque")
    http_method_names = ["get", "post", "head", "options"]

    def create(self, *args, **kwargs):
        raise ValidationError("Create cheques through customer-payments/.")


class SupplierViewSet(MasterViewSet):
    queryset = m.Supplier.objects.all()
    serializer_class = s.SupplierSerializer

    @action(detail=True, methods=["get"])
    def statement(self, request, pk=None):
        if not request.user.has_perms(
            ["operations.view_purchasebill", "operations.view_supplierpayment"]
        ):
            raise PermissionDenied
        obj = self.get_object()
        purchases = m.PurchaseBill.objects.filter(supplier=obj, status="posted")
        payments = (
            m.SupplierPayment.objects.filter(supplier=obj, status="posted")
            .exclude(cheque_status="bounced")
            .exclude(method="cheque", cheque_status="pending")
        )
        return Response(
            {
                "supplier": obj.pk,
                "opening_balance": obj.opening_balance,
                "purchased": services.total(purchases, "total"),
                "paid": services.total(payments, "amount"),
                "balance": obj.opening_balance
                + services.total(purchases, "total")
                - services.total(payments, "amount"),
                "purchases": s.PurchaseSerializer(purchases, many=True).data,
                "payments": s.SupplierPaymentSerializer(payments, many=True).data,
            }
        )


class SupplierPaymentViewSet(DocumentViewSet):
    queryset = m.SupplierPayment.objects.all()
    serializer_class = s.SupplierPaymentSerializer
    filter_fields = {
        "status": "status",
        "supplier": "supplier_id",
        "purchase": "purchase_id",
    }
    clear = ReceiptViewSet.clear
    bounce = ReceiptViewSet.bounce


class JobViewSet(DocumentViewSet):
    queryset = m.JobOrder.objects.all()
    serializer_class = s.JobSerializer

    @extend_schema(request=s.RevisionSerializer)
    @action(detail=True, methods=["post"])
    def complete(self, request, pk=None):
        return self.run_action(request, services.complete_job)


class PayrollViewSet(DocumentViewSet):
    queryset = m.PayrollRun.objects.all()
    serializer_class = s.PayrollSerializer

    @extend_schema(request=s.RevisionSerializer)
    @action(detail=True, methods=["post"])
    def calculate(self, request, pk=None):
        return self.run_action(request, services.calculate_payroll)

    @extend_schema(request=s.RevisionSerializer)
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        return self.run_action(request, services.approve_payroll)

    @extend_schema(request=s.RevisionSerializer)
    @action(detail=True, methods=["post"])
    def post(self, request, pk=None):
        raise ValidationError("Use approve/ to finalize payroll.")


class LabourViewSet(BaseViewSet):
    queryset = m.LabourEntry.objects.all()
    serializer_class = s.LabourSerializer
    filter_fields = {"worker": "worker_id", "worksheet": "worksheet_id"}

    def perform_create(self, serializer):
        worksheet = m.Worksheet.objects.select_for_update().get(
            pk=serializer.validated_data["worksheet"].pk
        )
        services.draft(worksheet)
        super().perform_create(serializer)
        services.touch(worksheet)

    def perform_update(self, serializer):
        if (
            "worksheet" in serializer.validated_data
            and serializer.validated_data["worksheet"].pk
            != serializer.instance.worksheet_id
        ):
            raise ValidationError("Labour entries cannot be moved between worksheets.")
        worksheet = m.Worksheet.objects.select_for_update().get(
            pk=serializer.instance.worksheet_id
        )
        services.draft(worksheet)
        super().perform_update(serializer)
        services.touch(worksheet)


class ReadOnlyViewSet(viewsets.ReadOnlyModelViewSet):
    permission_classes = [ModelPermissions]

    def get_queryset(self):
        queryset = super().get_queryset().order_by("pk")
        for key in ("item", "location", "account", "customer", "term"):
            if key in self.request.query_params and any(
                f.name == key for f in queryset.model._meta.fields
            ):
                queryset = queryset.filter(
                    **{
                        key + "_id": serializers.IntegerField().run_validation(
                            self.request.query_params[key]
                        )
                    }
                )
        return queryset


class AccountViewSet(MasterViewSet):
    queryset = m.PaymentAccount.objects.all()
    serializer_class = s.PaymentAccountSerializer

    @action(detail=True, methods=["get"])
    def balance(self, request, pk=None):
        if not request.user.has_perm("operations.view_accountmovement"):
            raise PermissionDenied
        obj = self.get_object()
        return Response({"account": obj.pk, "balance": services.account_balance(obj)})


class BankAccountViewSet(AccountViewSet):
    queryset = m.PaymentAccount.objects.filter(kind="bank")

    def perform_create(self, serializer):
        if serializer.validated_data.get("kind") != "bank":
            raise ValidationError("Use payment-accounts/ for cash or mobile accounts.")
        super().perform_create(serializer)


# Domain resources share consistent transactions, revisions, audit and permissions.
def resource(name, model, serializer, base=DocumentViewSet, filters=None):
    attrs = {
        "queryset": model.objects.all(),
        "serializer_class": serializer,
        "__module__": __name__,
    }
    if filters:
        attrs["filter_fields"] = filters
    return type(name, (base,), attrs)


TermViewSet = resource("TermViewSet", Term, s.TermSerializer, MasterViewSet)
StockItemViewSet = resource(
    "StockItemViewSet", m.StockItem, s.StockItemSerializer, MasterViewSet
)
LocationViewSet = resource(
    "LocationViewSet", m.Location, s.LocationSerializer, MasterViewSet
)
WorkerViewSet = resource("WorkerViewSet", m.Worker, s.WorkerSerializer, MasterViewSet)
CategoryViewSet = resource(
    "CategoryViewSet", m.ExpenseCategory, s.CategorySerializer, MasterViewSet
)
PurchaseViewSet = resource(
    "PurchaseViewSet",
    m.PurchaseBill,
    s.PurchaseSerializer,
    filters={"status": "status", "supplier": "supplier_id"},
)
GoodsReceiptViewSet = resource(
    "GoodsReceiptViewSet",
    m.GoodsReceipt,
    s.GoodsReceiptSerializer,
    filters={"status": "status", "purchase": "purchase_id"},
)
TransferViewSet = resource("TransferViewSet", m.AccountTransfer, s.TransferSerializer)
AdjustmentViewSet = resource(
    "AdjustmentViewSet", m.StockAdjustment, s.AdjustmentSerializer
)
IssueViewSet = resource(
    "IssueViewSet",
    m.MaterialIssue,
    s.IssueSerializer,
    filters={"status": "status", "job": "job_id"},
)
ProductionViewSet = resource(
    "ProductionViewSet",
    m.ProductionReport,
    s.ProductionSerializer,
    filters={"status": "status", "job": "job_id"},
)
ExpenseViewSet = resource(
    "ExpenseViewSet",
    m.Expense,
    s.ExpenseSerializer,
    filters={"status": "status", "job": "job_id", "category": "category_id"},
)
WorksheetViewSet = resource(
    "WorksheetViewSet",
    m.Worksheet,
    s.WorksheetSerializer,
    filters={"status": "status", "job": "job_id"},
)
AdvanceViewSet = resource(
    "AdvanceViewSet",
    m.SalaryAdvance,
    s.AdvanceSerializer,
    filters={"status": "status", "worker": "worker_id"},
)
SalaryPaymentViewSet = resource(
    "SalaryPaymentViewSet", m.SalaryPayment, s.SalaryPaymentSerializer
)
BalanceViewSet = resource(
    "BalanceViewSet", m.StockBalance, s.BalanceSerializer, ReadOnlyViewSet
)
MovementViewSet = resource(
    "MovementViewSet", m.StockMovement, s.MovementSerializer, ReadOnlyViewSet
)
AccountMovementViewSet = resource(
    "AccountMovementViewSet",
    m.AccountMovement,
    s.AccountMovementSerializer,
    ReadOnlyViewSet,
)
AuditViewSet = resource(
    "AuditViewSet", m.AuditEvent, s.AuditSerializer, ReadOnlyViewSet
)


class ReportsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request, report):
        sources = {
            "sales": (Invoice, s.InvoiceSerializer, "total"),
            "purchases": (m.PurchaseBill, s.PurchaseSerializer, "total"),
            "production": (
                m.ProductionReport,
                s.ProductionSerializer,
                "produced_quantity",
            ),
            "expenses": (m.Expense, s.ExpenseSerializer, "amount"),
            "payroll": (m.PayrollRun, s.PayrollSerializer, "total"),
        }
        if report in sources:
            model, serializer, field = sources[report]
            self.require(request, model)
            rows = model.objects.filter(status="posted").order_by("-date", "-pk")
            for param, lookup in [("from", "date__gte"), ("to", "date__lte")]:
                if param in request.query_params:
                    rows = rows.filter(
                        **{
                            lookup: serializers.DateField().run_validation(
                                request.query_params[param]
                            )
                        }
                    )
            from rest_framework.pagination import PageNumberPagination

            pagination = PageNumberPagination()
            page = pagination.paginate_queryset(rows, request)
            return Response(
                {
                    "count": rows.count(),
                    "next": pagination.get_next_link(),
                    "previous": pagination.get_previous_link(),
                    "total": services.total(rows, field),
                    "results": serializer(page, many=True).data,
                }
            )
        if report == "stock":
            self.require(request, m.StockBalance)
            return Response(
                {
                    "results": s.BalanceSerializer(
                        m.StockBalance.objects.all(), many=True
                    ).data
                }
            )
        if report == "cash-bank":
            self.require(request, m.PaymentAccount)
            self.require(request, m.AccountMovement)
            return Response(
                {
                    "results": [
                        {
                            "id": a.pk,
                            "name": a.name,
                            "kind": a.kind,
                            "balance": services.account_balance(a),
                        }
                        for a in m.PaymentAccount.objects.all()
                    ]
                }
            )
        raise ValidationError("Unknown report.")

    def require(self, request, model):
        opts = model._meta
        if not request.user.has_perm(f"{opts.app_label}.view_{opts.model_name}"):
            raise PermissionDenied


class DateConversionView(APIView):
    @extend_schema(
        parameters=[
            OpenApiParameter("date", str, required=True),
            OpenApiParameter("calendar", str, enum=["ad", "bs"], required=True),
        ],
        responses=OpenApiTypes.OBJECT,
    )
    def get(self, request):
        import nepali_datetime

        value = request.query_params.get("date", "")
        calendar = request.query_params.get("calendar", "ad")
        try:
            if calendar == "bs":
                bs = nepali_datetime.date(*map(int, value.split("-")))
                ad = bs.to_datetime_date()
            elif calendar == "ad":
                ad = serializers.DateField().run_validation(value)
                bs = nepali_datetime.date.from_datetime_date(ad)
            else:
                raise ValueError("Unsupported calendar")
        except (ValueError, TypeError, OverflowError) as error:
            raise ValidationError(
                {"date": "Enter a valid supported date; calendar must be ad or bs."}
            ) from error
        return Response({"ad": ad.isoformat(), "bs": bs.isoformat()})


LegacyPaymentViewSet = resource(
    "LegacyPaymentViewSet",
    Payment,
    s.model_serializer(Payment, readonly=tuple(f.name for f in Payment._meta.fields)),
    ReadOnlyViewSet,
)
OpeningBalanceViewSet = resource(
    "OpeningBalanceViewSet",
    OpeningBalance,
    s.model_serializer(
        OpeningBalance, readonly=tuple(f.name for f in OpeningBalance._meta.fields)
    ),
    ReadOnlyViewSet,
)
