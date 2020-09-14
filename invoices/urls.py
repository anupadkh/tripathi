from django.urls import path

from . import views

urlpatterns=[
    path('', views.index, name="index"),
    path("invoice/<int:id>", views.index, name="index_id"),
    path("invoice/<int:id>/<int:cs_id>", views.index, name="index_id_csid")
]

app_name = "invoices"