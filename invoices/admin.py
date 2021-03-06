from django.apps import apps
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.conf import settings
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin, GroupAdmin as BaseGroupAdmin
from django.contrib.auth.models import User, Group
from inline_actions.admin import InlineActionsMixin
from django.shortcuts import redirect
from django.utils.translation import ugettext_lazy as _
from django.utils.safestring import mark_safe
from nepali_date.date import NepaliDate


allowed_list = [
    "ContactPerson", "Customer", "Owner"
    ]

class PaymentInline(admin.TabularInline):
    model = apps.get_model('invoices', model_name='Payment')
    extra = 1
    show_change_link = True
    ordering = ('-date',)
    classes = ["tab-payment-inline", "collapse"]
    fields = ['nepali_date', 'amount', 'payment_mode', 'nep_date', 'date']
    readonly_fields = ['nep_date',]

    def nep_date(self, obj):
        try:
            # valid_dob = (self.date.split('-'))
            return NepaliDate.to_nepali_date(obj.date)
        except:
            return '-'
        return

class InvoiceInline(admin.TabularInline, InlineActionsMixin):
    model = apps.get_model('invoices', model_name='Invoice')
    fields = ('Invoice','nep_date','is_posted', 'to_pay', 'total', 'tax', 'vat_bill_no', 'is_vat')
    extra = 1
    show_change_link = True
    inline_actions = ['view']
    readonly_fields = ['Invoice', 'nep_date']
    ordering = ('-date',)
    classes = ["tab-invoice-inline","collapse"]

    def url(self,obj):
        if obj.id:
            return reverse('invoices:index_id', kwargs={"id": obj.id})
        else:
            return reverse('invoices:index_id_csid', kwargs={"id": 0, "cs_id":obj.issued_for.id})

    def Invoice(self, obj):
        return mark_safe("<a href=\"%s\"> View </a>" % self.url(obj) )

    def get_form(self, request, obj=None, **kwargs):
        form = super(InvoiceInline, self).get_form(request, obj, **kwargs)
        form.base_fields['user'] = request.user
        return form

    def nep_date(self, obj):
        try:
            # valid_dob = (self.date.split('-'))
            return NepaliDate.to_nepali_date(obj.date)
        except:
            return '-'
        return


    # def view(self, request, obj, parent_obj=None):
    #     url = "/hello"
    #     return redirect(url)
    # view.short_description = "Generate Items"

class OpeningInline(admin.TabularInline):
    model = apps.get_model('invoices', model_name='OpeningBalance')
    # fields = '__all__'
    extra = 0
    classes = ["tab-opening-inline", "collapse"]
    show_change_link = True



@admin.register(apps.get_model('invoices', model_name='Customer'))
class CustomerAdmin(admin.ModelAdmin):
    model = apps.get_model('invoices', model_name='Customer')
    ordering = ('name',)
    list_display = ['name', 'contact_person', 'phone', 'pan', 'address', 'remaining_pay']
    inlines = [InvoiceInline, PaymentInline, OpeningInline]
    readonly_fields = ('addInvoice', )
    search_fields = ('name','address', 'phone','pan')
    classes = ('extrapretty',)
    admin_order_field = ('remaining_pay',)
    fieldsets = (
        (None,
            { "fields": ('name', 'addInvoice' ),
            "classes": ["tab-basic",],}
        ),
        ("Other Details",
            {
            'classes': ('collapse', "other"),
            "fields": ("contact_person", "phone", "pan", "address", )
            }
        )
    )
    save_on_top = True
    tabs = [
        ("Payment", ["tab-payment-inline",]),
        ("Invoices", ["tab-invoice-inline",]),
        ("Opening", ["tab-opening-inline",]),
        ("Basic Info", ["tab-basic", "other"])
    ]


    def addInvoice(self, obj):
        try:
            return format_html("<a class='button' href='%s'>Add New Invoice</a>" % reverse('invoices:index_id_csid', kwargs={"id": 0, "cs_id":obj.id}))
        except:
            return "Save the customer first"


# Register your models here.
from .models import *
from django.apps import apps
admin.site.unregister(User)

class UserTypeInline( admin.StackedInline ):
    model = apps.get_model('invoices', model_name="UserSystem")

class UserAdmin(BaseUserAdmin):
    inlines=(UserTypeInline, )
    extra = 1

admin.site.register(User, UserAdmin)

for x in apps.get_models():
    # if 'User' in str(x):
    #     continue
    # if 'viewflow' in str(x):
    #     admin.site.unregister(x)


        for r in allowed_list:
            if r in str(x):
                try:
                    admin.site.register(x)
                except:
                    pass



@admin.register(apps.get_model('invoices', model_name='Term'))
class TermAdmin(admin.ModelAdmin):
    list_display = ['title','start_date', 'end_date', 'total_due', 'total_sales' ]
    readonly_fields = ('total_due', 'total_sales')

    def total_due(self, obj):
        balances = OpeningBalance.objects.filter(term=obj)
        total_due_amount = 0
        for x in balances:
            total_due_amount += x.closing_due
        return "NPR {:,.2f}".format(total_due_amount)

    def total_sales(self,obj):
        balances = OpeningBalance.objects.filter(term=obj)
        total_sales_amount = 0
        for x in balances:
            total_sales_amount += x.total_sales
        return "NPR {:,.2f}".format(total_sales_amount)



@admin.register(apps.get_model('invoices', model_name='OpeningBalance'))
class OpeningAdmin(admin.ModelAdmin):
    list_display = ['customer', 'closing_due', 'term']
    readonly_fields = [ 'closing_due', 'term_start', 'term_end', 'print_statement']
    list_filter = ['customer', 'term']
    search_fields = ('customer__name',)


    def print_statement(self,obj):
        return format_html("<a href='%s' target='_blank' class='button'>Open Statement</a>" % reverse('invoices:customer_term', kwargs= {"id":obj.id}))
