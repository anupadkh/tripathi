from decimal import Decimal, ROUND_HALF_UP
from django.db.models import Sum
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from invoices.models import Invoice, InvNum, InvoiceCounter, Payment
from . import models as m
from .api_errors import Conflict

ZERO = Decimal("0")


def money(value):
    number = Decimal(str(value or 0))
    limit = Decimal("10000000000000000")
    if not number.is_finite() or abs(number) >= limit:
        raise ValidationError(
            "Calculated amount exceeds the supported monetary precision."
        )
    rounded = number.quantize(Decimal(".01"), rounding=ROUND_HALF_UP)
    if abs(rounded) >= limit:
        raise ValidationError(
            "Calculated amount exceeds the supported monetary precision."
        )
    return rounded


def total(queryset, field):
    value = queryset.aggregate(value=Sum(field))["value"] or ZERO
    places = getattr(queryset.model._meta.get_field(field), "decimal_places", 2)
    return value.quantize(Decimal(10) ** -places, rounding=ROUND_HALF_UP)


def audit(user, obj, action, details=None):
    m.AuditEvent.objects.create(
        actor=user,
        resource=obj._meta.label_lower,
        resource_id=obj.pk,
        action=action,
        details=details or {},
    )


def check_revision(obj, value):
    if value is None:
        raise ValidationError({"revision": "Supply the current revision."})
    if str(value) != str(obj.revision):
        raise Conflict()


def touch(obj):
    obj.revision += 1
    obj.save()


def draft(obj):
    if obj.status != "draft":
        raise ValidationError("Only draft documents can be changed.")


def active_account(account):
    if not account.active:
        raise ValidationError("Payment account is inactive.")


def account_balance(account):
    return account.opening_balance + total(account.movements.all(), "amount")


def move_money(account, amount, date, reference, description=""):
    account = m.PaymentAccount.objects.select_for_update().get(pk=account.pk)
    active_account(account)
    if amount < 0 and account_balance(account) + amount < 0:
        raise ValidationError("Insufficient funds in payment account.")
    m.AccountMovement.objects.create(
        account=account,
        amount=money(amount),
        date=date,
        reference=reference,
        description=description,
    )


def move_stock(item, location, qty, date, kind, reference):
    item = m.StockItem.objects.select_for_update().get(pk=item.pk)
    if not item.active:
        raise ValidationError("Stock item is inactive.")
    balance, _ = m.StockBalance.objects.get_or_create(item=item, location=location)
    balance = m.StockBalance.objects.select_for_update().get(pk=balance.pk)
    if balance.quantity + qty < 0:
        raise ValidationError(f"Insufficient stock for {item.sku} at {location.name}.")
    if balance.quantity + qty >= Decimal("100000000000000"):
        raise ValidationError("Stock quantity exceeds the supported precision.")
    balance.quantity += qty
    balance.save(update_fields=["quantity"])
    m.StockMovement.objects.create(
        item=item,
        location=location,
        quantity=qty,
        date=date,
        kind=kind,
        reference=reference,
    )


def invoice_outstanding(invoice):
    return (invoice.to_pay or ZERO) - total(
        invoice.allocations.filter(reversed=False, receipt__status="posted")
        .exclude(receipt__cheque_status="bounced")
        .exclude(receipt__method="cheque", receipt__cheque_status="pending"),
        "amount",
    )


def invoice_available(invoice):
    return (invoice.to_pay or ZERO) - total(
        invoice.allocations.filter(reversed=False, receipt__status="posted").exclude(
            receipt__cheque_status="bounced"
        ),
        "amount",
    )


