from django.db import models
from django.contrib.auth.models import User
from nepali_date.date import NepaliDate
from django.db.models import Q
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
        return "<a class=\"button\" href=\"%s\" target='_blank'>Add Invoice</a>" % reverse('invoices:index_id_csid', kwargs={"id": 0, "cs_id":pk})

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
    def arthik_remaining_pay(self):
        try:
            open_bal = self.openingbalance_set.all().prefetch_related('term').order_by('-term__start_date')[0]
            return round(
                sum(self.invoice_set.filter(date__gte = open_bal.term.start_date).values_list("to_pay", flat=True)) - \
                sum(self.payment_set.filter(date__gte = open_bal.term.start_date).filter(
                Q(term__isnull=True) | Q(term = open_bal.term.id)
                ).values_list('amount', flat=True)) + \
                open_bal.amount,
            2)
        except:
            return round(
                sum(self.invoice_set.all().values_list("to_pay", flat=True)) - \
                sum(self.payment_set.all().values_list('amount', flat=True)),
            2)


class Invoice(models.Model):
    issued_for = models.ForeignKey(Customer, on_delete=models.CASCADE, null=True, blank=True)
    issued_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    is_posted = models.BooleanField(default=False)
    total = models.FloatField(null=True, blank=True)
    tax = models.FloatField(null=True, blank=True)
    paid_amount = models.FloatField(null=True, blank=True, default=0)
    date = models.DateField(null=True, blank=True)
    to_pay = models.FloatField(null=True, blank=True, default=0)
    discount = models.FloatField(null=True, blank=True, default=0)
    notes = models.TextField(blank=True, null=True)
    vat_bill_no = models.CharField( verbose_name="Bill No" ,null=True, blank=True, max_length=500)
    is_vat = models.BooleanField(default=False)

    def __str__(self):
        try:
            return self.issued_for.name + " " + self.issued_by.name
        except:
            try:
                return self.issued_for.name
            except:
                return self.total




class Items(models.Model):
    density = models.CharField(null=True, blank=True, max_length=30)
    length = models.FloatField(null=True, blank=True)
    breadth =models.FloatField(null=True, blank=True)
    height = models.FloatField(null=True, blank=True)
    mm = models.FloatField(null=True, blank=True)
    rate = models.FloatField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    calculated_rate = models.FloatField()
    qty = models.FloatField(null=True, blank=True)
    price = models.FloatField(null=True, blank=True)
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

class Payment(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    amount = models.FloatField()
    payment_mode = models.IntegerField(choices=((1, "Cheque"), (2, "Cash"), (3,"Bank Transfer"), (4, "Internet Payment"), (5, "Transport"), (6, "Bank Deposit"), (7, "Goods Returned"), (8, "Discount")))
    date = models.DateField(null=True, blank=True)
    nepali_date = models.CharField(blank=True, max_length=20, default="")
    term = models.ForeignKey("Term", on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return "%s" % self.amount

    def save(self, *args, **kwargs):
        if self.nepali_date != "":
            self.date = NepaliDate.to_english_date(NepaliDate(*self.nepali_date.split('-')))
        super(Payment, self).save(*args, **kwargs)

class Term(models.Model):
    start_date = models.DateField()
    end_date = models.DateField()
    title = models.CharField(max_length=300)

    def __str__(self):
        return self.title

class OpeningBalance(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    amount = models.FloatField("Opening Balance",) # blank=True, null=True)
    term = models.ForeignKey(Term, on_delete=models.CASCADE)


    def __str__(self):
        return "%s : %s" % (self.customer.name, self.amount)

    # def save(self, *args, **kwargs):
    #     if self.amount == NULL  :
    #         if ('amount' in kwargs ) & kwargs['amount'] == NULL:
    #             self.amount = self.customer.remaining_pay()
    #
    #
    #     super(OpeningBalance, self).save(*args, **kwargs)

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
                date__range=[self.term.start_date, self.term.end_date]
            ).values_list('amount', flat=True)) + \
            self.amount

    @property
    def total_sales(self):
        return sum(self.customer.invoice_set.filter(
                date__range=[self.term.start_date, self.term.end_date]
            ).values_list("to_pay", flat=True))

    @property
    def total_pay(self):
        return sum(self.customer.payment_set.filter(
            date__range=[self.term.start_date, self.term.end_date]
        ).values_list('amount', flat=True))
