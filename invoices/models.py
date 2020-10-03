from django.db import models
from django.contrib.auth.models import User
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
        return "<a class=\"button\" href=\"%s\">Add Invoice</a>" % reverse('invoices:index_id_csid', kwargs={"id": 0, "cs_id":pk})

    def remaining_pay(self):
        return sum(self.invoice_set.all().values_list("to_pay", flat=True)) - \
        sum(self.payment_set.all().values_list('amount', flat=True))

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
    vat_bill_no = models.CharField(null=True, blank=True, max_length=500)

    def __str__(self):
        try:
            return self.issued_for.name + " " + self.issued_by.name
        except:
            try:
                return self.issued_for.name
            except:
                return self.total
    
    


class Items(models.Model):
    density = models.FloatField(null=True, blank=True)
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

class Payment(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    amount = models.FloatField()
    payment_mode = models.IntegerField(choices=((1, "Cheque"), (2, "Cash"), (3,"Bank Transfer"), (4, "Internet Payment")))
    date = models.DateField(null=True, blank=True)

    def __str__(self):
        return "%s" % self.amount

class OpeningBalance(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    amount = models.FloatField()
    date = models.DateField()

    def __str__(self):
        return "%s : %s" % (customer, amount) 