def line_billing_quantity(line):
    """Keep piece counts for stock; bill dimensional foam using the old mm rule."""
    if line.unit != "mm":
        return line.qty
    dimensions = [
        Decimal(str(value or 0)) for value in (line.length, line.breadth, line.height)
    ]
    mm = dimensions[0] * dimensions[1] * dimensions[2] / Decimal("2592")
    if not mm:
        mm = Decimal(str(line.mm or 0))
    quantity = mm * line.qty
    if quantity <= 0 or quantity >= Decimal("100000000000000"):
        raise ValidationError(
            "Dimensional foam needs positive dimensions or a positive manual mm value."
        )
    return quantity.quantize(Decimal(".0001"), rounding=ROUND_HALF_UP)


def group_invoice(invoice):
    if invoice.source != "api" or invoice.status not in ("draft", "grouped"):
        raise ValidationError("Only API drafts can be grouped.")
    lines = list(invoice.items_set.all())
    if not lines:
        raise ValidationError("Add at least one foam line.")
    groups = {}
    for line in lines:
        key = (line.density, line.unit, line.taxable)
        groups[key] = groups.get(key, ZERO) + line_billing_quantity(line)
    invoice.density_groups.all().delete()
    for (density, unit, taxable), qty in groups.items():
        if qty >= Decimal("100000000000000"):
            raise ValidationError("Grouped quantity exceeds the supported precision.")
        m.DensityGroup.objects.create(
            invoice=invoice, density=density, unit=unit, taxable=taxable, quantity=qty
        )
    invoice.status = "grouped"
    touch(invoice)


def invoice_totals(invoice):
    groups = list(invoice.density_groups.all())
    if not groups:
        raise ValidationError("Group the invoice before pricing.")
    subtotal = sum((money(g.quantity * g.rate) for g in groups), ZERO)
    taxable = sum((money(g.quantity * g.rate) for g in groups if g.taxable), ZERO)
    discount = invoice.discount or ZERO
    if discount < 0 or discount > subtotal:
        raise ValidationError("Discount must be between zero and subtotal.")
    taxable_discount = money(discount * taxable / subtotal) if subtotal else ZERO
    tax = (
        money((taxable - taxable_discount) * invoice.vat_rate / 100)
        if invoice.is_vat
        else ZERO
    )
    return {
        "subtotal": money(subtotal),
        "discount": discount,
        "tax": tax,
        "total": money(subtotal - discount + tax),
    }


def post_invoice(invoice):
    if invoice.source != "api" or invoice.status != "grouped":
        raise ValidationError("Group and price an API invoice before posting.")
    year = invoice.fiscal_year
    if not year or not year.start_date <= invoice.date <= year.end_date:
        raise ValidationError("Invoice date must fall within its fiscal year.")
    values = invoice_totals(invoice)
    if any(g.rate <= 0 for g in invoice.density_groups.all()):
        raise ValidationError("Enter a positive rate for each density group.")
    # The fiscal-year row serializes numbering, including first counter creation.
    type(year).objects.select_for_update().get(pk=year.pk)
    series = "VAT" if invoice.is_vat else "INV"
    sequence, _ = m.DocumentSequence.objects.get_or_create(
        fiscal_year=year, series=series
    )
    sequence.value += 1
    sequence.save()
    invoice.number = f"{series}-{year.pk}-{sequence.value:06d}"
    if invoice.is_vat:
        invoice.vat_bill_no = invoice.number
    for group in invoice.density_groups.all():
        group.amount = money(group.quantity * group.rate)
        group.save(update_fields=["amount"])
        for line in invoice.items_set.filter(
            density=group.density, unit=group.unit, taxable=group.taxable
        ):
            line.rate = group.rate
            line.calculated_rate = (
                group.rate * line_billing_quantity(line) / line.qty
            ).quantize(Decimal(".0001"), rounding=ROUND_HALF_UP)
            line.price = money(line_billing_quantity(line) * group.rate)
            line.save()
    links = (
        m.SalesLineStock.objects.filter(line__invoice=invoice)
        .select_related("line", "item", "location")
        .order_by("item_id", "location_id")
    )
    movements = {}
    for link in links:
        key = (link.item_id, link.location_id)
        if key not in movements:
            movements[key] = [link.item, link.location, ZERO]
        movements[key][2] += link.line.qty
    for item, location, qty in movements.values():
        move_stock(item, location, -qty, invoice.date, "sale", f"invoice:{invoice.pk}")
    invoice.total = values["total"]
    invoice.tax = values["tax"]
    invoice.to_pay = values["total"]
    invoice.paid_amount = ZERO
    invoice.status = "posted"
    invoice.is_posted = True
    counter, _ = InvoiceCounter.objects.get_or_create(term=year)
    counter.count += 1
    counter.save()
    InvNum.objects.create(invoice=invoice, num=counter.count)
    touch(invoice)


