"""
Mutabakat veri katmanı.

Akış: Müşteriye e-posta ile link (GUID) + doğrulama kodu gönderilir. Müşteri
linke tıklar, kodu girer; o cariye ait TEK mutabakat kaydı gösterilir.

Veri kaynağı (settings.MUTABAKAT_DATA_SOURCE):
  - "mock" : yerel örnek veri (geliştirme). Kod: 123456
  - "erp"  : Erecon servisleri (gerçek).

Erecon /erecon/list yanıt şeması: <TMPCONF><LINE>...</LINE></TMPCONF>
Erecon /erecon/update yanıt şeması: <MESSAGETABLE><ROW><TYPE>...</TYPE>...</ROW></MESSAGETABLE>
Hata durumları da MESSAGETABLE (TYPE=E) olarak döner.

Bu proje VERİTABANI KULLANMAZ.
"""
from __future__ import annotations

import json
import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

from django.conf import settings

from . import erecon

logger = logging.getLogger(__name__)

# Karar kodları (Erecon /erecon/update 3. PARAM). 1=onay, 2=itiraz.
KARAR_KODU = {"mutabik": "1", "itiraz": "2"}

# FINPERIOD (dönem no) -> ay adı
_AYLAR = {
    "01": "Ocak", "02": "Şubat", "03": "Mart", "04": "Nisan", "05": "Mayıs",
    "06": "Haziran", "07": "Temmuz", "08": "Ağustos", "09": "Eylül",
    "10": "Ekim", "11": "Kasım", "12": "Aralık",
}


@dataclass
class MutabakatSatiri:
    ba: str                 # "Alacak" / "Borç"
    tutar: Decimal
    para_birimi: str
    tutar_fpb: Decimal
    firma_pb: str


@dataclass
class Mutabakat:
    token: str
    dokuman_id: str = ""
    cari_kod: str = ""
    cari_adi: str = ""
    mutabakat_tarihi: str = ""
    konu: str = ""
    firma_pb: str = "TL"
    satirlar: list = field(default_factory=list)
    toplam: Decimal = Decimal("0")
    vkn: str = ""
    donem_ay: str = ""
    donem_yil: str = ""
    gonderilme_zamani: str = ""
    yetkili_adi: str = ""
    yetkili_unvani: str = ""
    email: str = ""
    tel: str = ""
    fax: str = ""
    mektup_url: str = ""      # Mutabakat Mektubu (PDF) indirme linki
    ekstre_url: str = ""      # Ekstre dosyası indirme linki
    sfile_b64: str = ""       # Mutabakat mektubu ham base64 (PDF)
    tfile_b64: str = ""       # Ekstre ham base64
    confirmcode: str = ""     # ERP CONFIRMCODE (list yanıtından; update'e gönderilir)
    ukey: str = ""            # ERP UKEY (list yanıtından; update'e gönderilir)
    durum: str = ""           # ERECONSTATUS
    firma_kodu: str = ""      # COMPANY (logo dosyası bu koda göre seçilir)


class BaseDataSource:
    def get_kayit(self, token: str, kod: str = "") -> Optional[Mutabakat]:
        raise NotImplementedError

    def sifre_dogru(self, token: str, kod: str) -> bool:
        raise NotImplementedError


class MockDataSource(BaseDataSource):
    """Geliştirme için örnek veri. Kod: 123456"""

    KOD = "123456"

    def get_kayit(self, token: str, kod: str = "") -> Optional[Mutabakat]:
        return Mutabakat(
            token=token, dokuman_id="00000016", cari_kod="D01.02.0050",
            cari_adi="D01.02.0050",
            mutabakat_tarihi="01.07.2026 00:00:00", konu="Mutabakat mektubu",
            firma_pb="TL",
            satirlar=[
                MutabakatSatiri("Alacak", Decimal("365090.48"), "TL", Decimal("365090.48"), "TL"),
            ],
            toplam=Decimal("-365090.48"),
            donem_ay="Temmuz", donem_yil="2026",
            email="muhasebe@ornekfirma.com.tr",
            confirmcode="10058842", durum="0",
        )

    def sifre_dogru(self, token: str, kod: str) -> bool:
        return (kod or "").strip() == self.KOD


