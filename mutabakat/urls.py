from django.urls import path

from . import views

app_name = "mutabakat"

# Link müşteriye şu biçimde gider: mutabakat.basbug.com.tr/<GUID>/
urlpatterns = [
    path("", views.index, name="index"),
    path("<uuid:token>/", views.giris, name="giris"),
    path("<uuid:token>/detay/", views.detay, name="detay"),
    path("<uuid:token>/cevap/", views.cevap, name="cevap"),
    path("<uuid:token>/mektup/", views.mektup, name="mektup"),
    path("<uuid:token>/ekstre/", views.ekstre, name="ekstre"),
]
