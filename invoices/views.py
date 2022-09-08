from django.shortcuts import render
import nepali_datetime
from .models import *
from .serializer import *
import json
# from nepali_date import NepaliDate
import nepali_datetime as NepDate
import pandas as pd

"""
inv_no = Invoice Counter
invoice_no = Invoice Number
"""
def sanitize_floats(x):
    if type(x) == str:
        return float(x)
    else:
        return x


def index(request, id=None, cs_id=None):
    # Set the counters
    inv_no, status = InvoiceCounter.objects.get_or_create(term=request.user.usersystem.billing_term)
    invoice_no = InvNum()
    invoice_no.num = inv_no.count + 1

    if id==0 :
        customer = Customer.objects.get(id=cs_id)
        invoice = Invoice(issued_for=customer)
        due = round(customer.arthik_remaining_pay(end_date=invoice.date), 2)


        if request.method=="POST":
            invoice.save()
            id = invoice.id
            inv_no.count += 1
            inv_no.save()
            invoice_no, status = InvNum.objects.get_or_create(invoice=invoice)
            invoice_no.num = inv_no.count
            invoice_no.save()


    else:
        invoice = Invoice.objects.get(id=id)
        customer = invoice.issued_for
        due = round(customer.arthik_remaining_pay(end_date=invoice.date), 2)
        invoice_no, status = InvNum.objects.get_or_create(invoice=invoice)
        if status: # For Old Invoices
            invoice_no.num = invoice.id
            invoice_no.save()
            inv_no.count += 1
            inv_no.save()
    if cs_id:
        customer = Customer.objects.get(id=cs_id)
        due = round(customer.arthik_remaining_pay(end_date=None), 2)
    else:
        customer = invoice.issued_for
    user = request.user
    try:
        owner = Owner.objects.get(usersystem__user = user)
    except:
        owner = None

    items = Items.objects.filter(invoice=invoice)
    context = {
        "inv_no": invoice_no.num ,
        "id" : id,
        "invoice": invoice,
        "user": user,
        "owner": owner,
        "items": items,
        "customer" : customer,
        "unsaved": True,
        "due" : due
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
            invoice.notes = invoiceDetails['notes']
            invoice.is_posted = True
            invoice.vat_bill_no = invoiceDetails['vat']
            invoice.to_pay = invoiceDetails['to_pay']
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
                        "errors":"Error in Item " + posted_item['description'],
                        "invoice": invoice,
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
        "due" : due,
        "inv_no": invoice_no.num ,
        }
        return render(request, 'invoice/index.html', context)

    return render(request, 'invoice/index.html', context)


def customer_details(request,id, vat=False):
    openBal = OpeningBalance.objects.get(id=id)


    context = {
        "title": "%s-%s" %(openBal.customer.name , openBal.term.title),
        "invoices": openBal.invoices().filter(is_vat=vat),
        "payments": openBal.payments,
        "opening": openBal,
        "vat": vat
    }
    if vat:
        context['payments'] = []
        openBal.amount = 0
    else:
        context['invoices'] = openBal.invoices()
    return render (request, 'invoice/customer_details.html', context=context)


def monthly_details(request, id, term, vat=False):
    customer = Customer.objects.get(id =id)
    opening = OpeningBalance.objects.get(term__id = term, customer = customer)
    nep_start = NepDate.date.from_datetime_date(opening.term.start_date)
    nep_end = NepDate.date.from_datetime_date(opening.term.end_date)
    if NepDate.date.today()< nep_end:
        nep_end = NepDate.date.today()
    all_calendar = pd.read_csv(nepali_datetime.calendar_file.name, index_col = 0)

    current_year = int(nep_start.year)
    current_month = int(nep_start.month)
    i = True
    titles = []
    openings = []
    sales = []
    payments = []
    id_tags = []
    opening_dates = []

    while (i):
        if current_month == 1:
            prev_month = 12
            prev_year = current_year - 1
        else:
            prev_month = current_month - 1
            prev_year = current_year


        year_calendar = all_calendar.loc[current_year]
        titles.append('%s:%s' % (current_year, year_calendar.index[current_month-1]))
        month_days = int(year_calendar[current_month-1])
        prev_month_days = int(year_calendar[prev_month-1])

        start_day = NepDate.date(prev_year, prev_month, prev_month_days).to_datetime_date()
        end_day = NepDate.date(current_year, current_month, month_days).to_datetime_date()
        opening_dates.append(start_day)
        monthly_opening = opening.amount + sum(opening.sales_until(start_day)) - sum(opening.payments_until(start_day))
        monthly_invoices = Invoice.objects.filter(
            Q(date__gte = start_day) & Q(date__lte = end_day) & Q(issued_for=customer)
        )
        if vat:
            monthly_invoices = monthly_invoices.filter(is_vat=vat)
        monthly_payments = Payment.objects.filter(
            Q(date__gte=start_day) & Q(date__lte=end_day) & Q(Q(term__isnull=True) | Q(term__id=term)) & Q(customer=customer)
        )

        i, current_month, current_year = update_loop(i, current_month, current_year, nep_end)
        sales.append(monthly_invoices)
        if vat:
            payments.append([])
            openings.append(0)
        else:
            payments.append(monthly_payments)
            openings.append(monthly_opening)
        id_tags.append('%s%s'%(current_year, current_month))

    context = {
        'page_title': customer.name,
        'titles':titles, 'openings': openings, 'sales': sales, 'debits':payments, 'ids': id_tags,
        # 'titles_ids': zip(titles, id_tags),
        'accounts': zip(id_tags, openings, opening_dates, sales, payments, titles),
        "vat": vat
    }
    return render(request, 'invoice/monthly_details.html', context=context)


