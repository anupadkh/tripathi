from django.shortcuts import render

from .models import *
from .serializer import *
import json
# Create your views here.

def sanitize_floats(x):
    if type(x) == str:
        return float(x)
    else:
        return x

def index(request, id=None, cs_id=None):
    if id==0 :
        customer = Customer.objects.get(id=cs_id)
        invoice = Invoice(issued_for=customer)
        if request.method=="POST":
            invoice.save()
            id = invoice.id
    else:
        invoice = Invoice.objects.get(id=id)
    if cs_id:
        customer = Customer.objects.get(id=cs_id)
    else:
        customer = invoice.issued_for
    user = request.user
    try:
        owner = Owner.objects.get(usersystem__user = user)
    except:
        owner = None

    items = Items.objects.filter(invoice=invoice)
    context = {
        "id" : id,
        "invoice": invoice,
        "user": user,
        "owner": owner,
        "items": items,
        "customer" : customer,
        "unsaved": True,
        "due" : round(customer.arthik_remaining_pay, 2)
        }
    if request.method == "POST":
        data = request.POST
        items_post = json.loads(data['items'])
        invoiceDetails = json.loads(data['invoice'])
        invoice.issued_by = user
        try:
            invoice.total = invoiceDetails['total']
            invoice.tax = invoiceDetails['tax']
            invoice.paid_amount = invoiceDetails['paid']
            invoice.date = invoiceDetails['date']
            invoice.discount = invoiceDetails['discount']
            invoice.to_pay = invoiceDetails['to_pay']
            invoice.notes = invoiceDetails['notes']
            invoice.is_posted = True
            invoice.vat_bill_no = invoiceDetails['vat']
            invoice.save()
            invoice = Invoice.objects.get(id=invoice.id)
        except:
            context["errors"]= "Error in Details of Invoice"
            return(request, 'invoice/index.html', context)

        already_saved_ids = items.values_list('id', flat=True)
        saved_items_id = []
        for posted_item in items_post:
            posted_item['invoice'] = invoice.id
            if posted_item['id'] == "":
                item_save = ItemSerializer(data=posted_item)
            else:
                item_saved = Items.objects.get(id=posted_item["id"])
                item_save = ItemSerializer(instance=item_saved, data=posted_item)
            if item_save.is_valid():
                item_saved = item_save.save()
            else:
                context.update({
                        "errors":"Error in Item " + posted_item['description']
                    })
                return(request, 'invoice/index.html', context)

            saved_items_id.append(item_saved.id)

        to_delete = list(
            set(already_saved_ids) - set(saved_items_id)
        )
        Items.objects.filter(id__in = to_delete).delete()
        items = Items.objects.filter(invoice=invoice)
        context = {
        "id" : id,
        "invoice": invoice,
        "user": user,
        "owner": owner,
        "items": items,
        "customer" : customer,
        "unsaved": False,
        "due" : customer.remaining_pay()
        }
        return render(request, 'invoice/index.html', context)






    return render(request, 'invoice/index.html', context)

def customer_details(request,id):
    openBal = OpeningBalance.objects.get(id=id)


    context = {
        "title": "%s-%s" %(openBal.customer.name , openBal.term.title),
        "invoices": openBal.invoices,
        "payments": openBal.payments,
        "opening": openBal
    }
    return render (request, 'invoice/customer_details.html', context=context)