class ErpDataSource(BaseDataSource):
    """Erecon (gerçek servis) veri kaynağı. GUID + doğrulama kodu ile çalışır."""

    def get_kayit(self, token: str, kod: str = "") -> Optional[Mutabakat]:
        xml_text = erecon.erecon_list(token, kod)
        return _parse_list_response(xml_text, token=token)

    def sifre_dogru(self, token: str, kod: str) -> bool:
        # list geçerli bir TMPCONF döndürüyorsa kod doğru; MESSAGETABLE(E) ise yanlış.
        try:
            return self.get_kayit(token, kod) is not None
        except Exception:
            logger.warning("Erecon kod doğrulama sırasında hata", exc_info=True)
            return False


# --------------------------------------------------------------------------- #
# XML yardımcıları
# --------------------------------------------------------------------------- #
def _jval(r: dict, *keys):
    """BALANCEHTML JSON'dan ilk DOLU anahtarı döndürür.
    Alt çizgili/çizgisiz varyantları otomatik dener (ERP alan adı değişikliğine dayanıklı)."""
    for k in keys:
        for kk in (k, k.replace("_", "")):
            v = r.get(kk)
            if v not in (None, ""):
                return v
    return None


def _to_decimal(s) -> Optional[Decimal]:
    if s is None:
        return None
    t = str(s).strip().replace(" ", "")
    if not t:
        return None
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        return Decimal(t)
    except InvalidOperation:
        return None


# TYPE oncelik: E(hata) > W(uyari) > I(bilgi) > S(basari)
_TIP_ONCELIK = {"E": 3, "W": 2, "I": 1, "S": 0}


def _messagetable(root) -> tuple[str, str]:
    """MESSAGETABLE kökünden (tip, mesaj) döndürür. tip: E/W/I/S (en agir)."""
    tips = []
    msgs = []
    for row in root.iter("ROW"):
        typ = (row.findtext("TYPE") or "").strip().upper()
        msg = (row.findtext("SYSTEMMSG") or row.findtext("MESSAGE") or "").strip()
        if typ:
            tips.append(typ)
        if msg:
            msgs.append(msg)
    tip = max(tips, key=lambda t: _TIP_ONCELIK.get(t, 0)) if tips else "S"
    return tip, " ".join(msgs)