def validate_method(obj):
    active_account(obj.account)
    kinds = {"cash": "cash", "mobile": "mobile", "bank": "bank", "cheque": "bank"}
    if obj.account.kind != kinds[obj.method]:
        raise ValidationError("Payment method does not match account type.")
    if obj.method == "cheque" and (
        not obj.cheque_number.strip() or not obj.cheque_bank.strip()
    ):
        raise ValidationError("Cheque number and bank are required.")


def settle_receipt(receipt, date):
    move_money(
        receipt.account,
        receipt.amount,
        date,
        f"customerreceipt:{receipt.pk}",
        "Customer receipt",
    )
    receipt.legacy_payment = Payment.objects.create(
        customer=receipt.customer,
        amount=receipt.amount,
        payment_mode={"cash": 2, "cheque": 1, "mobile": 4, "bank": 3}[receipt.method],
        date=date,
    )


def post_receipt(receipt):
    draft(receipt)
    validate_method(receipt)
    if receipt.method != "cheque":
        settle_receipt(receipt, receipt.date)
    receipt.status = "posted"
    touch(receipt)


def allocate_receipt(receipt, allocations):
    if receipt.status != "posted" or receipt.cheque_status == "bounced":
        raise ValidationError("Receipt must be posted and not bounced.")
    if not allocations:
        raise ValidationError("Provide at least one allocation.")
    seen = set()
    existing = total(receipt.allocations.filter(reversed=False), "amount")
    available = receipt.amount - existing
    for allocation in sorted(allocations, key=lambda a: a["invoice"].pk):
        invoice = Invoice.objects.select_for_update().get(pk=allocation["invoice"].pk)
        if invoice.pk in seen:
            raise ValidationError("Duplicate invoice allocation.")
        seen.add(invoice.pk)
        if invoice.status != "posted" or invoice.issued_for_id != receipt.customer_id:
            raise ValidationError(
                "Allocation must reference a posted invoice for this customer."
            )
        amount = allocation["amount"]
        if amount <= 0 or amount > available or amount > invoice_available(invoice):
            raise ValidationError(
                "Allocation exceeds available payment or invoice balance."
            )
        allocation = receipt.allocations.filter(invoice=invoice).first()
        if allocation and not allocation.reversed:
            raise ValidationError("This receipt is already allocated to the invoice.")
        if allocation:
            raise ValidationError(
                "Use a new receipt for an invoice whose allocation was reversed; history is retained."
            )
        m.PaymentAllocation.objects.create(
            receipt=receipt, invoice=invoice, amount=amount
        )
        available -= amount
        touch(invoice)
    touch(receipt)


def post_supplier_payment(payment):
    draft(payment)
    validate_method(payment)
    m.Supplier.objects.select_for_update().get(pk=payment.supplier_id)
    if payment.purchase:
        purchase = m.PurchaseBill.objects.select_for_update().get(
            pk=payment.purchase_id
        )
        if purchase.supplier_id != payment.supplier_id or purchase.status != "posted":
            raise ValidationError("Select a posted purchase for this supplier.")
        paid = total(
            m.SupplierPayment.objects.filter(
                purchase=purchase, status="posted"
            ).exclude(cheque_status="bounced"),
            "amount",
        )
        if payment.amount > purchase.total - paid:
            raise ValidationError("Payment exceeds purchase balance.")
    if payment.method != "cheque":
        move_money(
            payment.account,
            -payment.amount,
            payment.date,
            f"supplierpayment:{payment.pk}",
        )
    payment.status = "posted"
    touch(payment)


