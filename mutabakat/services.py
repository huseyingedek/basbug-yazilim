"""
Mutabakat veri katmanı (tek-kayıt akışı).

Her müşteriye e-posta ile link (GUID) + şifre gönderilir. Şifre doğrulanınca o
müşteriye ait TEK mutabakat kaydı gösterilir. Bu katman veriyi nereden aldığını
soyutlar: "mock" (geliştirme) veya "erp" (Erecon servisleri).

Bu proje VERİTABANI KULLANMAZ. "erp" modunda veri Erecon /erecon/list'ten
çekilir, müşteri kararı /erecon/update'e iletilir (bkz. mutabakat/erecon.py).

Ayar: settings.MUTABAKAT_DATA_SOURCE = "mock" | "erp"
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from django.conf import settings

from . import erecon

logger = logging.getLogger(__name__)

# Karar kodları (Erecon /erecon/update 3. PARAM).
# Dokümandaki örnekte 1 = "Mutabakat onaylandı" -> mutabık.
# İtiraz kodu doküman/örnekte yok; İbrahim ekibinden teyit edilecek (şimdilik 2).
KARAR_KODU = {"mutabik": "1", "itiraz": "0"}  # 1=onay, 0=itiraz (İbrahim teyidi bekleniyor)


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
    dokuman_id: str
    cari_kod: str
    cari_adi: str
    mutabakat_tarihi: str
    konu: str
    firma_pb: str
    satirlar: list = field(default_factory=list)
    toplam: Decimal = Decimal("0")
    # Erecon/Logo mutabakat mektubundaki ek alanlar (opsiyonel):
    vkn: str = ""
    donem_ay: str = ""
    donem_yil: str = ""
    gonderilme_zamani: str = ""
    yetkili_adi: str = ""
    yetkili_unvani: str = ""
    email: str = ""
    tel: str = ""
    fax: str = ""
    mektup_url: str = ""      # Mutabakat Mektubu (PDF) linki
    ekstre_url: str = ""      # Ekstre dosyası linki


class BaseDataSource:
    def get_kayit(self, token: str) -> Optional[Mutabakat]:
        raise NotImplementedError

    def sifre_dogru(self, token: str, girilen: str) -> bool:
        raise NotImplementedError


class MockDataSource(BaseDataSource):
    """Geliştirme için örnek veri. Şifre: 1234"""

    SIFRE = "1234"

    def get_kayit(self, token: str) -> Optional[Mutabakat]:
        return Mutabakat(
            token=token, dokuman_id="00000016", cari_kod="00006968",
            cari_adi="CNR DEMİR ÇELİK SANAYİ VE TİCARET ANONİM ŞİRKETİ",
            mutabakat_tarihi="04.03.2026", konu="ONLİNE MUTABAKAT", firma_pb="TL",
            satirlar=[
                MutabakatSatiri("Alacak", Decimal("163697.41"), "EUR", Decimal("8535863.55"), "TL"),
                MutabakatSatiri("Borç", Decimal("79120.28"), "TL", Decimal("79120.28"), "TL"),
            ],
            toplam=Decimal("-8456743.27"),
            vkn="5400382777",
            donem_ay="Mayıs",
            donem_yil="2026",
            gonderilme_zamani="07.07.2026 11:59:32",
            yetkili_adi="Muhasebe Muhasebe",
            yetkili_unvani="MUHASEBE ŞEFİ",
            email="muhasebe@ornekfirma.com",
            tel="(352) 207 70 00",
            fax="-",
            mektup_url="",
            ekstre_url="",
        )

    def sifre_dogru(self, token: str, girilen: str) -> bool:
        return girilen.strip() == self.SIFRE


class ErpDataSource(BaseDataSource):
    """
    Erecon (gerçek servis) veri kaynağı.

    get_kayit(token): /erecon/list çağırır ve XML yanıtı Mutabakat'a çevirir.
      NOT: /erecon/list İKİ parametre ister: GUID (link anahtarı) + cari kod.
      Bizim URL'deki token = GUID. Cari kodun nereden geleceği İbrahim ekibiyle
      netleşecek (linkte mi, yanıtta mı). Şimdilik token "guid" veya "guid|cari"
      biçiminde çözülür.
    """

    def _guid_cari(self, token: str):
        if "|" in token:
            guid, cari = token.split("|", 1)
            return guid.strip(), cari.strip()
        return token.strip(), erecon._cfg("ERECON_DEFAULT_CARI", "")

    def get_kayit(self, token: str) -> Optional[Mutabakat]:
        guid, cari = self._guid_cari(token)
        xml_text = erecon.erecon_list(guid, cari)
        logger.info("Erecon /erecon/list yanıtı (parse için ham): %s", xml_text[:2000])
        return _parse_list_response(xml_text, token=token)

    # Şifre doğrulama: Dokümanda müşteri şifresi için bir uç yok. Netleşene
    # kadar geçici olarak mock şifre (1234) kullanılıyor.
    SIFRE = "1234"

    def sifre_dogru(self, token: str, girilen: str) -> bool:
        return girilen.strip() == self.SIFRE


def _parse_list_response(xml_text: str, token: str) -> Optional[Mutabakat]:
    """
    /erecon/list XML yanıtını Mutabakat nesnesine çevirir.

    TODO: Gerçek yanıt şeması (etiket adları, satır yapısı) elimize ulaşınca
    burası doldurulacak. Şu an yanıt örneği olmadığı için parse yapılamıyor.
    """
    raise NotImplementedError(
        "Erecon /erecon/list yanıt şeması bekleniyor. Dev ortamdan bir örnek "
        "yanıt alınınca bu fonksiyon yazılacak."
    )


def get_data_source() -> BaseDataSource:
    kaynak = getattr(settings, "MUTABAKAT_DATA_SOURCE", "mock").lower()
    if kaynak == "erp":
        return ErpDataSource()
    return MockDataSource()


def get_kayit(token: str) -> Optional[Mutabakat]:
    return get_data_source().get_kayit(token)


def sifre_dogru(token: str, girilen: str) -> bool:
    return get_data_source().sifre_dogru(token, girilen)


def gonder_cevap(token, mutabakat, karar, mesaj="", ad_soyad="", dosya=None):
    """
    Müşterinin kararını (Mutabıkız / İtiraz) işler.

    - "mock" modunda: yalnızca log'a yazar (yerelde saklanmaz).
    - "erp" modunda: Erecon /erecon/update'e iletir.
      PARAM sırası: guid, cari, karar_kodu, dosya(base64), ad_soyad, mesaj.
    """
    kaynak = getattr(settings, "MUTABAKAT_DATA_SOURCE", "mock").lower()

    if kaynak == "erp":
        guid = getattr(mutabakat, "token", token) or token
        cari = getattr(mutabakat, "cari_kod", "")
        karar_kodu = KARAR_KODU.get(karar, karar)
        dosya_b64 = erecon.dosya_to_base64(dosya)
        sonuc = erecon.erecon_update(
            guid=guid, cari=cari, karar_kodu=karar_kodu,
            dosya_b64=dosya_b64, ad_soyad=ad_soyad, mesaj=mesaj,
        )
        logger.info("Erecon /erecon/update sonucu: %s", (sonuc or "")[:500])
        return sonuc

    logger.info(
        "Mutabakat kararı alındı (mock) | token=%s cari=%s karar=%s ad_soyad=%s "
        "mesaj=%r dosya=%s",
        token, getattr(mutabakat, "cari_kod", ""), karar, ad_soyad, mesaj,
        getattr(dosya, "name", None),
    )
    return None
