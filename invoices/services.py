from decimal import Decimal, ROUND_HALF_UP
from django.db import transaction
from rest_framework import serializers
from .models import Invoice, Items, InvoiceCounter, InvNum, Term
from operations.services import audit, money


class LegacyLineSerializer(serializers.Serializer):
    id = serializers.CharField(required=False, allow_blank=True)
    density = serializers.CharField(
        max_length=30, allow_blank=True, required=False, default=""
    )
    description = serializers.CharField(allow_blank=True, required=False, default="")
    length = serializers.DecimalField(
        max_digits=18, decimal_places=4, min_value=0, default=0
    )
    breadth = serializers.DecimalField(
        max_digits=18, decimal_places=4, min_value=0, default=0
    )
    height = serializers.DecimalField(
        max_digits=18, decimal_places=4, min_value=0, default=0
    )
    mm = serializers.DecimalField(
        max_digits=18, decimal_places=4, min_value=0, default=0
    )
    rate = serializers.DecimalField(
        max_digits=18, decimal_places=4, min_value=0, default=0
    )
    calculated_rate = serializers.DecimalField(
        max_digits=18, decimal_places=4, min_value=0, default=0
    )
    qty = serializers.DecimalField(
        max_digits=18, decimal_places=4, min_value=Decimal(".0001")
    )
    taxable = serializers.BooleanField()
    tax_include = serializers.BooleanField()


@transaction.atomic
def save_legacy_invoice(invoice, year, user, raw_lines, details):
    # Validate every line before modifying the invoice or counter.
    line_serializer = LegacyLineSerializer(data=raw_lines, many=True)
    line_serializer.is_valid(raise_exception=True)
    if not line_serializer.validated_data:
        raise serializers.ValidationError("Add at least one line.")
    date = serializers.DateField().run_validation(details.get("date"))
    discount = serializers.DecimalField(
        max_digits=18, decimal_places=2, min_value=0
    ).run_validation(details.get("discount", 0))
    paid = serializers.DecimalField(
        max_digits=18, decimal_places=2, min_value=0
    ).run_validation(details.get("paid", 0))
    if not year or not year.start_date <= date <= year.end_date:
        raise serializers.ValidationError(
            "Choose a fiscal year containing the bill date."
        )
    if invoice.pk:
        invoice = Invoice.objects.select_for_update().get(pk=invoice.pk)
        if invoice.source == "api" or invoice.is_posted:
            raise serializers.ValidationError(
                "Posted/API invoices cannot be edited through the legacy form."
            )
    prepared = []
    subtotal = Decimal("0")
    taxable_base = Decimal("0")
    for row in line_serializer.validated_data:
        row = dict(row)
        row.pop("id", None)
        mm = row["length"] * row["breadth"] * row["height"] / Decimal("2592")
        if not mm:
            mm = row["mm"]
        rate = mm * row["rate"] if mm * row["rate"] > 0 else row["calculated_rate"]
        rate = rate.quantize(Decimal(".0001"), rounding=ROUND_HALF_UP)
        amount = money(rate * row["qty"])
        base = (
            money(amount / Decimal("1.13"))
            if row["taxable"] and row["tax_include"]
            else amount
        )
        subtotal += base
        if row["taxable"]:
            taxable_base += base
        row.update(
            mm=float(mm),
            length=float(row["length"]),
            breadth=float(row["breadth"]),
            height=float(row["height"]),
            calculated_rate=rate,
            price=base,
        )
        prepared.append(row)
    if discount > subtotal:
        raise serializers.ValidationError("Discount exceeds subtotal.")
    tax = money(
        (taxable_base - (discount * taxable_base / subtotal if subtotal else 0))
        * Decimal(".13")
    )
    final = money(subtotal - discount + tax)
    if paid > final:
        raise serializers.ValidationError("Paid amount exceeds invoice total.")
    Term.objects.select_for_update().get(pk=year.pk)
    if not invoice.pk:
        invoice.save()
        counter, _ = InvoiceCounter.objects.get_or_create(term=year)
        counter.count += 1
        counter.save()
        InvNum.objects.create(invoice=invoice, num=counter.count)
    invoice.issued_by = user
    invoice.fiscal_year = year
    invoice.date = date
    invoice.discount = discount
    invoice.paid_amount = paid
    invoice.total = final
    invoice.tax = tax
    invoice.to_pay = final - paid
    invoice.notes = details.get("notes", "")
    invoice.vat_bill_no = details.get("vat", "")
    invoice.is_vat = bool(invoice.vat_bill_no and invoice.vat_bill_no.strip())
    invoice.is_posted = True
    invoice.revision += 1
    invoice.save()
    invoice.items_set.all().delete()
    for row in prepared:
        Items.objects.create(invoice=invoice, **row)
    audit(user, invoice, "legacy_post")
    return invoice