def cheque_action(obj, action, date):
    allowed = ("pending", "cleared") if action == "bounce" else ("pending",)
    if (
        obj.method != "cheque"
        or obj.status != "posted"
        or obj.cheque_status not in allowed
    ):
        raise ValidationError(
            "Cheque cannot be cleared or bounced in its current state."
        )
    if date < obj.date or (obj.clearance_date and date < obj.clearance_date):
        raise ValidationError("Cheque event date cannot precede its payment date.")
    if action == "clear":
        if isinstance(obj, m.CustomerReceipt):
            settle_receipt(obj, date)
        else:
            move_money(obj.account, -obj.amount, date, f"supplierpayment:{obj.pk}")
        obj.cheque_status = "cleared"
        obj.clearance_date = date
    else:
        if obj.cheque_status == "cleared":
            amount = -obj.amount if isinstance(obj, m.CustomerReceipt) else obj.amount
            move_money(
                obj.account,
                amount,
                date,
                f"{obj._meta.model_name}-bounce:{obj.pk}",
                "Cheque bounce reversal",
            )
            if isinstance(obj, m.CustomerReceipt) and obj.legacy_payment:
                obj.legacy_payment.amount = ZERO
                obj.legacy_payment.save(update_fields=["amount"])
        if isinstance(obj, m.CustomerReceipt):
            for allocation in obj.allocations.select_related("invoice"):
                invoice = Invoice.objects.select_for_update().get(
                    pk=allocation.invoice_id
                )
                touch(invoice)
        obj.cheque_status = "bounced"
    touch(obj)


def post_purchase(bill):
    draft(bill)
    lines = list(bill.lines.all())
    if not lines:
        raise ValidationError("Add purchase lines.")
    for line in lines:
        if not line.item.active:
            raise ValidationError("Purchase item is inactive.")
        line.amount = money(line.quantity * line.rate)
        line.save(update_fields=["amount"])
    bill.total = sum((line.amount for line in lines), ZERO) + bill.tax
    bill.status = "posted"
    touch(bill)


def post_goods_receipt(receipt):
    draft(receipt)
    purchase = m.PurchaseBill.objects.select_for_update().get(pk=receipt.purchase_id)
    if purchase.status != "posted":
        raise ValidationError("Purchase must be posted before receiving goods.")
    lines = list(
        receipt.lines.select_related("purchase_line__item").order_by(
            "purchase_line__item_id"
        )
    )
    if not lines:
        raise ValidationError("Add received quantities.")
    movements = {}
    for line in lines:
        source = line.purchase_line
        if source.bill_id != purchase.pk:
            raise ValidationError("Receipt line belongs to another purchase.")
        received = total(
            source.receipt_lines.filter(receipt__status="posted"), "quantity"
        )
        if received + line.quantity > source.quantity:
            raise ValidationError("Received quantity exceeds purchase quantity.")
        if source.item_id not in movements:
            movements[source.item_id] = [source.item, ZERO]
        movements[source.item_id][1] += line.quantity
    for item, qty in movements.values():
        move_stock(
            item,
            receipt.location,
            qty,
            receipt.received_date,
            "purchase",
            f"goodsreceipt:{receipt.pk}",
        )
    receipt.status = "posted"
    touch(receipt)


def post_transfer(obj):
    draft(obj)
    if obj.source_account_id == obj.destination_account_id:
        raise ValidationError("Transfer accounts must differ.")
    list(
        m.PaymentAccount.objects.select_for_update()
        .filter(pk__in=[obj.source_account_id, obj.destination_account_id])
        .order_by("pk")
    )
    move_money(obj.source_account, -obj.amount, obj.date, f"accounttransfer:{obj.pk}")
    move_money(
        obj.destination_account, obj.amount, obj.date, f"accounttransfer:{obj.pk}"
    )
    obj.status = "posted"
    touch(obj)