def _parse_list_response(xml_text: str, token: str) -> Optional[Mutabakat]:
    """/erecon/list yanıtını (TMPCONF) Mutabakat'a çevirir. Hata/boş -> None."""
    logger.info("Erecon /erecon/list ham yanıt: %s", (xml_text or "")[:3000])
    if not xml_text or not xml_text.strip():
        return None
    try:
        root = ET.fromstring(xml_text.strip())
    except ET.ParseError:
        logger.error("Erecon /erecon/list yanıtı geçerli XML değil.")
        return None

    tag = root.tag.split("}")[-1].upper()
    if tag == "MESSAGETABLE":
        _, msg = _messagetable(root)
        logger.warning("Erecon /erecon/list hata/doğrulama: %s", msg)
        return None
    if tag != "TMPCONF":
        logger.warning("Erecon /erecon/list beklenmeyen kök etiketi: %s", tag)
        return None

    line = root.find(".//LINE")
    if line is None:
        return None

    def g(name):
        el = line.find(name)
        return (el.text or "").strip() if (el is not None and el.text) else ""

    finperiod = g("FINPERIOD")
    m = Mutabakat(
        token=token,
        cari_kod=g("CUSTOMER"),
        cari_adi=g("CUSTNAME") or g("CUSTOMER"),   # ünvan: CUSTNAME (yoksa koda düş)
        mutabakat_tarihi=g("VALIDFROM"),
        konu=g("STDTEXT") or "ONLİNE MUTABAKAT",
        firma_pb=g("CURRENCY") or "TL",
        email=g("MAILADR"),
        donem_yil=g("FINYEAR"),
        donem_ay=_AYLAR.get(finperiod.zfill(2), finperiod),
        confirmcode=g("CONFIRMCODE"),
        ukey=g("UKEY"),
        durum=g("ERECONSTATUS"),
        firma_kodu=g("COMPANY"),
        sfile_b64=g("SFILE"),
        tfile_b64=g("TFILE"),
    )
    m.toplam = _to_decimal(g("BALANCE")) or Decimal("0")

    # BALANCEHTML: her para birimi için TEK satır -> BAKİYE (borç/alacak sign'a göre)
    bh = g("BALANCEHTML")
    if bh:
        try:
            for r in json.loads(bh):
                pb = _jval(r, "CURRENCY") or m.firma_pb
                dov_bakiye = _to_decimal(_jval(r, "DOVIZ_BAKIYE")) or Decimal("0")
                tl_bakiye = _to_decimal(_jval(r, "TL_BAKIYE"))
                if tl_bakiye is None:
                    tl_bakiye = dov_bakiye
                # Bakiye = Borç - Alacak: negatif -> Alacak, pozitif -> Borç
                ba = "Alacak" if dov_bakiye < 0 else "Borç"
                m.satirlar.append(
                    MutabakatSatiri(ba, abs(dov_bakiye), pb, abs(tl_bakiye), "TL")
                )
                hesap = _jval(r, "ACCOUNT")
                if hesap and not m.cari_kod:
                    m.cari_kod = m.cari_adi = hesap
        except Exception:
            logger.warning("BALANCEHTML JSON parse edilemedi: %s", bh[:200], exc_info=True)

    # Dosyalar mevcutsa indirme linkleri (base64 view üzerinden servis edilir)
    if m.sfile_b64:
        m.mektup_url = f"/{token}/mektup/"
    if m.tfile_b64:
        m.ekstre_url = f"/{token}/ekstre/"

    return m


def _parse_update_response(xml_text: str) -> tuple[bool, str, str]:
    """/erecon/update yanıtını (ok, mesaj, tip) döndürür. tip: E/W/I/S."""
    if not xml_text or not xml_text.strip():
        return True, "", "S"
    try:
        root = ET.fromstring(xml_text.strip())
    except ET.ParseError:
        logger.error("Erecon /erecon/update yanıtı geçerli XML değil: %s", xml_text[:300])
        return False, "Servis yanıtı okunamadı.", "E"
    if root.tag.split("}")[-1].upper() == "MESSAGETABLE":
        tip, msg = _messagetable(root)
        return (tip != "E"), msg, tip
    return True, "", "S"


# --------------------------------------------------------------------------- #
# Dış arayüz
# --------------------------------------------------------------------------- #
def get_data_source() -> BaseDataSource:
    kaynak = getattr(settings, "MUTABAKAT_DATA_SOURCE", "mock").lower()
    if kaynak == "erp":
        return ErpDataSource()
    return MockDataSource()


def get_kayit(token: str, kod: str = "") -> Optional[Mutabakat]:
    return get_data_source().get_kayit(token, kod)


def sifre_dogru(token: str, kod: str) -> bool:
    return get_data_source().sifre_dogru(token, kod)


