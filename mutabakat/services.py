"""
Mutabakat veri katmanı (tek-kayıt akışı).

Her müşteriye e-posta ile link + şifre gönderilir. Şifre doğrulanınca o
müşteriye ait TEK mutabakat kaydı gösterilir. Bu katman veriyi nereden aldığını
soyutlar: şu an "mock", ileride ErpDataSource doldurulacak; view/şablonlar
değişmez.

Bu proje VERİTABANI KULLANMAZ. Müşteri kararı yerelde saklanmaz; ileride
servise HTTP isteğiyle iletilecektir (bkz. gonder_cevap).

Ayar: settings.MUTABAKAT_DATA_SOURCE = "mock" | "erp"
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)


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


class BaseDataSource:
    def get_kayit(self, token: str) -> Optional[Mutabakat]:
        """Bu token'a (müşteriye) ait tek mutabakat kaydını döndürür."""
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
        )

    def sifre_dogru(self, token: str, girilen: str) -> bool:
        return girilen.strip() == self.SIFRE


class ErpDataSource(BaseDataSource):
    """
    Gerçek ERP servisi. İbrahim servisi verince doldurulacak.
    get_kayit(token) -> token'a karşılık gelen müşterinin tek mutabakat kaydı.
    sifre_dogru(token, girilen) -> maildeki şifre doğrulaması.
    """

    def get_kayit(self, token: str) -> Optional[Mutabakat]:
        raise NotImplementedError(
            "ERP veri kaynağı henüz bağlanmadı. .env içinde MUTABAKAT_DATA_SOURCE=mock kullanın."
        )

    def sifre_dogru(self, token: str, girilen: str) -> bool:
        raise NotImplementedError


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
    Müşterinin kararını (Mutabıkız / İtiraz) işleyen uç.

    Bu proje veritabanı KULLANMAZ; karar yerelde saklanmaz. İbrahim'in servisi
    hazır olunca burada SERVIS_URL adresine bir HTTP isteği (POST) atılacaktır.
    Şimdilik yalnızca log'a yazar; akışı bozmaz.

    Örnek (ileride):
        import requests
        requests.post(
            settings.SERVIS_URL,
            json={
                "token": token,
                "dokuman_id": mutabakat.dokuman_id,
                "cari_kod": mutabakat.cari_kod,
                "karar": karar,
                "mesaj": mesaj,
                "ad_soyad": ad_soyad,
            },
            timeout=15,
        )
    """
    logger.info(
        "Mutabakat karari alindi | token=%s cari=%s karar=%s ad_soyad=%s "
        "mesaj=%r dosya=%s",
        token,
        getattr(mutabakat, "cari_kod", ""),
        karar,
        ad_soyad,
        mesaj,
        getattr(dosya, "name", None),
    )
