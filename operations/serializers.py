from decimal import Decimal
from django.db import transaction
from rest_framework import serializers
from invoices.models import Customer, Term, Invoice, Items
from . import models as m
from .services import draft


class StrictSerializer(serializers.ModelSerializer):
    def to_internal_value(self, data):
        unknown = set(data) - set(self.fields)
        forbidden = {
            key
            for key in data
            if key in self.fields and self.fields[key].read_only and key != "revision"
        }
        if unknown or forbidden:
            raise serializers.ValidationError(
                {key: "Unknown or server-managed field." for key in unknown | forbidden}
            )
        return super().to_internal_value(data)


def model_serializer(model, exclude=(), readonly=()):
    class Meta:
        fields = "__all__"
        read_only_fields = readonly

    Meta.model = model
    if exclude:
        del Meta.fields
        Meta.exclude = exclude
    return type(
        f"{model.__name__}Serializer",
        (StrictSerializer,),
        {"Meta": Meta, "__module__": __name__},
    )


class CustomerSerializer(StrictSerializer):
    balance = serializers.SerializerMethodField()

    class Meta:
        model = Customer
        fields = "__all__"
        extra_kwargs = {
            "name": {"required": True, "allow_blank": False, "allow_null": False}
        }

    def get_balance(self, obj) -> str | None:
        request = self.context.get("request")
        if request and request.user.has_perms(
            [
                "invoices.view_invoice",
                "invoices.view_payment",
                "invoices.view_openingbalance",
            ]
        ):
            return str(obj.arthik_remaining_pay())
        return None


class TermSerializer(StrictSerializer):
    class Meta:
        model = Term
        fields = "__all__"

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end <= start:
            raise serializers.ValidationError(
                {"end_date": "End date must follow start date."}
            )
        return attrs


SupplierSerializer = model_serializer(m.Supplier)
PaymentAccountSerializer = model_serializer(m.PaymentAccount)
StockItemSerializer = model_serializer(m.StockItem)
LocationSerializer = model_serializer(m.Location)
WorkerSerializer = model_serializer(m.Worker)
CategorySerializer = model_serializer(m.ExpenseCategory)
BalanceSerializer = model_serializer(
    m.StockBalance, readonly=("item", "location", "quantity")
)
MovementSerializer = model_serializer(
    m.StockMovement,
    readonly=("item", "location", "quantity", "date", "kind", "reference"),
)
AccountMovementSerializer = model_serializer(
    m.AccountMovement,
    readonly=("account", "amount", "date", "reference", "description"),
)
AuditSerializer = model_serializer(
    m.AuditEvent,
    readonly=("actor", "action", "resource", "resource_id", "details", "created_at"),
)
GroupSerializer = model_serializer(
    m.DensityGroup,
    readonly=("invoice", "density", "unit", "taxable", "quantity", "amount"),
)
AllocationSerializer = model_serializer(
    m.PaymentAllocation,
    readonly=("receipt", "invoice", "amount", "reversed", "reversal_reason"),
)
PayrollLineSerializer = model_serializer(
    m.PayrollLine, readonly=tuple(f.name for f in m.PayrollLine._meta.fields)
)