def gonder_cevap(token, mutabakat, karar, mesaj="", ad_soyad="", dosya=None, kod=""):
    """
    Müşteri kararını işler ve (ok, mesaj) döndürür.
      - "mock": log'a yazar, (True, "") döner.
      - "erp" : /erecon/update -> PARAM: guid, kod, karar_kodu, dosya(b64), ad, mesaj.
    """
    kaynak = getattr(settings, "MUTABAKAT_DATA_SOURCE", "mock").lower()

    if kaynak == "erp":
        karar_kodu = KARAR_KODU.get(karar, karar)
        dosya_b64 = erecon.dosya_to_base64(dosya)
        # ÖNEMLİ (Bora): EReconUpdate'e, kullanıcının linkindeki değerler DEĞİL,
        # EReconList'in DÖNDÜĞÜ kaydın UKEY + CONFIRMCODE'u gönderilmeli. ERP,
        # gelen GUID'i başka/güncel bir kayda eşleyip farklı UKEY/CONFIRMCODE
        # dönebiliyor; karar o kayda işlenmeli. Yoksa (boşsa) linke geri düş.
        ukey = (getattr(mutabakat, "ukey", "") or token)
        confirmcode = (getattr(mutabakat, "confirmcode", "") or kod)
        logger.info(
            "Erecon /erecon/update gönderiliyor | ukey=%s confirmcode=%s karar=%s",
            ukey, confirmcode, karar_kodu,
        )
        sonuc = erecon.erecon_update(
            ukey=ukey, confirmcode=confirmcode, karar_kodu=karar_kodu,
            dosya_b64=dosya_b64, ad_soyad=ad_soyad, mesaj=mesaj,
        )
        logger.info("Erecon /erecon/update sonucu: %s", (sonuc or "")[:500])
        return _parse_update_response(sonuc)  # (ok, mesaj, tip)

    logger.info(
        "Mutabakat kararı alındı (mock) | token=%s karar=%s ad_soyad=%s mesaj=%r dosya=%s",
        token, karar, ad_soyad, mesaj, getattr(dosya, "name", None),
    )
    return True, "", "S"


# --------------------------------------------------------------------------- #
# Talep (dışarıdan mutabakat talebi oluşturma)
#   Dış müşteri/tedarikçi ana ekrandan "Talep Oluştur" der; VKN + tarih aralığı
#   ile talep açar. VKN girilince "son mutabakat bitiş tarihi" başlangıca gelir.
#   Şimdilik MOCK; Canias/Erecon servisi gelince ilgili dalları doldurulacak.
# --------------------------------------------------------------------------- #
def onceki_ay_son_gun(bugun: Optional[date] = None) -> date:
    """Bir önceki ayın son gününü döndürür (bitiş tarihi varsayılanı)."""
    bugun = bugun or date.today()
    return bugun.replace(day=1) - timedelta(days=1)


def _iso_to_ddmmyyyy(s: str) -> str:
    """'2026-01-31' -> '31.01.2026'. E-Recon PSSDATE/PSEDATE formatı dd.mm.yyyy.
    Zaten dd.mm.yyyy ise / boşsa dokunmadan döner."""
    s = (s or "").strip()
    if not s:
        return ""
    try:
        return date.fromisoformat(s).strftime("%d.%m.%Y")
    except ValueError:
        return s


def _extract_response_data(xml_text: str) -> str:
    """<RESPONSE><DATA>base64</DATA></RESPONSE> içinden DATA (base64) döndürür.
    GetReconDash ve AccountStatement yanıtları için. Bulunamazsa boş string."""
    if not xml_text or not xml_text.strip():
        return ""
    try:
        root = ET.fromstring(xml_text.strip())
    except ET.ParseError:
        logger.error("RESPONSE yanıtı geçerli XML değil: %s", xml_text[:200])
        return ""
    # <RESPONSE><DATA>..</DATA></RESPONSE> ya da doğrudan <DATA>
    el = root.find(".//DATA")
    if el is None and root.tag.split("}")[-1].upper() == "DATA":
        el = root
    return (el.text or "").strip() if (el is not None and el.text) else ""


def talep_son_mutabakat_bitis(vkn: str) -> Optional[date]:
    """
    Verilen VKN için EN SON yapılan mutabakatın bitiş tarihini döndürür (yeni
    talebin başlangıcı olarak önerilir). Kayıt yoksa None.

    - "erp": ileride Canias/Erecon servisi ile sorgulanacak (TODO).
    - Aksi halde MOCK: örnek sabit tarih (demoda otomatik doldurmayı göstermek için).
    """
    v = (vkn or "").strip()
    if not v:
        return None

    kaynak = getattr(settings, "MUTABAKAT_DATA_SOURCE", "mock").lower()
    if kaynak == "erp":
        # E-Recon dökümanında (v1.0) "VKN -> son mutabakat tarihi" için bir servis
        # YOK. Sahte tarih göstermemek için None dönüyoruz: başlangıç boş gelir,
        # talep eden kendisi seçer. İbrahim böyle bir servis sağlarsa buraya bağlanır.
        return None

    # Yalnızca "mock" modda örnek tarih (geliştirme için).
    return date(2026, 4, 30)