def post_adjustment(obj):
    draft(obj)
    lines = list(obj.lines.select_related("item").order_by("item_id"))
    if not lines or not obj.reason.strip():
        raise ValidationError("Adjustment lines and reason are required.")
    items = {}
    for line in lines:
        if not line.quantity:
            raise ValidationError("Adjustment quantity must be nonzero.")
        if line.item_id not in items:
            items[line.item_id] = [line.item, ZERO]
        items[line.item_id][1] += line.quantity
    for item, qty in items.values():
        move_stock(
            item, obj.location, qty, obj.date, "adjustment", f"stockadjustment:{obj.pk}"
        )
    obj.status = "posted"
    touch(obj)


def lock_job(job_id):
    job = m.JobOrder.objects.select_for_update().get(pk=job_id)
    if job.status != "posted" or job.completed:
        raise ValidationError("Select an open posted job order.")
    return job


def post_issue(obj):
    draft(obj)
    lock_job(obj.job_id)
    lines = list(obj.lines.select_related("item").order_by("item_id"))
    if not lines:
        raise ValidationError("Add material issue lines.")
    items = {}
    for line in lines:
        if line.item.kind == "finished":
            raise ValidationError(
                "Material issue requires a raw material or consumable item."
            )
        if line.item_id not in items:
            items[line.item_id] = [line.item, ZERO]
        items[line.item_id][1] += line.quantity
    for item, qty in items.values():
        move_stock(
            item,
            obj.location,
            -qty,
            obj.date,
            "material_issue",
            f"materialissue:{obj.pk}",
        )
    obj.status = "posted"
    touch(obj)


def validate_consumption(report):
    for line in report.consumption.all():
        issued = total(
            m.MaterialIssueLine.objects.filter(
                issue__job=report.job, issue__status="posted", item=line.item
            ),
            "quantity",
        )
        used = m.ProductionConsumption.objects.filter(
            report__job=report.job, report__status="posted", item=line.item
        ).exclude(report=report)
        consumed = total(used, "consumed_quantity") + total(used, "waste_quantity")
        if line.consumed_quantity + line.waste_quantity + consumed > issued:
            raise ValidationError(
                "Reported consumption and waste exceed issued material."
            )


def post_production(obj):
    draft(obj)
    job = lock_job(obj.job_id)
    if not obj.consumption.exists():
        raise ValidationError("Record material consumption before posting production.")
    if (
        sum(
            (
                line.consumed_quantity + line.waste_quantity
                for line in obj.consumption.all()
            ),
            ZERO,
        )
        <= 0
    ):
        raise ValidationError("Record positive material consumption or waste.")
    validate_consumption(obj)
    move_stock(
        job.product,
        obj.location,
        obj.produced_quantity,
        obj.date,
        "production",
        f"productionreport:{obj.pk}",
    )
    obj.status = "posted"
    touch(obj)


def complete_job(job):
    lock_job(job.pk)
    if not job.reports.filter(status="posted").exists():
        raise ValidationError("Post a production report before completing the job.")
    issued = {}
    for line in m.MaterialIssueLine.objects.filter(
        issue__job=job, issue__status="posted"
    ):
        issued[line.item_id] = issued.get(line.item_id, ZERO) + line.quantity
    for item_id, qty in issued.items():
        lines = m.ProductionConsumption.objects.filter(
            report__job=job, report__status="posted", item_id=item_id
        )
        if total(lines, "consumed_quantity") + total(lines, "waste_quantity") != qty:
            raise ValidationError(
                "Account for all issued materials as consumption or waste before completing the job."
            )
    job.completed = True
    touch(job)