class SalesLineSerializer(StrictSerializer):
    length = serializers.DecimalField(
        max_digits=12, decimal_places=4, min_value=0, default=0
    )
    breadth = serializers.DecimalField(
        max_digits=12, decimal_places=4, min_value=0, default=0
    )
    height = serializers.DecimalField(
        max_digits=12, decimal_places=4, min_value=0, default=0
    )
    mm = serializers.DecimalField(
        max_digits=12, decimal_places=4, min_value=0, default=0
    )
    billing_quantity = serializers.SerializerMethodField()
    stock_item_id = serializers.SerializerMethodField()
    location_id = serializers.SerializerMethodField()
    stock_item = serializers.PrimaryKeyRelatedField(
        queryset=m.StockItem.objects.filter(active=True),
        required=False,
        write_only=True,
    )
    location = serializers.PrimaryKeyRelatedField(
        queryset=m.Location.objects.all(), required=False, write_only=True
    )

    class Meta:
        model = Items
        fields = [
            "id",
            "density",
            "length",
            "breadth",
            "height",
            "mm",
            "description",
            "qty",
            "unit",
            "taxable",
            "tax_include",
            "stock_item",
            "location",
            "rate",
            "calculated_rate",
            "price",
            "billing_quantity",
            "stock_item_id",
            "location_id",
        ]
        read_only_fields = ["rate", "calculated_rate", "price"]
        extra_kwargs = {
            "qty": {
                "required": True,
                "allow_null": False,
                "min_value": Decimal(".0001"),
            },
            "density": {"required": True, "allow_null": False, "allow_blank": False},
            "taxable": {"default": True},
            "tax_include": {"default": False},
        }

    def get_billing_quantity(self, obj) -> str:
        from .services import line_billing_quantity

        # Historical lines remain readable even when original dimensions are absent.
        if obj.invoice.source != "api":
            return str(obj.qty or 0)
        return str(line_billing_quantity(obj))

    def get_stock_item_id(self, obj) -> int | None:
        return obj.stock_link.item_id if hasattr(obj, "stock_link") else None

    def get_location_id(self, obj) -> int | None:
        return obj.stock_link.location_id if hasattr(obj, "stock_link") else None

    def validate(self, attrs):
        if attrs.get("tax_include"):
            raise serializers.ValidationError(
                "Use tax-exclusive group rates; included-tax conversion is not enabled."
            )
        item = attrs.get("stock_item")
        location = attrs.get("location")
        if bool(item) != bool(location):
            raise serializers.ValidationError(
                "Provide both stock_item and location, or neither for a non-stock line."
            )
        if item and (
            item.unit
            != ("piece" if attrs.get("unit") == "mm" else attrs.get("unit", "piece"))
            or item.density != attrs.get("density")
        ):
            raise serializers.ValidationError(
                "Line unit and density must match the stock item."
            )
        if attrs.get("unit") == "mm":
            from .services import line_billing_quantity
            from types import SimpleNamespace

            line_billing_quantity(
                SimpleNamespace(
                    **{"length": 0, "breadth": 0, "height": 0, "mm": 0, **attrs}
                )
            )
        return attrs