def talep_olustur(vkn: str, baslangic: str = "", bitis: str = "",
                  email: str = "") -> tuple[bool, str]:
    """
    Yeni mutabakat talebini işler ve (ok, mesaj) döndürür.
      - "erp": E-Recon EReconRequest servisine iletir (VKN + tarih aralığı).
               Yanıt MESSAGETABLE (TYPE / SYSTEMMSG) olarak değerlendirilir.
      - Aksi halde MOCK: log'a yazar, başarılı döner.
    """
    kaynak = getattr(settings, "MUTABAKAT_DATA_SOURCE", "mock").lower()

    if kaynak == "erp":
        pssdate = _iso_to_ddmmyyyy(baslangic)
        psedate = _iso_to_ddmmyyyy(bitis)
        xml_text = erecon.erecon_request(pstaxnum=vkn, pssdate=pssdate, psedate=psedate)
        ok, mesaj, tip = _parse_update_response(xml_text)
        logger.info("EReconRequest sonucu | tip=%s mesaj=%r", tip, mesaj)
        # NOT (döküman uyarısı): Bu serviste başarı durumunda dahi TYPE=E
        # dönebiliyor; SYSTEMMSG "Talebiniz Alınmıştır" gibi olumlu olabilir.
        # TYPE'a güvenip talebi hatalı göstermemek için: SYSTEMMSG varsa onu
        # kullanıcıya gösterip talebi ALINMIŞ kabul ediyoruz. TYPE'ın gerçek
        # semantiği İbrahim'den teyit edilince bu satır netleştirilecek.
        if mesaj:
            return True, mesaj
        return ok, (mesaj or "Mutabakat talebiniz alınmıştır.")

    logger.info(
        "Mutabakat talebi alındı (mock) | vkn=%s email=%s aralik=%s - %s",
        vkn, email, baslangic or "?", bitis or "?",
    )
    return True, ("Talebiniz alındı. Mutabakat hazırlanınca %s adresine "
                  "kişiye özel bağlantı gönderilecektir." % (email or "e-posta"))


def dashboard_verisi(vkn: str, yil: str, donem: str) -> str:
    """
    GetReconDash: VKN + yıl + dönem -> dashboard XML metni (<TMPDASH>...</TMPDASH>).
    Gerçek yanıt: TÜM gövde base64'lü XML; erecon._return_or_raise base64'ü çözer,
    yani burada doğrudan XML döner. Boş/hatalıysa "".
    """
    from . import erecon
    return erecon.get_recon_dash(pstaxnum=vkn, psyear=yil, psperiod=donem) or ""


def hesap_ekstresi(uuid: str) -> bytes:
    """
    AccountStatement: UUID(30) -> hesap ekstresi (PDF bytes).
    Gerçek yanıt: base64 -> <TMPCONF> XML; PDF, TMPCONF içindeki bir base64 alanda
    (ör. TFILE/SFILE/FILE). O alanı bulup çözer; bulamazsa b"".
    """
    from . import erecon
    xml_text = erecon.account_statement(uuid=uuid) or ""
    if not xml_text.strip():
        return b""
    try:
        root = ET.fromstring(xml_text.strip())
    except ET.ParseError:
        logger.warning("AccountStatement XML değil: %s", xml_text[:200])
        return b""
    for alan in ("TFILE", "SFILE", "FILE", "PDF", "EKSTRE", "DATA", "CONTENT"):
        el = root.find(".//" + alan)
        if el is not None and (el.text or "").strip():
            try:
                import base64 as _b64
                return _b64.b64decode((el.text or "").strip())
            except Exception:
                logger.warning("AccountStatement %s base64 çözülemedi.", alan, exc_info=True)
                return b""
    logger.warning("AccountStatement TMPCONF alanları (PDF alanı bulunamadı): %s",
                   [c.tag for c in list(root)][:20])
    return b""


