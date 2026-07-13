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

    # ok=True (TYPE!=E): sonucu YEŞİL olarak DETAYDA göster (login'de mesaj yok).
    if mesaj:
        messages.success(request, mesaj)
    elif form.cleaned_data["karar"] == "itiraz":
        messages.success(request, "İtiraz bildiriminiz alınmıştır. Teşekkür ederiz.")
    else:
        messages.success(request, "Mutabakat onayınız alınmıştır. Teşekkür ederiz.")
    return redirect("mutabakat:detay", token=token)


# --------------------------------------------------------------------------- #
# Dosya indirme: Mutabakat Mektubu (SFILE) / Ekstre (TFILE)
# ERP dosyayı base64 içinde gönderir; PDF veya PNG olabilir.
# --------------------------------------------------------------------------- #
def _pdf_onar(raw: bytes) -> bytes:
    """
    ERP, dosyayı base64'lemeden önce ikili veriyi ISO-8859-9 metin gibi okuyup
    UTF-8'e çevirerek bozabiliyor (mojibake): 0x9C -> 0xC2 0x9C gibi. Ham ikili
    veri geçerli UTF-8 OLMAZ; eğer bytes UTF-8'e çözülebiliyorsa bozulmuştur,
    ISO-8859-9'a geri kodlayarak orijinali kurtarırız. Zaten temizse (ham ikili)
    UTF-8 decode hata verir, dokunmadan döneriz. PNG gibi temiz gelen dosyalara
    dokunmaz.
    """
    try:
        s = raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw  # zaten temiz ikili
    try:
        return s.encode("iso-8859-9")
    except UnicodeEncodeError:
        return raw


def _icerik_tipi(raw: bytes):
    """Sihirli baytlara göre (content_type, uzanti) döndürür."""
    if raw[:4] == b"%PDF":
        return "application/pdf", "pdf"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png", "png"
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg", "jpg"
    return "application/octet-stream", "bin"


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


def mektup(request, token):
    return _dosya_indir(request, token, "sfile_b64", "mutabakat-mektubu")


def ekstre(request, token):
    return _dosya_indir(request, token, "tfile_b64", "ekstre")
