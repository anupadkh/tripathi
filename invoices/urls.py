from django.urls import path

from . import views

urlpatterns=[
    path('', views.index, name="index"),
    path("invoice/<int:id>", views.index, name="index_id"),
    path("invoice/<int:id>/<int:cs_id>", views.index, name="index_id_csid"),
    path("invoice/<int:id>/term", views.customer_details, name="customer_term"),
    path("invoice/customer/<int:id>/term/<int:term>", views.monthly_details, name="term_details"),
    path("invoice/term/<int:term>", views.term_monthly_details, name="term_monthly_details"),
    path("invoice/<int:id>/term/vat/<int:vat>", views.customer_details, name="vat_customer_term"),
    path("invoice/customer/<int:id>/term/<int:term>/vat/<int:vat>", views.monthly_details, name="vat_term_details"),
    path("invoice/term/<int:term>/vat/<int:vat>", views.term_monthly_details, name="vat_term_monthly_details"),
    
]

app_name = "invoices"