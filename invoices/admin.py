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



allowed_list = [
    "ContactPerson", "Customer", "Owner"
    ]

class PaymentInline(admin.TabularInline):
    model = apps.get_model('invoices', model_name='Payment')
    extra = 1
    show_change_link = True
    ordering = ('-date',)

class InvoiceInline(admin.TabularInline, InlineActionsMixin):
    model = apps.get_model('invoices', model_name='Invoice')
    fields = ('Invoice','is_posted', 'to_pay', 'total', 'tax', 'paid_amount', 'date', 'vat_bill_no')
    extra = 1
    show_change_link = True
    inline_actions = ['view']
    readonly_fields = ['Invoice']
    ordering = ('-date',)

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


    # def view(self, request, obj, parent_obj=None):
    #     url = "/hello"
    #     return redirect(url)
    # view.short_description = "Generate Items"

class OpeningInline(admin.TabularInline):
    model = apps.get_model('invoices', model_name='OpeningBalance')
    # fields = '__all__'
    extra = 0
    ordering=('-date',)



@admin.register(apps.get_model('invoices', model_name='Customer'))
class CustomerAdmin(admin.ModelAdmin):
    model = apps.get_model('invoices', model_name='Customer')
    ordering = ('name',)
    list_display = ['name', 'contact_person', 'phone', 'pan', 'address', 'remaining_pay']
    inlines = [InvoiceInline, PaymentInline, OpeningInline]
    readonly_fields = ('addInvoice',)
    search_fields = ('name',)
    fieldsets = (
        (None,
            { "fields": ('name', )}
        ), 
        ("Other Details", 
            {   
            'classes': ('collapse',),
            "fields": ("contact_person", "phone", "pan", "address", )
            }
        )
    )

    def addInvoice(self, obj):
        return reverse('invoices:index_id_csid', kwargs={"id": 0, "cs_id":obj.id})


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