class InvoiceSerializer(StrictSerializer):
    customer_name = serializers.CharField(
        source="issued_for.name", read_only=True, allow_null=True
    )
    lines = SalesLineSerializer(many=True, source="items_set", required=False)
    groups = GroupSerializer(many=True, source="density_groups", read_only=True)
    outstanding = serializers.SerializerMethodField()
    pending_payment = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = [
            "id",
            "issued_for",
            "customer_name",
            "issued_by",
            "date",
            "notes",
            "is_vat",
            "vat_rate",
            "discount",
            "fiscal_year",
            "status",
            "source",
            "revision",
            "number",
            "vat_bill_no",
            "total",
            "tax",
            "paid_amount",
            "to_pay",
            "cancellation_reason",
            "credit_bank_name",
            "lines",
            "groups",
            "outstanding",
            "pending_payment",
        ]
        read_only_fields = [
            "issued_by",
            "status",
            "source",
            "revision",
            "number",
            "vat_bill_no",
            "total",
            "tax",
            "paid_amount",
            "to_pay",
            "cancellation_reason",
        ]
        extra_kwargs = {
            "issued_for": {"required": True, "allow_null": False},
            "date": {"required": True, "allow_null": False},
            "fiscal_year": {"required": True, "allow_null": False},
            "discount": {"min_value": Decimal("0"), "allow_null": False},
            "vat_rate": {"min_value": Decimal("0"), "max_value": Decimal("100")},
        }

    def get_outstanding(self, obj) -> str:
        from .services import invoice_outstanding

        return str(invoice_outstanding(obj))

    def get_pending_payment(self, obj) -> str:
        from .services import total

        return str(
            total(
                obj.allocations.filter(
                    reversed=False,
                    receipt__status="posted",
                    receipt__method="cheque",
                    receipt__cheque_status="pending",
                ),
                "amount",
            )
        )

    def validate(self, attrs):
        year = attrs.get("fiscal_year", getattr(self.instance, "fiscal_year", None))
        date = attrs.get("date", getattr(self.instance, "date", None))
        if year and date and not year.start_date <= date <= year.end_date:
            raise serializers.ValidationError(
                {"date": "Date is outside the selected fiscal year."}
            )
        return attrs

    def save_lines(self, invoice, lines):
        invoice.items_set.all().delete()
        invoice.density_groups.all().delete()
        for attrs in lines:
            item = attrs.pop("stock_item", None)
            location = attrs.pop("location", None)
            line = Items.objects.create(invoice=invoice, calculated_rate=0, **attrs)
            if item:
                m.SalesLineStock.objects.create(line=line, item=item, location=location)

    @transaction.atomic
    def create(self, validated_data):
        lines = validated_data.pop("items_set", [])
        invoice = Invoice.objects.create(
            source="api", issued_by=self.context["request"].user, **validated_data
        )
        self.save_lines(invoice, lines)
        return invoice

    @transaction.atomic
    def update(self, instance, validated_data):
        if instance.source != "api" or instance.status not in ("draft", "grouped"):
            raise serializers.ValidationError("Only API drafts can be edited.")
        lines = validated_data.pop("items_set", None)
        if lines is not None:
            self.save_lines(instance, lines)
            instance.status = "draft"
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.revision += 1
        instance.save()
        return instance


DOCUMENT_READONLY = (
    "status",
    "revision",
    "created_by",
    "created_at",
    "cancellation_reason",
)


class DocumentSerializer(StrictSerializer):
    nested = None

    @transaction.atomic
    def create(self, data):
        rows = data.pop(self.nested[0], []) if self.nested else None
        instance = self.Meta.model.objects.create(
            created_by=self.context["request"].user, **data
        )
        if self.nested:
            for row in rows:
                self.nested[1].objects.create(**{self.nested[2]: instance}, **row)
        return instance

    @transaction.atomic
    def update(self, instance, data):
        draft(instance)
        rows = data.pop(self.nested[0], None) if self.nested else None
        for key, value in data.items():
            setattr(instance, key, value)
        instance.revision += 1
        instance.save()
        if rows is not None:
            getattr(instance, self.nested[0]).all().delete()
            for row in rows:
                self.nested[1].objects.create(**{self.nested[2]: instance}, **row)
        return instance

    def validate(self, attrs):
        if self.nested:
            rows = attrs.get(self.nested[0])
            if rows is not None:
                # Duplicate item/material lines are rejected for a clear document contract.
                identities = []
                for row in rows:
                    key = (
                        row.get("purchase_line") or row.get("item") or row.get("worker")
                    )
                    if key is not None:
                        identities.append(key.pk)
                if len(identities) != len(set(identities)):
                    raise serializers.ValidationError(
                        "Duplicate lines are not allowed; combine their quantities."
                    )
        if (
            isinstance(self.instance, m.CustomerReceipt)
            and self.instance.allocations.exists()
        ):
            raise serializers.ValidationError("Allocated receipts cannot be edited.")
        if self.Meta.model is m.SalaryPayment:
            line = attrs.get(
                "payroll_line", getattr(self.instance, "payroll_line", None)
            )
            if line and line.run.status != "posted":
                raise serializers.ValidationError(
                    "Approve payroll before creating salary payments."
                )
        return attrs


