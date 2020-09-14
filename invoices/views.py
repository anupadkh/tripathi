from django.shortcuts import render

from .models import *
from .serializer import *
import json
# Create your views here.

def index(request, id=None):
    invoice = Invoice.objects.get(id=id)
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
        "unsaved": True
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
            invoice.save()
            invoice = Invoice.objects.get(id=invoice.id)
        except:
            context.update({"errors": "Error in Details of Invoice"})
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
        "unsaved": False
        }
        return render(request, 'invoice/index.html', context)
        

            
            
        

    return render(request, 'invoice/index.html', context)

