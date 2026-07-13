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
from decimal import Decimal, InvalidOperation
from typing import Optional

from django.conf import settings

from . import erecon

logger = logging.getLogger(__name__)

# Karar kodları (Erecon /erecon/update 3. PARAM). 1=onay, 0=itiraz.
KARAR_KODU = {"mutabik": "1", "itiraz": "0"}

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
    confirmcode: str = ""     # ERP CONFIRMCODE (doğrulama kodu)
    durum: str = ""           # ERECONSTATUS


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
                MutabakatSatiri("Borç", Decimal("5291530.17"), "TL", Decimal("5291530.17"), "TL"),
                MutabakatSatiri("Alacak", Decimal("5656620.65"), "TL", Decimal("5656620.65"), "TL"),
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
        durum=g("ERECONSTATUS"),
        sfile_b64=g("SFILE"),
        tfile_b64=g("TFILE"),
    )
    m.toplam = _to_decimal(g("BALANCE")) or Decimal("0")

    # BALANCEHTML: gömülü JSON -> Borç / Alacak satırları
    bh = g("BALANCEHTML")
    if bh:
        try:
            for r in json.loads(bh):
                pb = r.get("CURRENCY", m.firma_pb)
                borc = _to_decimal(r.get("DOVIZ_BORC")) or Decimal("0")
                alacak = _to_decimal(r.get("DOVIZ_ALACAK")) or Decimal("0")
                tl_borc = _to_decimal(r.get("TL_BORC")) or borc
                tl_alacak = _to_decimal(r.get("TL_ALACAK")) or alacak
                m.satirlar.append(MutabakatSatiri("Borç", borc, pb, tl_borc, "TL"))
                m.satirlar.append(MutabakatSatiri("Alacak", alacak, pb, tl_alacak, "TL"))
                if r.get("ACCOUNT") and not m.cari_kod:
                    m.cari_kod = m.cari_adi = r["ACCOUNT"]
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
        sonuc = erecon.erecon_update(
            guid=token, kod=kod, karar_kodu=karar_kodu,
            dosya_b64=dosya_b64, ad_soyad=ad_soyad, mesaj=mesaj,
        )
        logger.info("Erecon /erecon/update sonucu: %s", (sonuc or "")[:500])
        return _parse_update_response(sonuc)  # (ok, mesaj, tip)

    logger.info(
        "Mutabakat kararı alındı (mock) | token=%s karar=%s ad_soyad=%s mesaj=%r dosya=%s",
        token, karar, ad_soyad, mesaj, getattr(dosya, "name", None),
    )
    return True, "", "S"