# =========================================================================== #
# PANEL (iç) veri katmanı — Dashboard + Karşılaştırma
#   Kaynak "erp" ise GetReconDash (VKN + yıl + dönem) çağrılır; dönen ZIP/xlsx
#   çözümlenip ekranlara aktarılır. Yalnızca CANLI veri gösterilir; veri
#   yoksa/servise ulaşılamazsa ekran "veri yok" durumunu gösterir (örnek veri YOK).
#   Gerçek bir GetReconDash örneği gelince yalnızca _recon_dash_coz() güncellenecek.
# =========================================================================== #
_AY_KISA = {1: "Oca", 2: "Şub", 3: "Mar", 4: "Nis", 5: "May", 6: "Haz",
            7: "Tem", 8: "Ağu", 9: "Eyl", 10: "Eki", 11: "Kas", 12: "Ara"}
_AY_UZUN = {1: "Ocak", 2: "Şubat", 3: "Mart", 4: "Nisan", 5: "Mayıs", 6: "Haziran",
            7: "Temmuz", 8: "Ağustos", 9: "Eylül", 10: "Ekim", 11: "Kasım", 12: "Aralık"}


def _son_12_ay(bugun: Optional[date] = None):
    """En eskiden yeniye 12 ay: [(yil, ay, 'Tem 26'), ...]."""
    bugun = bugun or date.today()
    out = []
    y, a = bugun.year, bugun.month
    for _ in range(12):
        out.append((y, a, f"{_AY_KISA[a]} {str(y)[2:]}"))
        a -= 1
        if a == 0:
            a = 12
            y -= 1
    return list(reversed(out))


def panel_donem_secenekleri(bugun: Optional[date] = None):
    """Dönem seçici için son 12 ay: [{'value':'2026-07','label':'Temmuz 2026'}]."""
    out = []
    for y, a, _ in reversed(_son_12_ay(bugun)):  # en yeni üstte
        out.append({"value": f"{y}-{a:02d}", "label": f"{_AY_UZUN[a]} {y}"})
    return out


def panel_donem_coz(value: str, bugun: Optional[date] = None):
    """'2026-07' -> ('2026', '07', 'Temmuz 2026'). Geçersizse içinde bulunulan ay."""
    bugun = bugun or date.today()
    y, a = bugun.year, bugun.month
    if value and "-" in value:
        try:
            ys, as_ = value.split("-", 1)
            y, a = int(ys), int(as_)
        except ValueError:
            pass
    a = min(12, max(1, a))
    return str(y), f"{a:02d}", f"{_AY_UZUN[a]} {y}"


# ------------------------- GetReconDash çözümleme ---------------------------- #
# ERECONSTATUS anlamları (gerçek yanıttan + KARAR_KODU ile uyumlu; İbrahim teyidi iyi olur):
#   "0" = Gönderildi / yanıt bekleniyor
#   "1" = Mutabık (onay)
#   "2" = Mutabık Değil (itiraz)
ERECON_DURUM_MUTABIK = "1"
ERECON_DURUM_ITIRAZ = "2"


def varsayilan_dash_vkn() -> str:
    """Dashboard'ın sorgulayacağı firma VKN'si (Başbuğ). .env: ERECON_DASH_VKN."""
    return (getattr(settings, "ERECON_DASH_VKN", "") or "").strip()