def update_loop(i, current_month, current_year, nep_end):
    if (current_year == nep_end.year) & (current_month == nep_end.month):
        i = False
    if current_month == 12:
        current_month = 1
        current_year += 1
    else:
        current_month += 1
    return i, current_month, current_year


def term_monthly_details(request, term, vat=False):
    opening_bals = OpeningBalance.objects.filter(term__id = term)
    opening_term = Term.objects.get(id=term)
    monthly_opening = sum(opening_bals.values_list('amount', flat=True))
    nep_start = NepDate.date.from_datetime_date(opening_term.start_date)
    nep_end = NepDate.date.from_datetime_date(opening_term.end_date)
    if NepDate.date.today()< nep_end:
        nep_end = NepDate.date.today()
    all_calendar = pd.read_csv(nepali_datetime.calendar_file.name, index_col = 0)

    current_year = int(nep_start.year)
    current_month = int(nep_start.month)
    i = True
    titles = []
    openings = []
    sales = []
    payments = []
    id_tags = []
    opening_dates = []
    cash_payments = []

    while (i):
        if current_month == 1:
            prev_month = 12
            prev_year = current_year - 1
        else:
            prev_month = current_month - 1
            prev_year = current_year


        year_calendar = all_calendar.loc[current_year]
        titles.append('%s:%s' % (current_year, year_calendar.index[current_month-1]))
        month_days = int(year_calendar[current_month-1])
        prev_month_days = int(year_calendar[prev_month-1])

        start_day = NepDate.date(current_year, current_month, 1).to_datetime_date()
        end_day = NepDate.date(current_year, current_month, month_days).to_datetime_date()
        opening_dates.append(start_day)
        monthly_invoices = Invoice.objects.filter(
            Q(date__gte = start_day) & Q(date__lte = end_day)
        ).prefetch_related('issued_for')
        monthly_payments = Payment.objects.filter(
            Q(date__gte=start_day) & Q(date__lte=end_day) & Q(Q(term__isnull=True) | Q(term__id=term))
        ).prefetch_related('customer')

        i, current_month, current_year = update_loop(i, current_month, current_year, nep_end)
        if vat:
            monthly_invoices = monthly_invoices.filter(is_vat=vat)
            payments.append([])
            monthly_opening = 0
            openings.append(0)
        else:
            payments.append(monthly_payments)
            openings.append(monthly_opening)
            monthly_opening += sum(monthly_invoices.values_list('total', flat=True)) - sum(monthly_payments.values_list('amount', flat=True)) - sum(monthly_invoices.values_list('paid_amount', flat=True))
        sales.append(monthly_invoices)

        id_tags.append('%s%s'%(current_year, current_month))
        cash_payments.append({'amount':sum(monthly_invoices.values_list('paid_amount', flat=True)), 'date': end_day})

    context = {
        'page_title': "Monthly Summary",
        'titles':titles, 'openings': openings, 'sales': sales, 'debits':payments, 'ids': id_tags,
        'titles_ids': zip(titles, id_tags),
        'accounts': zip(id_tags, openings, opening_dates, sales, payments, titles, cash_payments),
        "vat": vat
    }
    return render(request, 'invoice/monthly_details_term.html', context=context)