def calculate_payroll(run):
    draft(run)
    if run.start_date > run.end_date:
        raise ValidationError("Payroll start date must not exceed end date.")
    run.lines.all().delete()
    entries = m.LabourEntry.objects.filter(
        worksheet__status="posted",
        worksheet__date__range=(run.start_date, run.end_date),
    )
    worker_ids = set(entries.values_list("worker_id", flat=True)) | set(
        run.adjustments.values_list("worker_id", flat=True)
    )
    worker_ids |= set(
        m.SalaryAdvance.objects.filter(
            status="posted", settled_in__isnull=True, date__lte=run.end_date
        ).values_list("worker_id", flat=True)
    )
    run.total = ZERO
    for worker in (
        m.Worker.objects.select_for_update().filter(pk__in=worker_ids).order_by("pk")
    ):
        overlap = m.PayrollLine.objects.filter(
            worker=worker,
            run__status="posted",
            run__start_date__lte=run.end_date,
            run__end_date__gte=run.start_date,
        ).exclude(run=run)
        if overlap.exists():
            raise ValidationError(
                "A posted payroll already covers this worker and period."
            )
        units = total(entries.filter(worker=worker), "units")
        overtime = total(entries.filter(worker=worker), "overtime_hours")
        if worker.salary_basis == "monthly" and units > run.expected_days:
            raise ValidationError("Monthly attendance exceeds expected days.")
        base = (
            money(worker.rate * units / run.expected_days)
            if worker.salary_basis == "monthly"
            else money(worker.rate * units)
        )
        overtime_pay = money(overtime * worker.overtime_rate)
        allowance = total(
            run.adjustments.filter(worker=worker, kind="allowance"), "amount"
        )
        deduction = total(
            run.adjustments.filter(worker=worker, kind="deduction"), "amount"
        )
        advances = total(
            m.SalaryAdvance.objects.filter(
                worker=worker,
                status="posted",
                settled_in__isnull=True,
                date__lte=run.end_date,
            ),
            "amount",
        )
        net = money(base + overtime_pay + allowance - deduction - advances)
        if net < 0:
            raise ValidationError(
                "Deductions and advances exceed earned pay. Adjust the payroll before approving."
            )
        m.PayrollLine.objects.create(
            run=run,
            worker=worker,
            units=units,
            overtime_hours=overtime,
            base_pay=base,
            overtime_pay=overtime_pay,
            allowances=allowance,
            deductions=deduction,
            advances=advances,
            net_pay=net,
            salary_basis=worker.salary_basis,
            rate=worker.rate,
            overtime_rate=worker.overtime_rate,
        )
        run.total += net
    if not worker_ids:
        raise ValidationError("No posted labour entries or adjustments in this period.")
    touch(run)


def approve_payroll(run):
    calculate_payroll(run)
    for line in run.lines.all():
        m.SalaryAdvance.objects.filter(
            worker=line.worker,
            status="posted",
            settled_in__isnull=True,
            date__lte=run.end_date,
        ).update(settled_in=run)
    run.status = "posted"
    touch(run)


def post_cash_document(obj):
    draft(obj)
    if isinstance(obj, m.SalaryAdvance):
        m.Worker.objects.select_for_update().get(pk=obj.worker_id)
    if isinstance(obj, m.SalaryPayment):
        line = (
            m.PayrollLine.objects.select_for_update()
            .select_related("run")
            .get(pk=obj.payroll_line_id)
        )
        if line.run.status != "posted":
            raise ValidationError("Approve payroll before paying salary.")
        paid = total(line.payments.filter(status="posted"), "amount")
        if paid + obj.amount > line.net_pay:
            raise ValidationError("Salary payment exceeds unpaid salary.")
    if (
        isinstance(obj, m.Expense)
        and obj.worksheet
        and obj.job
        and obj.worksheet.job_id != obj.job_id
    ):
        raise ValidationError("Worksheet and expense job must match.")
    move_money(obj.account, -obj.amount, obj.date, f"{obj._meta.model_name}:{obj.pk}")
    obj.status = "posted"
    touch(obj)


