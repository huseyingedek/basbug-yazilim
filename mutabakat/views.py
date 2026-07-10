import base64

from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import redirect, render

from .forms import CevapForm, SifreForm
from .services import get_kayit, gonder_cevap, sifre_dogru


def _ok_key(token):
    return f"mutabakat_ok_{token}"


def _kod_key(token):
    return f"mutabakat_kod_{token}"


def _girisli_mi(request, token):
    return bool(request.session.get(_ok_key(token)))


# --------------------------------------------------------------------------- #
# Kök: bilgilendirme (portala kişiye özel link ile erişilir)
# --------------------------------------------------------------------------- #
def index(request):
    return render(request, "mutabakat/bilgi.html")


# --------------------------------------------------------------------------- #
# Giriş: /<GUID>/  -> doğrulama kodu
# --------------------------------------------------------------------------- #
def giris(request, token):
    token = str(token)
    hata = None
    if request.method == "POST":
        form = SifreForm(request.POST)
        if form.is_valid():
            kod = form.cleaned_data["sifre"]
            if sifre_dogru(token, kod):
                request.session[_ok_key(token)] = True
                request.session[_kod_key(token)] = kod
                return redirect("mutabakat:detay", token=token)
            hata = "Kod hatalı. Lütfen e-postanızdaki doğrulama kodunu giriniz."
    else:
        form = SifreForm()
    return render(request, "mutabakat/giris.html",
                  {"form": form, "token": token, "hata": hata})


# --------------------------------------------------------------------------- #
# Detay + karar
# --------------------------------------------------------------------------- #
def detay(request, token):
    token = str(token)
    if not _girisli_mi(request, token):
        return redirect("mutabakat:giris", token=token)

    kod = request.session.get(_kod_key(token), "")
    m = get_kayit(token, kod)
    if m is None:
        request.session.pop(_ok_key(token), None)
        request.session.pop(_kod_key(token), None)
        messages.error(request, "Mutabakat kaydı getirilemedi. Lütfen kodu tekrar giriniz.")
        return redirect("mutabakat:giris", token=token)

    return render(request, "mutabakat/detay.html",
                  {"m": m, "form": CevapForm(), "token": token})


def cevap(request, token):
    token = str(token)
    if not _girisli_mi(request, token):
        return redirect("mutabakat:giris", token=token)

    kod = request.session.get(_kod_key(token), "")
    m = get_kayit(token, kod)
    if m is None:
        raise Http404("Mutabakat kaydı bulunamadı.")

    if request.method != "POST":
        return redirect("mutabakat:detay", token=token)

    form = CevapForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(request, "mutabakat/detay.html",
                      {"m": m, "form": form, "token": token})

    ok, mesaj = gonder_cevap(
        token=token,
        mutabakat=m,
        kod=kod,
        karar=form.cleaned_data["karar"],
        mesaj=form.cleaned_data["mesaj"],
        ad_soyad=form.cleaned_data["ad_soyad"],
        dosya=form.cleaned_data.get("dosya"),
    )

    if not ok:
        # Servis kararı işleyemedi: detayda kal, hatayı göster.
        messages.error(request, mesaj or "Kararınız işlenemedi. Lütfen tekrar deneyiniz.")
        return render(request, "mutabakat/detay.html",
                      {"m": m, "form": CevapForm(), "token": token})

    # Başarılı: oturumu kapat ve girişe dön; bilgilendirme mesajı göster
    request.session.pop(_ok_key(token), None)
    request.session.pop(_kod_key(token), None)
    if form.cleaned_data["karar"] == "itiraz":
        messages.success(request, "İtiraz bildiriminiz alınmıştır. Teşekkür ederiz.")
    else:
        messages.success(request, "Mutabakat onayınız alınmıştır. Teşekkür ederiz.")
    return redirect("mutabakat:giris", token=token)


# --------------------------------------------------------------------------- #
# Dosya indirme: Mutabakat Mektubu (SFILE) / Ekstre (TFILE) — base64 -> PDF
# --------------------------------------------------------------------------- #
def _dosya_indir(request, token, alan, dosya_adi):
    token = str(token)
    if not _girisli_mi(request, token):
        return redirect("mutabakat:giris", token=token)
    kod = request.session.get(_kod_key(token), "")
    m = get_kayit(token, kod)
    b64 = getattr(m, alan, "") if m else ""
    if not b64:
        raise Http404("Dosya bulunamadı.")
    try:
        icerik = base64.b64decode(b64)
    except Exception:
        raise Http404("Dosya çözümlenemedi.")
    resp = HttpResponse(icerik, content_type="application/pdf")
    resp["Content-Disposition"] = f'inline; filename="{dosya_adi}"'
    return resp


def mektup(request, token):
    return _dosya_indir(request, token, "sfile_b64", "mutabakat-mektubu.pdf")


def ekstre(request, token):
    return _dosya_indir(request, token, "tfile_b64", "ekstre.pdf")
