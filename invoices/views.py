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


from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponseBadRequest, HttpResponseForbidden
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from .services import save_legacy_invoice

@login_required
def index(request, id=None, cs_id=None):
    if id == 0 and cs_id:
        if not request.user.has_perm('invoices.add_invoice'):
            return HttpResponseForbidden('Invoice creation permission is required.')
        customer = Customer.objects.get(pk=cs_id)
        invoice = Invoice(issued_for=customer)
    elif id:
        invoice = Invoice.objects.select_related('issued_for').get(pk=id)
        customer = invoice.issued_for
        if not request.user.has_perm('invoices.view_invoice'):
            return HttpResponseForbidden('Invoice viewing permission is required.')
    else:
        return HttpResponseBadRequest('Choose a customer or an invoice from the admin.')
    if invoice.source == 'api':
        return HttpResponseForbidden('Use the desktop/API to view this invoice; the legacy form uses different quantity calculations.')
    user_system = UserSystem.objects.filter(user=request.user).first()
    year = invoice.fiscal_year or (user_system.billing_term if user_system else None)
    if request.method == 'POST':
        permission = 'invoices.change_invoice' if invoice.pk else 'invoices.add_invoice'
        if not request.user.has_perm(permission):
            return HttpResponseForbidden('Invoice write permission is required.')
        try:
            invoice = save_legacy_invoice(invoice, year, request.user, json.loads(request.POST['items']), json.loads(request.POST['invoice']))
        except (ValidationError, ValueError, KeyError) as error:
            return HttpResponseBadRequest(str(error))
    invnum = InvNum.objects.filter(invoice=invoice).first() if invoice.pk else None
    owner = Owner.objects.filter(usersystem__user=request.user).first()
    context = {'inv_no': invnum.num if invnum else 'Draft', 'id': invoice.pk or 0, 'invoice': invoice, 'user': request.user, 'owner': owner, 'items': invoice.items_set.all() if invoice.pk else [], 'customer': customer, 'unsaved': not invoice.is_posted, 'due': customer.arthik_remaining_pay(end_date=invoice.date)}
    bill_date = invoice.date or timezone.localdate()
    context['bill_date_ad'] = bill_date.isoformat()
    context['bill_date_bs'] = NepDate.date.from_datetime_date(bill_date).isoformat()
    return render(request, 'invoice/index.html', context)

@login_required
@permission_required(('invoices.view_invoice','invoices.view_payment','invoices.view_openingbalance'),raise_exception=True)
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


@login_required
@permission_required(('invoices.view_invoice','invoices.view_payment','invoices.view_openingbalance'),raise_exception=True)
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
        month_days = int(year_calendar.iloc[current_month-1])
        prev_month_days = int(year_calendar.iloc[prev_month-1])

        start_day = NepDate.date(prev_year, prev_month, prev_month_days).to_datetime_date()
        end_day = NepDate.date(current_year, current_month, month_days).to_datetime_date()
        opening_dates.append(start_day)
        monthly_opening = opening.amount + sum(opening.sales_until(start_day)) - sum(opening.payments_until(start_day))
        monthly_invoices = Invoice.objects.filter(status='posted').filter(
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


@login_required
@permission_required(('invoices.view_invoice','invoices.view_payment','invoices.view_openingbalance'),raise_exception=True)
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
        month_days = int(year_calendar.iloc[current_month-1])
        prev_month_days = int(year_calendar.iloc[prev_month-1])

        start_day = NepDate.date(current_year, current_month, 1).to_datetime_date()
        end_day = NepDate.date(current_year, current_month, month_days).to_datetime_date()
        opening_dates.append(start_day)
        monthly_invoices = Invoice.objects.filter(status='posted').filter(
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