def _tmpdash_satirlari(xml_text: str) -> list:
    """GetReconDash yanıtındaki <TMPDASH><LINE>...</LINE></TMPDASH> kayıtlarını
    sözlük listesine çevirir. Her LINE = bir mutabakat kaydı."""
    if not xml_text or not xml_text.strip():
        return []
    try:
        root = ET.fromstring(xml_text.strip())
    except ET.ParseError:
        logger.warning("GetReconDash XML değil: %s", xml_text[:200])
        return []
    tmp = root if root.tag.upper().endswith("TMPDASH") else root.find(".//TMPDASH")
    if tmp is None:
        return []
    out = []
    for line in tmp.findall("LINE"):
        def g(t):
            v = line.findtext(t)
            return (v or "").strip()
        out.append({
            "ukey": g("UKEY"), "musteri": g("CUSTOMER"), "mail": g("MAILADR"),
            "bakiye": g("BALANCE"), "durum": g("ERECONSTATUS"),
            "yil": g("FINYEAR"), "donem": g("FINPERIOD"),
            "tarih": g("VALIDFROM"), "kod": g("CONFIRMCODE"),
        })
    return out


def _durum_say(satirlar: list):
    """(gönderilen, dönen, mutabık, mutabık_değil) sayıları."""
    gonderilen = len(satirlar)
    mutabik = sum(1 for s in satirlar if s["durum"] == ERECON_DURUM_MUTABIK)
    mutabik_degil = sum(1 for s in satirlar if s["durum"] == ERECON_DURUM_ITIRAZ)
    donen = mutabik + mutabik_degil
    return gonderilen, donen, mutabik, mutabik_degil


def _son_12_donem(yil: str, donem: str):
    """Seçili dönemde biten son 12 ay: [(yil_str, ay_int, 'Tem 26'), ...] eski->yeni."""
    try:
        y, a = int(yil), int(donem)
    except Exception:
        t = date.today()
        y, a = t.year, t.month
    out = []
    for _ in range(12):
        out.append((str(y), a, f"{_AY_KISA[a]} {str(y)[2:]}"))
        a -= 1
        if a == 0:
            a = 12
            y -= 1
    return list(reversed(out))


def panel_dashboard_data(vkn: str = "", yil: str = "", donem: str = ""):
    """
    Panel dashboard (firma geneli, CANLI). GetReconDash'i firma VKN'siyle son 12 ay
    için çağırır; her ayın kayıtlarını duruma göre sayar. Kartlar seçili dönemdir.
    Veri hiç yoksa None -> "veri yok".
    """
    kaynak = getattr(settings, "MUTABAKAT_DATA_SOURCE", "mock").lower()
    if kaynak != "erp":
        return None
    from . import erecon
    vkn = (vkn or "").strip()
    if not vkn:
        return None  # VKN girilmeden veri çekilmez
    yil = yil or str(date.today().year)
    donem = donem or ("%02d" % date.today().month)

    aylar, g_s, d_s, m_s, md_s = [], [], [], [], []
    secili_satir = []
    toplam = 0
    hedef_y, hedef_a = str(int(yil)), int(donem)
    for y, a, etiket in _son_12_donem(yil, donem):
        try:
            xml = erecon.get_recon_dash(pstaxnum=vkn, psyear=y, psperiod="%02d" % a)
        except Exception:
            logger.warning("GetReconDash %s-%02d hata", y, a, exc_info=True)
            xml = ""
        satir = _tmpdash_satirlari(xml)
        gg, dd, mm, mdd = _durum_say(satir)
        aylar.append(etiket)
        g_s.append(gg); d_s.append(dd); m_s.append(mm); md_s.append(mdd)
        toplam += gg
        if y == hedef_y and a == hedef_a:
            secili_satir = satir

    if toplam == 0:
        return None  # 12 ayın hiçbirinde kayıt yok

    sg, sd, sm, smd = _durum_say(secili_satir)
    itirazlar = [s for s in secili_satir if s["durum"] == ERECON_DURUM_ITIRAZ]
    return {
        "aylar": aylar,
        "seriler": [
            {"ad": "Gönderilen",      "renk": "#2f6fd0", "veri": g_s},
            {"ad": "Dönen",           "renk": "#5b6b80", "veri": d_s},
            {"ad": "Mutabıkız",       "renk": "#1f9d55", "veri": m_s},
            {"ad": "Mutabık Değiliz", "renk": "#cf3127", "veri": md_s},
        ],
        "s_gonderilen": sg, "s_donen": sd, "s_mutabik": sm, "s_mutabik_degil": smd,
        "itirazlar": itirazlar,
        "canli": True,
    }


