from django.db import models
from django.contrib.auth.models import User
# from nepali_date.date import NepaliDate
import nepali_datetime as NepDate
from django.db.models import CheckConstraint, Q, F
from django.urls import reverse
from decimal import Decimal
# Create your models here.

class ContactPerson(models.Model):
    name = models.CharField(max_length=300)
    phone = models.IntegerField(null=True, blank=True)
    address = models.CharField(max_length=300, null=True, blank=True)

    def __str__(self):
        return self.name

class CustomerMeta(models.Model):
    name = models.CharField(max_length=300, null=True, blank=True)
    address = models.CharField(max_length=300, null=True, blank=True)
    phone = models.IntegerField(null=True, blank=True)
    pan = models.IntegerField(null=True, blank=True)
    contact_person = models.ForeignKey(ContactPerson, null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return self.name


    class Meta:
        abstract = True

class Customer(CustomerMeta):

    def addInvoice(self):
        return "<a class=\"button\" href=\"%s\" target='_blank'>Add Invoice</a>" % reverse('invoices:index_id_csid', kwargs={"id": 0, "cs_id":self.pk})

    # @property
    def remaining_pay(self):
        try:
            return round(
                sum(self.invoice_set.all().values_list("to_pay", flat=True)) - \
                sum(self.payment_set.all().values_list('amount', flat=True)) + \
                self.openingbalance_set.all().prefetch_related('term').order_by('term__start_date')[0].amount,
            2)
                # sum(self.openingbalance_set.all().values_list('amount', flat=True))
        except:
            return round(
                sum(self.invoice_set.all().values_list("to_pay", flat=True)) - \
                sum(self.payment_set.all().values_list('amount', flat=True)),
            2)

    @property
    def arthik_barsa(self):
        try:
            return self.openingbalance_set.all().prefetch_related('term').order_by('-term__start_date')[0].term
        except:
            return None

    def arthik_remaining_pay(self, end_date=None):
        try:
            open_bal = self.openingbalance_set.all().prefetch_related('term').order_by('-term__start_date')[0]
            if end_date:
                exp = Q(date__gte=open_bal.term.start_date) & Q(date__lte=end_date)
            else:
                exp = Q(date__gte=open_bal.term.start_date)
            return round(
                sum(self.invoice_set.filter(exp).values_list("to_pay", flat=True)) - \
                sum(self.payment_set.filter(exp).filter(
                Q(term__isnull=True) | Q(term = open_bal.term.id)
                ).values_list('amount', flat=True)) + \
                open_bal.amount,
            2)
        except:
            if end_date:
                exp = Q(date__lte=end_date)
            else:
                exp = Q()
            return round(
                sum(self.invoice_set.filter(exp).values_list("to_pay", flat=True)) - \
                sum(self.payment_set.filter(exp).values_list('amount', flat=True)),
            2)

    @property
    def arthik_pending(self):
        return 'NPR {:,.2f}'.format(self.arthik_remaining_pay(),)

    @property
    def pay_due(self):
        return 'NPR {:,.2f}'.format(self.remaining_pay(),)


class Invoice(models.Model):
    issued_for = models.ForeignKey(Customer, on_delete=models.PROTECT, null=True, blank=True)
    issued_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    is_posted = models.BooleanField(default=False)
    total = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    tax = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    paid_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, default=0)
    date = models.DateField(null=True, blank=True)
    to_pay = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, default=0)
    discount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, default=0)
    notes = models.TextField(blank=True, null=True)
    vat_bill_no = models.CharField( verbose_name="Bill No" ,null=True, blank=True, max_length=500)
    is_vat = models.BooleanField(default=False)
    status = models.CharField(max_length=12, default='draft', choices=[(s, s) for s in ('draft', 'grouped', 'posted', 'cancelled')])
    source = models.CharField(max_length=12, default='legacy', editable=False)
    revision = models.PositiveIntegerField(default=1)
    fiscal_year = models.ForeignKey('Term', null=True, blank=True, on_delete=models.PROTECT)
    number = models.CharField(max_length=80, null=True, blank=True, unique=True)
    vat_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('13.00'))
    cancellation_reason = models.TextField(blank=True, default='')
    credit_bank_name = models.CharField(max_length=100, blank=True, default='')

    def __str__(self):
        try:
            return self.issued_for.name + " " + self.issued_by.name
        except:
            try:
                return self.issued_for.name
            except:
                return self.total

    def save(self, *args, **kwargs):
        if self.source == 'legacy':
            if self._state.adding or not self.is_posted:
                self.is_vat = bool(self.vat_bill_no and self.vat_bill_no.strip())
            if self.is_posted and self.status != 'cancelled':
                self.status = 'posted'
        super(Invoice, self).save(*args, **kwargs)



