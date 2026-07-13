"""
Erecon (ERP) servis istemcisi.

Servisler (Geliştirme Ortamı — dokümana göre):
  Kimlik (JWT):
    POST {IDENTITY_BASE}/Identity/login        -> access_token alır
    POST {IDENTITY_BASE}/Identity/refreshtoken -> token yeniler
    POST {IDENTITY_BASE}/Identity/logout
  Mutabakat (Bearer + application/xml):
    GET  {MW_BASE}/erecon/list    -> cari mutabakat kaydını çeker
    POST {MW_BASE}/erecon/update  -> müşteri kararını iletir

XML gövde biçimi (her iki uç için):
  <PARAMETERS><PARAM>...</PARAM>...</PARAMETERS>

Ayarlar settings/.env üzerinden gelir (ERECON_*). Erişim jetonu bellek içinde
önbelleğe alınır; süresi dolunca önce refresh, olmazsa yeniden login denenir.
"""
from __future__ import annotations

import base64
import logging
import threading
import time
from xml.sax.saxutils import escape

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_tokens = {
    "access_token": None,
    "access_expires_at": 0.0,
    "refresh_token": None,
    "refresh_expires_at": 0.0,
}

# Güvenlik payı: jeton süresi bitmeden bu kadar saniye önce yenile.
_SKEW = 20


def _cfg(name, default=""):
    return getattr(settings, name, default) or default


# --------------------------------------------------------------------------- #
# Kimlik (JWT)
# --------------------------------------------------------------------------- #
def _store(data: dict):
    now = time.time()
    _tokens["access_token"] = data.get("access_token")
    _tokens["access_expires_at"] = now + int(data.get("expires_in", 300)) - _SKEW
    _tokens["refresh_token"] = data.get("refresh_token")
    _tokens["refresh_expires_at"] = now + int(data.get("refresh_expires_in", 3600)) - _SKEW


def _login() -> dict:
    url = _cfg("ERECON_IDENTITY_BASE").rstrip("/") + "/Identity/login"
    payload = {
        "username": _cfg("ERECON_USERNAME"),
        "password": _cfg("ERECON_PASSWORD"),
        "clientId": _cfg("ERECON_CLIENT_ID"),
        "clientSecret": _cfg("ERECON_CLIENT_SECRET"),
    }
    r = requests.post(url, json=payload, timeout=20)
    r.raise_for_status()
    j = r.json() or {}
    if not j.get("isSuccess", True):
        raise RuntimeError("Erecon login başarısız: %s" % j.get("message"))
    data = j.get("data") or {}
    if not data.get("access_token"):
        raise RuntimeError("Erecon login: access_token boş döndü (kimlik bilgileri/adres hatalı olabilir).")
    _store(data)
    logger.info("Erecon login OK (expires_in=%s)", data.get("expires_in"))
    return data


def _refresh() -> dict:
    url = _cfg("ERECON_IDENTITY_BASE").rstrip("/") + "/Identity/refreshtoken"
    payload = {
        "clientId": _cfg("ERECON_CLIENT_ID"),
        "clientSecret": _cfg("ERECON_CLIENT_SECRET"),
        "refreshToken": _tokens["refresh_token"],
    }
    r = requests.post(url, json=payload, timeout=20)
    r.raise_for_status()
    j = r.json() or {}
    if not j.get("isSuccess", True):
        raise RuntimeError("Erecon refresh başarısız: %s" % j.get("message"))
    data = j.get("data") or {}
    if not data.get("access_token"):
        raise RuntimeError("Erecon refresh: access_token boş döndü.")
    _store(data)
    logger.info("Erecon refresh OK")
    return data


def get_access_token() -> str:
    """Geçerli bir access_token döndürür; gerekiyorsa refresh/login yapar."""
    with _lock:
        now = time.time()
        if _tokens["access_token"] and now < _tokens["access_expires_at"]:
            return _tokens["access_token"]
        if _tokens["refresh_token"] and now < _tokens["refresh_expires_at"]:
            try:
                _refresh()
                return _tokens["access_token"]
            except Exception:
                logger.warning("Erecon refresh başarısız; login denenecek", exc_info=True)
        _login()
        return _tokens["access_token"]


