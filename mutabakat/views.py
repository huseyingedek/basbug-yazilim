from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render

from .forms import CevapForm, SifreForm
from .services import get_kayit, gonder_cevap, sifre_dogru


def _session_key(token):
    return f"mutabakat_ok_{token}"


def _girisli_mi(request, token):
    return bool(request.session.get(_session_key(token)))


# --------------------------------------------------------------------------- #
# Giriş (login) — maildeki link + şifre
# --------------------------------------------------------------------------- #
def _sifre_ekrani(request, token):
    hata = None
    if request.method == "POST":
        form = SifreForm(request.POST)
        if form.is_valid():
            if sifre_dogru(token, form.cleaned_data["sifre"]):
                request.session[_session_key(token)] = True
                return redirect("mutabakat:detay", token=token)
            hata = "Şifre hatalı. Lütfen tekrar deneyin."
    else:
        form = SifreForm()
    return render(request, "mutabakat/giris.html",
                  {"form": form, "token": token, "hata": hata})


def index(request):
    """Kök adres: giriş (login) ekranı."""
    return _sifre_ekrani(request, "web")


def giris(request, token):
    """Maildeki link ile gelinen giriş ekranı."""
    return _sifre_ekrani(request, token)


# --------------------------------------------------------------------------- #
# Detay + karar (müşterinin kendi mutabakatı)
# --------------------------------------------------------------------------- #
def detay(request, token):
    if not _girisli_mi(request, token):
        return redirect("mutabakat:giris", token=token)

    m = get_kayit(token)
    if m is None:
        raise Http404("Mutabakat kaydı bulunamadı.")

    return render(request, "mutabakat/detay.html",
                  {"m": m, "form": CevapForm(), "token": token})


def cevap(request, token):
    if not _girisli_mi(request, token):
        return redirect("mutabakat:giris", token=token)

    m = get_kayit(token)
    if m is None:
        raise Http404("Mutabakat kaydı bulunamadı.")

    if request.method != "POST":
        return redirect("mutabakat:detay", token=token)

    form = CevapForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(request, "mutabakat/detay.html",
                      {"m": m, "form": form, "token": token})

    # Karar yerelde saklanmaz; servise iletilir (şimdilik stub — bkz. services.py).
    gonder_cevap(
        token=token,
        mutabakat=m,
        karar=form.cleaned_data["karar"],
        mesaj=form.cleaned_data["mesaj"],
        ad_soyad=form.cleaned_data["ad_soyad"],
        dosya=form.cleaned_data.get("dosya"),
    )

    # Oturumu kapat ve login ekranına dön; bilgilendirme mesajı göster
    request.session.pop(_session_key(token), None)
    if form.cleaned_data["karar"] == "itiraz":
        messages.success(request, "İtiraz bildiriminiz alınmıştır. Teşekkür ederiz.")
    else:
        messages.success(request, "Mutabakat onayınız alınmıştır. Teşekkür ederiz.")

    return redirect("mutabakat:giris", token=token)
