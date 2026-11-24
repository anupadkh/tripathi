from decimal import Decimal
from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

ZERO = Decimal("0")
POSITIVE = MinValueValidator(Decimal("0.0001"))
NONNEGATIVE = MinValueValidator(ZERO)


def money(default=ZERO, **kwargs):
    return models.DecimalField(
        max_digits=18, decimal_places=2, default=default, **kwargs
    )


def qty_field(**kwargs):
    return models.DecimalField(max_digits=18, decimal_places=4, **kwargs)


class AccessToken(models.Model):
    digest = models.CharField(max_length=64, unique=True)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)


class PostingLock(models.Model):
    """Serialize postings within this single-company installation."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)


class AuditEvent(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    action = models.CharField(max_length=40)
    resource = models.CharField(max_length=80)
    resource_id = models.PositiveIntegerField()
    details = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class IdempotencyRecord(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    key = models.CharField(max_length=100)
    request_hash = models.CharField(max_length=64)
    response = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "key"], name="unique_user_retry_key"
            )
        ]


class DocumentSequence(models.Model):
    fiscal_year = models.ForeignKey("invoices.Term", on_delete=models.PROTECT)
    series = models.CharField(max_length=10)
    value = models.PositiveIntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["fiscal_year", "series"], name="unique_document_series"
            )
        ]


class Supplier(models.Model):
    name = models.CharField(max_length=300)
    address = models.CharField(max_length=300, blank=True)
    phone = models.CharField(max_length=40, blank=True)
    pan = models.CharField(max_length=40, blank=True)
    opening_balance = money()

    def __str__(self):
        return self.name


class PaymentAccount(models.Model):
    name = models.CharField(max_length=100, unique=True)
    kind = models.CharField(
        max_length=10, choices=[(s, s) for s in ("cash", "bank", "mobile")]
    )
    bank_name = models.CharField(max_length=100, blank=True)
    account_number = models.CharField(max_length=100, blank=True)
    opening_balance = money()
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class AccountMovement(models.Model):
    account = models.ForeignKey(
        PaymentAccount, on_delete=models.PROTECT, related_name="movements"
    )
    amount = money()
    date = models.DateField()
    reference = models.CharField(max_length=100)
    description = models.CharField(max_length=300, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["account", "reference"], name="unique_account_movement"
            )
        ]


class Document(models.Model):
    date = models.DateField(default=timezone.localdate)
    status = models.CharField(
        max_length=12,
        default="draft",
        choices=[(s, s) for s in ("draft", "posted", "cancelled")],
    )
    revision = models.PositiveIntegerField(default=1)
    notes = models.TextField(blank=True)
    cancellation_reason = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True


class DensityGroup(models.Model):
    invoice = models.ForeignKey(
        "invoices.Invoice", on_delete=models.CASCADE, related_name="density_groups"
    )
    density = models.CharField(max_length=30)
    unit = models.CharField(max_length=20)
    taxable = models.BooleanField(default=True)
    quantity = qty_field()
    rate = qty_field(default=ZERO, validators=[NONNEGATIVE])
    amount = money()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["invoice", "density", "unit", "taxable"],
                name="unique_invoice_density_group",
            )
        ]


class StockItem(models.Model):
    sku = models.CharField(max_length=80, unique=True)
    name = models.CharField(max_length=200)
    kind = models.CharField(
        max_length=12, choices=[(s, s) for s in ("raw", "finished", "consumable")]
    )
    density = models.CharField(max_length=30, blank=True)
    unit = models.CharField(max_length=20, default="piece")
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Location(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class SalesLineStock(models.Model):
    line = models.OneToOneField(
        "invoices.Items", on_delete=models.CASCADE, related_name="stock_link"
    )
    item = models.ForeignKey(StockItem, on_delete=models.PROTECT)
    location = models.ForeignKey(Location, on_delete=models.PROTECT)


class StockBalance(models.Model):
    item = models.ForeignKey(StockItem, on_delete=models.PROTECT)
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    quantity = qty_field(default=ZERO)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["item", "location"], name="unique_stock_balance"
            ),
            models.CheckConstraint(
                condition=Q(quantity__gte=0), name="stock_balance_nonnegative"
            ),
        ]


class StockMovement(models.Model):
    item = models.ForeignKey(StockItem, on_delete=models.PROTECT)
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    quantity = qty_field()
    date = models.DateField()
    kind = models.CharField(max_length=30)
    reference = models.CharField(max_length=100)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["item", "location", "reference"], name="unique_stock_movement"
            )
        ]


class CustomerReceipt(Document):
    customer = models.ForeignKey("invoices.Customer", on_delete=models.PROTECT)
    amount = money(validators=[MinValueValidator(Decimal("0.01"))])
    method = models.CharField(
        max_length=10, choices=[(s, s) for s in ("cash", "cheque", "mobile", "bank")]
    )
    account = models.ForeignKey(PaymentAccount, on_delete=models.PROTECT)
    cheque_number = models.CharField(max_length=100, blank=True)
    cheque_bank = models.CharField(max_length=100, blank=True)
    cheque_status = models.CharField(
        max_length=10,
        default="pending",
        choices=[(s, s) for s in ("pending", "cleared", "bounced")],
    )
    clearance_date = models.DateField(null=True, blank=True)
    legacy_payment = models.OneToOneField(
        "invoices.Payment",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="receipt",
    )


class PaymentAllocation(models.Model):
    receipt = models.ForeignKey(
        CustomerReceipt, on_delete=models.PROTECT, related_name="allocations"
    )
    invoice = models.ForeignKey(
        "invoices.Invoice", on_delete=models.PROTECT, related_name="allocations"
    )
    amount = money(validators=[MinValueValidator(Decimal("0.01"))])
    reversed = models.BooleanField(default=False)
    reversal_reason = models.TextField(blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["receipt", "invoice"], name="unique_receipt_invoice"
            )
        ]


class AccountTransfer(Document):
    source_account = models.ForeignKey(
        PaymentAccount, on_delete=models.PROTECT, related_name="+"
    )
    destination_account = models.ForeignKey(
        PaymentAccount, on_delete=models.PROTECT, related_name="+"
    )
    amount = money(validators=[MinValueValidator(Decimal("0.01"))])


class PurchaseBill(Document):
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    bill_number = models.CharField(max_length=100)
    billed_date = models.DateField()
    credit_bank_name = models.CharField(max_length=100, blank=True)
    payment_method = models.CharField(
        max_length=10,
        choices=[(s, s) for s in ("cash", "credit", "cheque", "bank", "mobile")],
    )
    tax = money(validators=[NONNEGATIVE])
    total = money()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["supplier", "bill_number"], name="unique_supplier_bill"
            )
        ]


class PurchaseLine(models.Model):
    bill = models.ForeignKey(
        PurchaseBill, on_delete=models.CASCADE, related_name="lines"
    )
    item = models.ForeignKey(StockItem, on_delete=models.PROTECT)
    quantity = qty_field(validators=[POSITIVE])
    rate = qty_field(validators=[NONNEGATIVE])
    amount = money()


class GoodsReceipt(Document):
    purchase = models.ForeignKey(
        PurchaseBill, on_delete=models.PROTECT, related_name="receipts"
    )
    received_date = models.DateField()
    location = models.ForeignKey(Location, on_delete=models.PROTECT)


class GoodsReceiptLine(models.Model):
    receipt = models.ForeignKey(
        GoodsReceipt, on_delete=models.CASCADE, related_name="lines"
    )
    purchase_line = models.ForeignKey(
        PurchaseLine, on_delete=models.PROTECT, related_name="receipt_lines"
    )
    quantity = qty_field(validators=[POSITIVE])

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["receipt", "purchase_line"], name="unique_receipt_purchase_line"
            )
        ]


class SupplierPayment(Document):
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT)
    purchase = models.ForeignKey(
        PurchaseBill, null=True, blank=True, on_delete=models.PROTECT
    )
    amount = money(validators=[MinValueValidator(Decimal("0.01"))])
    method = models.CharField(
        max_length=10, choices=[(s, s) for s in ("cash", "cheque", "mobile", "bank")]
    )
    account = models.ForeignKey(PaymentAccount, on_delete=models.PROTECT)
    cheque_number = models.CharField(max_length=100, blank=True)
    cheque_bank = models.CharField(max_length=100, blank=True)
    cheque_status = models.CharField(
        max_length=10,
        default="pending",
        choices=[(s, s) for s in ("pending", "cleared", "bounced")],
    )
    clearance_date = models.DateField(null=True, blank=True)


class StockAdjustment(Document):
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    reason = models.CharField(max_length=300)


class StockAdjustmentLine(models.Model):
    adjustment = models.ForeignKey(
        StockAdjustment, on_delete=models.CASCADE, related_name="lines"
    )
    item = models.ForeignKey(StockItem, on_delete=models.PROTECT)
    quantity = qty_field()


class JobOrder(Document):
    product = models.ForeignKey(StockItem, on_delete=models.PROTECT)
    planned_quantity = qty_field(validators=[POSITIVE])
    completed = models.BooleanField(default=False)


class MaterialIssue(Document):
    job = models.ForeignKey(JobOrder, on_delete=models.PROTECT, related_name="issues")
    location = models.ForeignKey(Location, on_delete=models.PROTECT)


class MaterialIssueLine(models.Model):
    issue = models.ForeignKey(
        MaterialIssue, on_delete=models.CASCADE, related_name="lines"
    )
    item = models.ForeignKey(StockItem, on_delete=models.PROTECT)
    quantity = qty_field(validators=[POSITIVE])


class ProductionReport(Document):
    job = models.ForeignKey(JobOrder, on_delete=models.PROTECT, related_name="reports")
    location = models.ForeignKey(Location, on_delete=models.PROTECT)
    produced_quantity = qty_field(validators=[POSITIVE])


class ProductionConsumption(models.Model):
    report = models.ForeignKey(
        ProductionReport, on_delete=models.CASCADE, related_name="consumption"
    )
    item = models.ForeignKey(StockItem, on_delete=models.PROTECT)
    consumed_quantity = qty_field(validators=[NONNEGATIVE])
    waste_quantity = qty_field(default=ZERO, validators=[NONNEGATIVE])

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["report", "item"], name="unique_report_consumption"
            )
        ]


class ExpenseCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)

    def __str__(self):
        return self.name


class Expense(Document):
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT)
    payee = models.CharField(max_length=200, blank=True)
    origin = models.CharField(max_length=200, blank=True)
    amount = money(validators=[MinValueValidator(Decimal("0.01"))])
    account = models.ForeignKey(PaymentAccount, on_delete=models.PROTECT)
    job = models.ForeignKey(JobOrder, null=True, blank=True, on_delete=models.PROTECT)
    worksheet = models.ForeignKey(
        "Worksheet", null=True, blank=True, on_delete=models.PROTECT
    )


class Worker(models.Model):
    name = models.CharField(max_length=200)
    phone = models.CharField(max_length=40, blank=True)
    salary_basis = models.CharField(
        max_length=10, choices=[(s, s) for s in ("monthly", "daily", "hourly", "piece")]
    )
    rate = money(validators=[NONNEGATIVE])
    overtime_rate = money(validators=[NONNEGATIVE])
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Worksheet(Document):
    job = models.ForeignKey(JobOrder, null=True, blank=True, on_delete=models.PROTECT)
    description = models.TextField()


class LabourEntry(models.Model):
    worksheet = models.ForeignKey(
        Worksheet, on_delete=models.PROTECT, related_name="entries"
    )
    worker = models.ForeignKey(Worker, on_delete=models.PROTECT)
    units = qty_field(validators=[POSITIVE])
    overtime_hours = qty_field(default=ZERO, validators=[NONNEGATIVE])

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["worksheet", "worker"], name="unique_worksheet_worker"
            )
        ]


class PayrollRun(Document):
    start_date = models.DateField()
    end_date = models.DateField()
    expected_days = models.PositiveIntegerField(
        default=26, validators=[MinValueValidator(1)]
    )
    total = money()


class PayrollLine(models.Model):
    run = models.ForeignKey(PayrollRun, on_delete=models.CASCADE, related_name="lines")
    worker = models.ForeignKey(Worker, on_delete=models.PROTECT)
    units = qty_field(default=ZERO)
    overtime_hours = qty_field(default=ZERO)
    base_pay = money()
    overtime_pay = money()
    allowances = money()
    deductions = money()
    advances = money()
    net_pay = money()
    salary_basis = models.CharField(max_length=10)
    rate = money()
    overtime_rate = money()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["run", "worker"], name="unique_payroll_worker"
            )
        ]


class PayrollAdjustment(models.Model):
    run = models.ForeignKey(
        PayrollRun, on_delete=models.CASCADE, related_name="adjustments"
    )
    worker = models.ForeignKey(Worker, on_delete=models.PROTECT)
    kind = models.CharField(
        max_length=12, choices=[(s, s) for s in ("allowance", "deduction")]
    )
    amount = money(validators=[MinValueValidator(Decimal("0.01"))])
    reason = models.CharField(max_length=300)


class SalaryAdvance(Document):
    worker = models.ForeignKey(Worker, on_delete=models.PROTECT)
    amount = money(validators=[MinValueValidator(Decimal("0.01"))])
    account = models.ForeignKey(PaymentAccount, on_delete=models.PROTECT)
    settled_in = models.ForeignKey(
        PayrollRun, null=True, blank=True, on_delete=models.PROTECT
    )


class SalaryPayment(Document):
    payroll_line = models.ForeignKey(
        PayrollLine, on_delete=models.PROTECT, related_name="payments"
    )
    amount = money(validators=[MinValueValidator(Decimal("0.01"))])
    account = models.ForeignKey(PaymentAccount, on_delete=models.PROTECT)