class Items(models.Model):
    density = models.CharField(null=True, blank=True, max_length=30)
    length = models.FloatField(null=True, blank=True)
    breadth =models.FloatField(null=True, blank=True)
    height = models.FloatField(null=True, blank=True)
    mm = models.FloatField(null=True, blank=True)
    rate = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    calculated_rate = models.DecimalField(max_digits=18, decimal_places=4)
    qty = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    price = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    unit = models.CharField(max_length=20, default='piece')
    taxable = models.BooleanField()
    tax_include = models.BooleanField()
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE)

class Owner(CustomerMeta):
    info = models.CharField(max_length=100, null=True, blank=True)
    email = models.EmailField(null=True, blank=True)

class UserSystem(models.Model):
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True)
    owner = models.ForeignKey(Owner, on_delete=models.SET_NULL, null=True)
    default_term = models.IntegerField(
        choices=((0, "Yes"), (1, "No")), default = 0
    )
    billing_term = models.ForeignKey('invoices.Term', on_delete=models.SET_NULL, null=True, blank=True)

class Payment(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    payment_mode = models.IntegerField(choices=((1, "Cheque"), (2, "Cash"), (3,"Bank Transfer"), (4, "Internet Payment"), (5, "Transport"), (6, "Bank Deposit"), (7, "Goods Returned"), (8, "Discount")))
    date = models.DateField(null=True, blank=True)
    nepali_date = models.CharField(blank=True, max_length=20, default="")
    term = models.ForeignKey("Term", on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return "%s" % self.amount

    def save(self, *args, **kwargs):
        if self.nepali_date != "":
            # self.date = NepaliDate.to_english_date(NepaliDate(*self.nepali_date.split('-')))
            self.date = NepDate.date.to_datetime_date(NepDate.date(*tuple([int(x) for x in self.nepali_date.split('-')])))
        super(Payment, self).save(*args, **kwargs)

class Term(models.Model):
    start_date = models.DateField()
    end_date = models.DateField()
    title = models.CharField(max_length=300)

    def __str__(self):
        return self.title


    class Meta:
        constraints = [
            CheckConstraint(
                check = Q(end_date__gt=F('start_date')),
                name = 'check_start_date',
            ),
        ]

class OpeningBalance(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    amount = models.DecimalField("Opening Balance", max_digits=18, decimal_places=2)
    term = models.ForeignKey(Term, on_delete=models.CASCADE)


    def __str__(self):
        return "%s : %s" % (self.customer.name, self.amount)

    def save(self, *args, **kwargs):
        if self.id:
            super(OpeningBalance, self).save(*args, **kwargs)
        else:
            if self.amount == 0:
                self.amount = self.customer.remaining_pay()
            super(OpeningBalance, self).save(*args, **kwargs)

    class Meta:
        unique_together=('customer', 'term')

    @property
    def term_start(self):
        return self.term.start_date

    @property
    def term_end(self):
        return self.term.end_date

    def invoices(self):
        return self.customer.invoice_set.filter(
                date__range=[self.term.start_date, self.term.end_date]
            )

    def payments(self):
        return self.customer.payment_set.filter(
                (Q(date__range=[self.term.start_date, self.term.end_date]) & Q(term__isnull = True)) | Q(term = self.term)
            )



    @property
    def closing_due(self):
        return sum(self.customer.invoice_set.filter(
                date__range=[self.term.start_date, self.term.end_date]
            ).values_list("to_pay", flat=True)) - \
            sum(self.customer.payment_set.filter(
                (Q(date__range=[self.term.start_date, self.term.end_date]) & Q(term__isnull = True)) | Q(term = self.term)
            ).values_list('amount', flat=True)) + \
            self.amount

    @property
    def total_sales(self):
        return sum(self.customer.invoice_set.filter(
                date__range=[self.term.start_date, self.term.end_date]
            ).filter(is_vat=False).values_list("to_pay", flat=True))

    @property
    def total_vat_sales(self):
        return sum(self.customer.invoice_set.filter(
                date__range=[self.term.start_date, self.term.end_date]
            ).filter(is_vat=True).values_list("to_pay", flat=True))

    @property
    def total_pay(self):
        return sum(self.customer.payment_set.filter(
            (Q(date__range=[self.term.start_date, self.term.end_date]) & Q(term__isnull = True)) | Q(term = self.term)
        ).values_list('amount', flat=True))

    def payments_until(self, end_date):
        return self.customer.payment_set.filter(
            (Q(date__range=[self.term.start_date, end_date]) & Q(term__isnull = True)) | Q(term = self.term)
        ).values_list('amount', flat=True)

    def sales_until(self, end_date):
        return self.customer.invoice_set.filter(
                date__range=[self.term.start_date, end_date]
            ).values_list("to_pay", flat=True)

class InvoiceCounter(models.Model):
    term = models.ForeignKey(Term, on_delete=models.CASCADE)
    count = models.IntegerField(default=0)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['term'], name='unique_invoice_counter_term'),
        ]

class InvNum(models.Model):
    invoice = models.OneToOneField(Invoice, on_delete = models.CASCADE)
    num = models.IntegerField(default=0)


    class Meta:
        verbose_name = "Invoice Number"
