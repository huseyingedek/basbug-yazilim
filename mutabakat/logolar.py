"""
Firma logoları — dosya önbelleği.

Logolar her mutabakat açılışında servisten ÇEKİLMEZ. Haftada bir (pazartesi
akşamı, Windows Görev Zamanlayıcı -> `python manage.py logo_guncelle`)
EReconCompanyPict servisi BOŞ parametreyle çağrılır; servis tüm firmaların
logolarını JSON olarak döner (COMPANY = firma kodu, LOGOBASE64 = logo).
Her logo `firma_logolari/<COMPANY>.png` olarak kaydedilir.

Sayfa, EReconList'in döndüğü COMPANY koduna göre logoyu bu klasörden gösterir.
Yeni açılan bir firmanın dosyası yoksa servis EN FAZLA saatte bir kez yeniden
çağrılır (her istekte değil); logo yine yoksa Başbuğ logosu gösterilir.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import threading
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)

LOGO_DIR = Path(getattr(settings, "FIRMA_LOGO_DIR", "") or (Path(settings.BASE_DIR) / "firma_logolari"))
_MARKER = ".son_guncelleme"
_EKSIK_YENILEME_ARALIGI = 3600  # sn: eksik logo için servise en fazla saatte bir git
_KOD_RE = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")
_lock = threading.Lock()


# --------------------------------------------------------------------------- #
# Dosya / görsel yardımcıları (views.py de kullanır)
# --------------------------------------------------------------------------- #
def _pdf_onar(raw: bytes) -> bytes:
    """
    ERP, dosyayı base64'lemeden önce ikili veriyi ISO-8859-9 metin gibi okuyup
    UTF-8'e çevirerek bozabiliyor (mojibake): 0x9C -> 0xC2 0x9C gibi. Ham ikili
    veri geçerli UTF-8 OLMAZ; eğer bytes UTF-8'e çözülebiliyorsa bozulmuştur,
    ISO-8859-9'a geri kodlayarak orijinali kurtarırız. Zaten temizse (ham ikili)
    UTF-8 decode hata verir, dokunmadan döneriz.
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


def _logo_kirp(raw: bytes) -> bytes:
    """
    Logo bazen büyük bir tuval içinde (bol boşlukla) geliyor; başlıktaki plakaya
    sığdırılınca minicik görünüyor. Etraftaki saydam VEYA beyaza yakın boşluğu
    kırpıp PNG olarak döner. Pillow yoksa / çözülemezse ham veriyi döndürür.
    """
    try:
        from PIL import Image, ImageChops
    except Exception:
        return raw
    try:
        im = Image.open(io.BytesIO(raw))
        im.load()
    except Exception:
        return raw

    rgba = im.convert("RGBA")
    alpha = rgba.getchannel("A")
    bbox = alpha.getbbox() if alpha.getextrema()[0] < 255 else None
    if bbox is None:
        rgb = rgba.convert("RGB")
        bg = Image.new("RGB", rgb.size, (255, 255, 255))
        bbox = ImageChops.difference(rgb, bg).getbbox()
    if not bbox:
        return raw

    pad = max(2, int(min(rgba.width, rgba.height) * 0.04))
    l, t, r, b = bbox
    kirpik = rgba.crop((max(0, l - pad), max(0, t - pad),
                        min(rgba.width, r + pad), min(rgba.height, b + pad)))
    if kirpik.width >= rgba.width * 0.98 and kirpik.height >= rgba.height * 0.98:
        return raw
    out = io.BytesIO()
    kirpik.save(out, format="PNG")
    return out.getvalue()


# --------------------------------------------------------------------------- #
# Servis yanıtı çözümleme
# --------------------------------------------------------------------------- #
def _jsona_cevir(text: str):
    """Yanıt metnini JSON nesnesine çevirir. Düz JSON, base64'lü JSON veya
    <...><DATA>json</DATA> biçimlerini dener. Olmazsa None."""
    s = (text or "").strip().lstrip("﻿")
    if not s:
        return None
    if s.startswith("<"):
        # XML zarfı: içindeki metni (DATA vb.) al
        try:
            root = ET.fromstring(s)
            el = root.find(".//DATA")
            s = ((el.text if el is not None else "".join(root.itertext())) or "").strip()
        except ET.ParseError:
            return None
    try:
        return json.loads(s)
    except ValueError:
        pass
    try:
        return json.loads(base64.b64decode(s, validate=False).decode("utf-8-sig"))
    except Exception:
        return None


def _kayitlari_bul(obj, out: list):
    """JSON içinde COMPANY + LOGOBASE64 anahtarlı tüm sözlükleri (iç içe olsa da) toplar."""
    if isinstance(obj, dict):
        anahtar = {str(k).upper(): v for k, v in obj.items()}
        if "COMPANY" in anahtar and "LOGOBASE64" in anahtar:
            out.append((str(anahtar["COMPANY"] or "").strip(),
                        str(anahtar["LOGOBASE64"] or "").strip()))
        for v in obj.values():
            if isinstance(v, (dict, list)):
                _kayitlari_bul(v, out)
    elif isinstance(obj, list):
        for v in obj:
            _kayitlari_bul(v, out)
    return out