def post_simple(obj):
    draft(obj)
    if isinstance(obj, m.JobOrder) and (
        not obj.product.active or obj.product.kind != "finished"
    ):
        raise ValidationError("Job product must be an active finished item.")
    if isinstance(obj, m.Worksheet) and not obj.entries.exists():
        raise ValidationError("Add labour entries before posting the worksheet.")
    if isinstance(obj, m.Worksheet):
        worker_ids = obj.entries.values_list("worker_id", flat=True)
        if m.PayrollLine.objects.filter(
            worker_id__in=worker_ids,
            run__status="posted",
            run__start_date__lte=obj.date,
            run__end_date__gte=obj.date,
        ).exists():
            raise ValidationError(
                "Payroll has already been approved for these workers and this date."
            )
    obj.status = "posted"
    touch(obj)


POSTERS = {
    m.PurchaseBill: post_purchase,
    m.GoodsReceipt: post_goods_receipt,
    m.CustomerReceipt: post_receipt,
    m.SupplierPayment: post_supplier_payment,
    m.AccountTransfer: post_transfer,
    m.StockAdjustment: post_adjustment,
    m.MaterialIssue: post_issue,
    m.ProductionReport: post_production,
    m.Expense: post_cash_document,
    m.SalaryAdvance: post_cash_document,
    m.SalaryPayment: post_cash_document,
    m.JobOrder: post_simple,
    m.Worksheet: post_simple,
}


def cancel_invoice(invoice, reason, date=None):
    date = date or timezone.localdate()
    if invoice.date and date < invoice.date:
        raise ValidationError("Reversal date cannot precede invoice date.")
    if invoice.source != "api":
        raise ValidationError(
            "Legacy invoices require a reviewed correction; automatic cancellation is disabled."
        )
    if invoice.status == "cancelled":
        raise ValidationError("Invoice is already cancelled.")
    if not reason.strip():
        raise ValidationError("A cancellation reason is required.")
    if (
        invoice.allocations.filter(reversed=False)
        .exclude(receipt__cheque_status="bounced")
        .exists()
        or invoice.paid_amount
    ):
        raise ValidationError(
            "Reverse or resolve payments before cancelling an invoice."
        )
    if invoice.status == "posted":
        for movement in (
            m.StockMovement.objects.filter(reference=f"invoice:{invoice.pk}")
            .select_related("item", "location")
            .order_by("item_id", "location_id")
        ):
            move_stock(
                movement.item,
                movement.location,
                -movement.quantity,
                date,
                "sale_reversal",
                f"invoice-cancel:{invoice.pk}",
            )
    invoice.status = "cancelled"
    invoice.is_posted = False
    invoice.to_pay = ZERO
    invoice.cancellation_reason = reason
    touch(invoice)


def reverse_allocations(receipt, allocation_ids, reason):
    if not reason.strip():
        raise ValidationError("A reversal reason is required.")
    allocations = list(
        receipt.allocations.filter(pk__in=allocation_ids, reversed=False)
        .select_related("invoice")
        .order_by("invoice_id")
    )
    if not allocations or len(allocations) != len(set(allocation_ids)):
        raise ValidationError("Choose active allocations belonging to this receipt.")
    for allocation in allocations:
        invoice = Invoice.objects.select_for_update().get(pk=allocation.invoice_id)
        allocation.reversed = True
        allocation.reversal_reason = reason
        allocation.save()
        touch(invoice)
    touch(receipt)


