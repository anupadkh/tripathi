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
    "ContactPerson", "Customer", "Items", "Owner", "Invoice"
    ]

class InvoiceInline(admin.TabularInline, InlineActionsMixin):
    model = apps.get_model('invoices', model_name='Invoice')
    extra = 1
    show_change_link = True
    inline_actions = ['view']
    readonly_fields = ['myview']

    def myview(self, obj):
        return mark_safe("<a href=\"/invoice/%s\"> Invoice </a>" % obj.id )
    
    def get_form(self, request, obj=None, **kwargs):
        form = super(InvoiceInline, self).get_form(request, obj, **kwargs)
        form.base_fields['user'] = request.user
        return form


    # def view(self, request, obj, parent_obj=None):
    #     url = "/hello"
    #     return redirect(url)
    # view.short_description = "Generate Items"





@admin.register(apps.get_model('invoices', model_name='Customer'))
class CustomerAdmin(admin.ModelAdmin):
    model = apps.get_model('invoices', model_name='Customer')
    ordering = ('name',)
    list_display = ['name', 'contact_person', 'phone', 'pan', 'address']
    inlines = [InvoiceInline, ]

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
