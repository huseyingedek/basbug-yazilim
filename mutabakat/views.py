import base64

from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render

from .forms import CevapForm, SifreForm
from .logolar import _icerik_tipi, _pdf_onar, logo_getir
from .services import (
    get_kayit,
    gonder_cevap,
    onceki_ay_son_gun,
    sifre_dogru,
    talep_olustur,
    talep_son_mutabakat_bitis,
)


# --------------------------------------------------------------------------- #
# Talep oluştur (dışarıdan): ana ekrandaki "Talep Oluştur" butonu buraya gelir.
# Kişiye özel link gerekmez; müşteri/tedarikçi VKN + tarih aralığı ile talep açar.
# --------------------------------------------------------------------------- #
def talep(request):
    bitis_default = onceki_ay_son_gun().isoformat()

    if request.method == "POST":
        vkn = (request.POST.get("vkn") or "").strip()
        email = (request.POST.get("email") or "").strip()
        bas = (request.POST.get("baslangic") or "").strip()
        bit = (request.POST.get("bitis") or "").strip()

        if not vkn:
            sonuc = ("hata", "Vergi numarası (VKN) zorunludur.")
        elif not email:
            sonuc = ("hata", "E-posta adresi zorunludur.")
        else:
            ok, mesaj = talep_olustur(vkn=vkn, baslangic=bas, bitis=bit, email=email)
            sonuc = ("ok" if ok else "hata", mesaj)

        return render(request, "mutabakat/talep.html", {
            "sonuc": sonuc, "vkn": vkn, "email": email,
            "baslangic": bas, "bitis": bit or bitis_default,
        })

    # GET: bitişi önceden dolduralım (önceki ayın son günü). Başlangıç, VKN
    # girilince (talep_son_tarih) otomatik gelecek.
    return render(request, "mutabakat/talep.html",
                  {"baslangic": "", "bitis": bitis_default})


def talep_son_tarih(request):
    """VKN -> son mutabakat bitiş tarihi (başlangıç önerisi). JSON döner."""
    vkn = (request.GET.get("vkn") or "").strip()
    d = talep_son_mutabakat_bitis(vkn)
    return JsonResponse({"baslangic": d.isoformat() if d else "", "bulundu": bool(d)})


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

    ok, mesaj, tip = gonder_cevap(
        token=token,
        mutabakat=m,
        kod=kod,
        karar=form.cleaned_data["karar"],
        mesaj=form.cleaned_data["mesaj"],
        ad_soyad=form.cleaned_data["ad_soyad"],
        dosya=form.cleaned_data.get("dosya"),
    )

    if not ok:
        # Servis hatası (TYPE=E): detayda kal, hatayı kırmızı göster.
        messages.error(request, mesaj or "Kararınız işlenemedi. Lütfen tekrar deneyiniz.")
        return render(request, "mutabakat/detay.html",
                      {"m": m, "form": CevapForm(), "token": token})

    # ok=True (TYPE!=E): oturumu kapat ve GİRİŞ (onay kodu) ekranına yeşil
    # bilgilendirme mesajıyla dön. (Bora: gönderdikten sonra başa dönsün ki
    # kullanıcı "iletilmedi" sanıp tekrar basmasın -> çift gönderim / "zaten
    # güncellenmiş kayıt tekrar güncellenemez" hatası yaşanmasın.)
    request.session.pop(_ok_key(token), None)
    request.session.pop(_kod_key(token), None)
    if mesaj:
        messages.success(request, mesaj)
    elif form.cleaned_data["karar"] == "itiraz":
        messages.success(request, "İtiraz bildiriminiz tarafımıza iletilmiştir. Teşekkür ederiz.")
    else:
        messages.success(request, "Mutabakat onayınız tarafımıza iletilmiştir. Teşekkür ederiz.")
    return redirect("mutabakat:giris", token=token)


# --------------------------------------------------------------------------- #
# Dosya indirme: Mutabakat Mektubu (SFILE) / Ekstre (TFILE)
# ERP dosyayı base64 içinde gönderir; PDF veya PNG olabilir.
# --------------------------------------------------------------------------- #
def _dosya_indir(request, token, alan, taban_ad):
    token = str(token)
    if not _girisli_mi(request, token):
        return redirect("mutabakat:giris", token=token)
    kod = request.session.get(_kod_key(token), "")
    m = get_kayit(token, kod)
    b64 = getattr(m, alan, "") if m else ""
    if not b64:
        raise Http404("Dosya bulunamadı.")
    try:
        icerik = _pdf_onar(base64.b64decode(b64))
    except Exception:
        raise Http404("Dosya çözümlenemedi.")
    ctype, uzanti = _icerik_tipi(icerik)
    ad = f"{taban_ad}.{uzanti}"
    resp = HttpResponse(icerik, content_type=ctype)
    resp["Content-Disposition"] = f'inline; filename="{ad}"'
    return resp


def firma_logo(request, token):
    """
    Firma logosunu DOSYADAN servis eder (firma_logolari/<COMPANY>.png).
    Servis her açılışta çağrılmaz; logolar haftalık `manage.py logo_guncelle`
    ile yenilenir. Firma kodu ?f=<COMPANY> ile gelir (EReconList yanıtından).
    Logo yoksa 404 -> şablon Başbuğ logosuna düşer.
    """
    token = str(token)
    if not _girisli_mi(request, token):
        return redirect("mutabakat:giris", token=token)
    kod = (request.GET.get("f") or "").strip()
    yol = logo_getir(kod)
    if not yol:
        raise Http404("Firma logosu bulunamadı.")
    ctype = "image/png" if yol.suffix == ".png" else "image/jpeg"
    resp = HttpResponse(yol.read_bytes(), content_type=ctype)
    resp["Content-Disposition"] = f'inline; filename="firma-logo{yol.suffix}"'
    resp["Cache-Control"] = "private, max-age=3600"
    return resp


def mektup(request, token):
    return _dosya_indir(request, token, "sfile_b64", "mutabakat-mektubu")


def ekstre(request, token):
    return _dosya_indir(request, token, "tfile_b64", "ekstre")
