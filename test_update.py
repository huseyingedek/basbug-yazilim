"""
Erecon /erecon/update yanitini izole test eder — servisin dondurdugu ham
MESSAGETABLE'i (TYPE dahil) gormek icin. Zaten onayli bir kaydi tekrar onaylar.
    python test_update.py
"""
import base64
import requests

IDENTITY_BASE = "https://devapi.basbugtech.com/identity"
MW_BASE = "http://dev.basbugtech.local/mw/services/erecon"
USERNAME = "erecon"
PASSWORD = "qRTnwnYyQKD2P6Cx"
CLIENT_ID = "bis-integrations-erecon"
CLIENT_SECRET = "84mJIeU0tNExRz6UQh2Bnmtx7uSgntHo"

# Zaten onayli kayit (tekrar onay -> "guncellenemez" mesaji doner)
GUID = "950c9b4e-e492-430b-ae39-be53b69a8002"
KOD = "00194109"
KARAR = "1"          # 1 = mutabik

print("=== LOGIN ===")
r = requests.post(IDENTITY_BASE.rstrip("/") + "/Identity/login", json={
    "username": USERNAME, "password": PASSWORD,
    "clientId": CLIENT_ID, "clientSecret": CLIENT_SECRET,
}, timeout=20)
token = ((r.json() or {}).get("data") or {}).get("access_token")
print("Token:", bool(token))

print("\n=== UPDATE (tekrar onay) ===")
body = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    "<PARAMETERS>\n"
    f"  <PARAM>{GUID}</PARAM>\n"
    f"  <PARAM>{KOD}</PARAM>\n"
    f"  <PARAM>{KARAR}</PARAM>\n"
    "  <PARAM></PARAM>\n"
    "  <PARAM>Test Ad</PARAM>\n"
    "  <PARAM>Test mesaj</PARAM>\n"
    "</PARAMETERS>"
).encode("utf-8")

r2 = requests.post(MW_BASE.rstrip("/") + "/erecon/update", data=body, headers={
    "Content-Type": "application/xml", "Accept": "*/*",
    "Authorization": f"Bearer {token}",
}, timeout=60)

print("Status:", r2.status_code)
text = (r2.text or "").strip()
if text and not text.startswith("<"):
    try:
        text = base64.b64decode(text, validate=True).decode("utf-8")
        print(">>> (yanit base64'tu, cozuldu)")
    except Exception:
        pass
print("HAM YANIT:")
print(text)