def _xml_kayitlari(s: str) -> list:
    """Düz XML yanıt: <...><COMPANY>01</COMPANY><LOGOFILE>..</LOGOFILE><LOGOBASE64>..</LOGOBASE64></...>"""
    try:
        root = ET.fromstring(s)
    except ET.ParseError:
        return []
    out = []
    for el in root.iter():
        alt = {c.tag.split("}")[-1].upper(): (c.text or "").strip() for c in el}
        if "COMPANY" in alt and "LOGOBASE64" in alt:
            out.append((alt["COMPANY"], alt["LOGOBASE64"]))
    return out


def yanit_coz(text: str) -> list[tuple[str, str]]:
    """
    Servis yanıtı -> [(firma_kodu, logo_base64), ...]
    Her kayıtta COMPANY, LOGOFILE (dosya adı; kullanılmıyor, tür içerikten
    anlaşılır) ve LOGOBASE64 gelir. JSON veya XML; gövde base64'lü de olabilir.
    """
    s = (text or "").strip().lstrip("\ufeff")
    adaylar = [s]
    if s and not s.startswith(("<", "[", "{")):
        try:
            adaylar.append(base64.b64decode(s).decode("utf-8-sig").strip())
        except Exception:
            pass
    for a in adaylar:
        if a.startswith("<"):
            kayit = _xml_kayitlari(a)
            if kayit:
                return kayit
    return _kayitlari_bul(_jsona_cevir(text), [])


# --------------------------------------------------------------------------- #
# Kaydet / bul
# --------------------------------------------------------------------------- #
def kod_gecerli(kod: str) -> bool:
    return bool(kod) and bool(_KOD_RE.match(kod))


def _yaz(path: Path, data: bytes):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)  # atomik: okuyan istek yarım dosya görmez


def logo_kaydet(kod: str, b64: str) -> bool:
    """Tek firmanın logosunu diske yazar. Başarılıysa True."""
    if not kod_gecerli(kod) or not b64:
        return False
    try:
        icerik = _pdf_onar(base64.b64decode(b64))
    except Exception:
        logger.warning("Logo base64 çözülemedi (firma=%s)", kod)
        return False
    ctype, _ = _icerik_tipi(icerik)
    if ctype not in ("image/png", "image/jpeg"):
        logger.warning("Logo görsel değil (firma=%s, tip=%s)", kod, ctype)
        return False
    kirpik = _logo_kirp(icerik)
    if kirpik[:8] == b"\x89PNG\r\n\x1a\n":
        icerik, uzanti, eski = kirpik, "png", "jpg"
    else:
        uzanti = "png" if ctype == "image/png" else "jpg"
        eski = "jpg" if uzanti == "png" else "png"
    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    _yaz(LOGO_DIR / f"{kod}.{uzanti}", icerik)
    (LOGO_DIR / f"{kod}.{eski}").unlink(missing_ok=True)  # eski uzantılı kopya kalmasın
    return True


def logo_dosyasi(kod: str) -> Optional[Path]:
    """Firma koduna ait kayıtlı logo dosyası; yoksa None."""
    if not kod_gecerli(kod):
        return None
    for uzanti in ("png", "jpg"):
        p = LOGO_DIR / f"{kod}.{uzanti}"
        if p.is_file():
            return p
    return None


def logolari_guncelle() -> dict:
    """
    EReconCompanyPict'i boş parametreyle çağırır, tüm logoları diske yazar.
    Dönen: {"bulunan": n, "kaydedilen": n, "ham": yanıtın başı (teşhis için)}
    """
    from . import erecon

    text = erecon.erecon_company_pict_tumu()
    kayitlar = yanit_coz(text)
    kaydedilen = sum(1 for kod, b64 in kayitlar if logo_kaydet(kod, b64))
    try:
        LOGO_DIR.mkdir(parents=True, exist_ok=True)
        (LOGO_DIR / _MARKER).write_text(time.strftime("%Y-%m-%d %H:%M:%S"), encoding="utf-8")
    except OSError:
        logger.warning("Logo klasörüne yazılamadı: %s", LOGO_DIR, exc_info=True)
    logger.info("Logo güncelleme: bulunan=%s kaydedilen=%s", len(kayitlar), kaydedilen)
    return {"bulunan": len(kayitlar), "kaydedilen": kaydedilen, "ham": (text or "")[:500]}


def logo_getir(kod: str) -> Optional[Path]:
    """
    Sayfa için logo dosyası. Dosya yoksa (ör. yeni açılan firma) servis en fazla
    saatte bir yeniden çağrılır; her istekte servise gidilmez.
    """
    p = logo_dosyasi(kod)
    if p or not kod_gecerli(kod):
        return p
    marker = LOGO_DIR / _MARKER
    with _lock:
        try:
            son = marker.stat().st_mtime
        except OSError:
            son = 0.0
        if time.time() - son < _EKSIK_YENILEME_ARALIGI:
            return None
        try:
            LOGO_DIR.mkdir(parents=True, exist_ok=True)
            marker.touch()  # eşzamanlı istekler tekrar tetiklemesin
            logolari_guncelle()
        except Exception:
            logger.warning("Eksik logo için güncelleme başarısız (firma=%s)", kod, exc_info=True)
    return logo_dosyasi(kod)