def document_serializer(model, nested=None, readonly=()):
    attrs = {"__module__": __name__}

    class Meta:
        fields = "__all__"
        read_only_fields = DOCUMENT_READONLY + readonly

    Meta.model = model
    attrs["Meta"] = Meta
    if nested:
        related, child, parent, child_readonly = nested
        child_serializer = model_serializer(
            child, exclude=(parent,), readonly=child_readonly
        )
        child_serializer.__name__ = f"{model.__name__}{child.__name__}Serializer"
        attrs[related] = child_serializer(many=True, required=False)
        attrs["nested"] = (related, child, parent)
    return type(f"{model.__name__}Serializer", (DocumentSerializer,), attrs)


ReceiptSerializer = document_serializer(
    m.CustomerReceipt, readonly=("legacy_payment", "cheque_status", "clearance_date")
)
ReceiptSerializer._declared_fields["allocations"] = AllocationSerializer(
    many=True, read_only=True
)
_ReceiptSerializer = ReceiptSerializer


class ReceiptSerializer(_ReceiptSerializer):
    unallocated_amount = serializers.SerializerMethodField()

    def get_unallocated_amount(self, obj) -> str:
        from .services import total

        if obj.status == "cancelled" or obj.cheque_status == "bounced":
            return "0.00"
        return str(obj.amount - total(obj.allocations.filter(reversed=False), "amount"))


TransferSerializer = document_serializer(m.AccountTransfer)
PurchaseSerializer = document_serializer(
    m.PurchaseBill, ("lines", m.PurchaseLine, "bill", ("amount",)), readonly=("total",)
)
GoodsReceiptSerializer = document_serializer(
    m.GoodsReceipt, ("lines", m.GoodsReceiptLine, "receipt", ())
)
SupplierPaymentSerializer = document_serializer(
    m.SupplierPayment, readonly=("cheque_status", "clearance_date")
)
AdjustmentSerializer = document_serializer(
    m.StockAdjustment, ("lines", m.StockAdjustmentLine, "adjustment", ())
)
JobSerializer = document_serializer(m.JobOrder, readonly=("completed",))
IssueSerializer = document_serializer(
    m.MaterialIssue, ("lines", m.MaterialIssueLine, "issue", ())
)
ProductionSerializer = document_serializer(
    m.ProductionReport, ("consumption", m.ProductionConsumption, "report", ())
)
ExpenseSerializer = document_serializer(m.Expense)
WorksheetSerializer = document_serializer(
    m.Worksheet, ("entries", m.LabourEntry, "worksheet", ())
)
PayrollSerializer = document_serializer(
    m.PayrollRun, ("adjustments", m.PayrollAdjustment, "run", ()), readonly=("total",)
)
PayrollSerializer._declared_fields["lines"] = PayrollLineSerializer(
    many=True, read_only=True
)
AdvanceSerializer = document_serializer(m.SalaryAdvance, readonly=("settled_in",))
SalaryPaymentSerializer = document_serializer(m.SalaryPayment)
LabourSerializer = model_serializer(m.LabourEntry)


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class AllocationInputSerializer(serializers.Serializer):
    invoice = serializers.PrimaryKeyRelatedField(queryset=Invoice.objects.all())
    amount = serializers.DecimalField(
        max_digits=18, decimal_places=2, min_value=Decimal(".01")
    )


class RevisionSerializer(serializers.Serializer):
    revision = serializers.IntegerField(min_value=1)


class CancellationSerializer(RevisionSerializer):
    reason = serializers.CharField()
    date = serializers.DateField(required=False)


class ChequeActionSerializer(RevisionSerializer):
    date = serializers.DateField()


class RateSerializer(RevisionSerializer):
    rate = serializers.DecimalField(
        max_digits=18, decimal_places=4, min_value=Decimal("0")
    )


class AllocationBatchSerializer(RevisionSerializer):
    allocations = AllocationInputSerializer(many=True)


class AllocationReversalSerializer(RevisionSerializer):
    allocation_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), allow_empty=False
    )
    reason = serializers.CharField()


class ReceiptPostingSerializer(RevisionSerializer):
    allocations = AllocationInputSerializer(many=True, required=False)