def logout():
    token = _tokens.get("refresh_token")
    if not token:
        return
    url = _cfg("ERECON_IDENTITY_BASE").rstrip("/") + "/Identity/logout"
    payload = {
        "clientId": _cfg("ERECON_CLIENT_ID"),
        "clientSecret": _cfg("ERECON_CLIENT_SECRET"),
        "refreshToken": token,
    }
    try:
        requests.post(url, json=payload, timeout=15)
    finally:
        _tokens.update(access_token=None, refresh_token=None,
                       access_expires_at=0.0, refresh_expires_at=0.0)


# --------------------------------------------------------------------------- #
# Mutabakat servisleri
# --------------------------------------------------------------------------- #
def _xml(*params) -> str:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<PARAMETERS>"]
    for p in params:
        val = "" if p is None else escape(str(p))
        lines.append(f"  <PARAM>{val}</PARAM>")
    lines.append("</PARAMETERS>")
    return "\n".join(lines)


def _headers() -> dict:
    return {
        "Content-Type": "application/xml",
        "Accept": "*/*",
        "Authorization": f"Bearer {get_access_token()}",
    }


def _mw(path: str) -> str:
    return _cfg("ERECON_MW_BASE").rstrip("/") + path


def _maybe_b64_decode(text: str) -> str:
    """
    Erecon büyük yanıtları (SFILE'lı) Kong üzerinden geçebilmek için tüm gövdeyi
    base64 olarak döndürüyor. Gövde XML değil de base64 ise çözer; zaten XML ise
    olduğu gibi bırakır.
    """
    s = (text or "").strip()
    if not s or s.startswith("<"):
        return text  # zaten düz XML
    try:
        decoded = base64.b64decode(s, validate=True).decode("utf-8")
    except Exception:
        return text  # base64 değil, dokunma
    return decoded if "<" in decoded else text


def _return_or_raise(r) -> str:
    """
    Erecon anlamlı hatalarını 400 statüsüyle birlikte MESSAGETABLE gövdesinde
    döndürür (ör. geçersiz kod/kayıt). Gövde XML ise onu döndür ki üst katman
    MESSAGETABLE'ı 'kod hatalı' olarak işleyebilsin. Sadece gerçekten
    beklenmedik durumlarda (boş gövde / 5xx) hata fırlat.
    Not: Yanıt base64 gelirse (büyük SFILE'lı kayıtlar) önce çözülür.
    """
    text = _maybe_b64_decode(r.text or "")
    logger.info("Erecon yanıt: status=%s body=%s", r.status_code, text[:800])
    if r.ok:
        return text
    if r.status_code < 500 and ("<MESSAGETABLE" in text or "<TMPCONF" in text):
        # İş kuralı hatası: gövdeyi olduğu gibi ver, parser ele alsın.
        return text
    r.raise_for_status()
    return text


def erecon_list(guid: str, kod: str) -> str:
    """
    Mutabakat kaydını çeker.
    Gövde: <PARAMETERS><PARAM>{guid}</PARAM><PARAM>{kod}</PARAM></PARAMETERS>
      PARAM1 = GUID (link anahtarı), PARAM2 = doğrulama kodu.
    Dönen: XML metin (services.py'de Mutabakat'a parse edilir).
    """
    body = _xml(guid, kod).encode("utf-8")
    # Doküman GET diyor ama gövdeyle; requests GET+data destekler.
    r = requests.request("GET", _mw("/erecon/list"), data=body, headers=_headers(), timeout=120)
    return _return_or_raise(r)


def erecon_update(guid: str, kod: str, karar_kodu, dosya_b64: str = "",
                  ad_soyad: str = "", mesaj: str = "") -> str:
    """
    Müşteri kararını iletir. PARAM sırası (dokümandaki örneğe göre):
      1) guid  2) kod  3) karar kodu  4) dosya(base64)  5) ad soyad  6) mesaj
    """
    body = _xml(guid, kod, karar_kodu, dosya_b64 or "", ad_soyad or "", mesaj or "").encode("utf-8")
    r = requests.post(_mw("/erecon/update"), data=body, headers=_headers(), timeout=120)
    return _return_or_raise(r)


def dosya_to_base64(dosya) -> str:
    """Django UploadedFile -> base64 metin. Dosya yoksa boş string."""
    if not dosya:
        return ""
    try:
        dosya.seek(0)
    except Exception:
        pass
    return base64.b64encode(dosya.read()).decode("ascii")
