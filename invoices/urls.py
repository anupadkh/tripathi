from django.urls import path

from . import views

urlpatterns=[
    path('', views.index, name="index"),
    path("invoice/<int:id>", views.index, name="index_id")
]

app_name = "invoices"