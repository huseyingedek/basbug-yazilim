from django.urls import path

from . import views

app_name = "mutabakat"

urlpatterns = [
    path("", views.index, name="index"),
    path("m/<str:token>/", views.giris, name="giris"),
    path("m/<str:token>/detay/", views.detay, name="detay"),
    path("m/<str:token>/cevap/", views.cevap, name="cevap"),
]