def cancel_document(obj, reason, date):
    if obj.status == "cancelled":
        raise ValidationError("Document is already cancelled.")
    if not reason.strip():
        raise ValidationError("A cancellation reason is required.")
    if date < obj.date:
        raise ValidationError("Reversal date cannot precede document date.")
    was_posted = obj.status == "posted"
    if was_posted:
        if isinstance(obj, m.PurchaseBill):
            if (
                obj.receipts.filter(status="posted").exists()
                or m.SupplierPayment.objects.filter(purchase=obj, status="posted")
                .exclude(cheque_status="bounced")
                .exists()
            ):
                raise ValidationError(
                    "Reverse receipts and payments before cancelling the purchase."
                )
        if isinstance(obj, m.JobOrder):
            if (
                obj.issues.filter(status="posted").exists()
                or obj.reports.filter(status="posted").exists()
            ):
                raise ValidationError(
                    "Reverse material issues and production reports before cancelling the job."
                )
        if isinstance(obj, m.MaterialIssue):
            job = m.JobOrder.objects.select_for_update().get(pk=obj.job_id)
            if job.completed:
                raise ValidationError("Completed job records cannot be cancelled.")
            for line in obj.lines.all():
                issued = total(
                    m.MaterialIssueLine.objects.filter(
                        issue__job=job, issue__status="posted", item=line.item
                    ).exclude(issue=obj),
                    "quantity",
                )
                used = m.ProductionConsumption.objects.filter(
                    report__job=job, report__status="posted", item=line.item
                )
                if (
                    total(used, "consumed_quantity") + total(used, "waste_quantity")
                    > issued
                ):
                    raise ValidationError(
                        "Issued materials have already been consumed; reverse production first."
                    )
        if isinstance(obj, m.ProductionReport):
            job = m.JobOrder.objects.select_for_update().get(pk=obj.job_id)
            if job.completed:
                raise ValidationError("Completed job records cannot be cancelled.")
        if isinstance(obj, m.Worksheet):
            if m.PayrollLine.objects.filter(
                worker_id__in=obj.entries.values_list("worker_id", flat=True),
                run__status="posted",
                run__start_date__lte=obj.date,
                run__end_date__gte=obj.date,
            ).exists():
                raise ValidationError(
                    "Cancel the covering payroll before cancelling this worksheet."
                )
        if isinstance(obj, m.PayrollRun):
            if m.SalaryPayment.objects.filter(
                payroll_line__run=obj, status="posted"
            ).exists():
                raise ValidationError(
                    "Reverse salary payments before cancelling payroll."
                )
            m.SalaryAdvance.objects.filter(settled_in=obj).update(settled_in=None)
        if isinstance(obj, m.SalaryAdvance) and obj.settled_in_id:
            raise ValidationError(
                "Advance is already deducted from an approved payroll."
            )
        if isinstance(obj, m.CustomerReceipt):
            if obj.allocations.filter(reversed=False).exists():
                raise ValidationError(
                    "Reverse allocations before cancelling the receipt."
                )
            if obj.legacy_payment:
                obj.legacy_payment.amount = ZERO
                obj.legacy_payment.save(update_fields=["amount"])
        reference = f"{obj._meta.model_name}:{obj.pk}"
        movements = list(
            m.StockMovement.objects.filter(reference=reference)
            .select_related("item", "location")
            .order_by("item_id", "location_id")
        )
        for movement in movements:
            move_stock(
                movement.item,
                movement.location,
                -movement.quantity,
                date,
                "reversal",
                f"{obj._meta.model_name}-cancel:{obj.pk}",
            )
        # Cleared then bounced cheques already have a monetary reversal.
        if not (
            isinstance(obj, (m.CustomerReceipt, m.SupplierPayment))
            and obj.cheque_status == "bounced"
        ):
            movements = list(
                m.AccountMovement.objects.filter(reference=reference)
                .select_related("account")
                .order_by("amount", "account_id")
            )
            for movement in movements:
                move_money(
                    movement.account,
                    -movement.amount,
                    date,
                    f"{obj._meta.model_name}-cancel:{obj.pk}",
                    reason,
                )
    obj.status = "cancelled"
    obj.cancellation_reason = reason
    touch(obj)