_DURUM_AD = {"0": "Gönderildi · yanıt bekleniyor", "1": "Mutabık", "2": "Mutabık Değil (itiraz)"}


def _tr_para(s) -> str:
    """'2398563.5' -> '2.398.563,50'. Sayı değilse olduğu gibi döner."""
    try:
        d = Decimal(str(s).replace(",", "."))
    except Exception:
        return str(s or "")
    neg = d < 0
    d = abs(d).quantize(Decimal("0.01"))
    tam = int(d)
    kur = int((d - tam) * 100)
    return f"{'-' if neg else ''}{format(tam, ',').replace(',', '.')},{kur:02d}"


def _cari_detay(rec: dict) -> Optional[dict]:
    """Bir cari kaydı için /erecon/list çağırıp Başbuğ tarafı özetini döndürür."""
    from . import erecon
    try:
        xml = erecon.erecon_list(rec["ukey"], rec["kod"])
    except Exception:
        logger.warning("erecon_list hata (ukey=%s)", rec.get("ukey"), exc_info=True)
        return None
    try:
        root = ET.fromstring((xml or "").strip())
    except ET.ParseError:
        return None
    ln = root.find(".//LINE")
    if ln is None:
        return None
    custname = (ln.findtext("CUSTNAME") or rec.get("musteri") or "").strip()
    borc = alacak = bakiye = ""
    pb = "TL"
    bh = (ln.findtext("BALANCEHTML") or "").strip()
    if bh:
        try:
            row = (json.loads(bh) or {}).get("ROW") or {}
            borc = _tr_para(row.get("TL_BORC", "0"))
            alacak = _tr_para(row.get("TL_ALACAK", "0"))
            bakiye = _tr_para(row.get("TL_BAKIYE", "0"))
            pb = row.get("CURRENCY") or "TL"
        except Exception:
            logger.warning("BALANCEHTML çözülemedi", exc_info=True)
    durum = rec.get("durum", "")
    return {
        "musteri": rec.get("musteri", ""), "custname": custname, "mail": rec.get("mail", ""),
        "durum": durum, "durum_ad": _DURUM_AD.get(durum, durum),
        "basbug": {"borc": borc, "alacak": alacak, "bakiye": bakiye, "pb": pb},
        # Karşı taraf: yalnızca müşteri itiraz edince (durum 2) oluşur; yapı henüz yok.
        "itiraz_var": durum == ERECON_DURUM_ITIRAZ,
    }


def panel_karsilastirma_data(vkn: str = "", yil: str = "", donem: str = "", musteri: str = ""):
    """
    Karşılaştırma verisi (CANLI). firma VKN + dönem -> cari listesi; bir müşteri
    seçilince o carinin Başbuğ tarafı özeti (/erecon/list) getirilir.
    Veri yoksa None.
    """
    kaynak = getattr(settings, "MUTABAKAT_DATA_SOURCE", "mock").lower()
    if kaynak != "erp":
        return None
    from . import erecon
    vkn = (vkn or "").strip()
    if not vkn:
        return None
    try:
        xml = erecon.get_recon_dash(pstaxnum=vkn, psyear=yil, psperiod=donem)
    except Exception:
        logger.warning("GetReconDash hata (karşılaştırma)", exc_info=True)
        return None
    satirlar = _tmpdash_satirlari(xml)
    if not satirlar:
        return None
    for s in satirlar:
        s["bakiye_fmt"] = _tr_para(s.get("bakiye"))
        s["durum_ad"] = _DURUM_AD.get(s.get("durum", ""), s.get("durum", ""))

    secili = None
    if (musteri or "").strip():
        rec = next((s for s in satirlar if s.get("musteri") == musteri.strip()), None)
        if rec:
            secili = _cari_detay(rec)
    return {"cariler": satirlar, "secili": secili}
