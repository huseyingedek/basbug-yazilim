"""
Erecon login + list akisini izole test eder.
Kendi bilgisayarinda (veya sunucuda) calistir, gercek hata govdesini gorelim.

Kullanim:
    python test_erecon.py
"""
import requests

IDENTITY_BASE = "https://devapi.basbugtech.com/identity"
MW_BASE = "http://dev.basbugtech.local/mw/services/erecon"

USERNAME = "erecon"
PASSWORD = "qRTnwnYyQKD2P6Cx"
CLIENT_ID = "bis-integrations-erecon"
CLIENT_SECRET = "84mJIeU0tNExRz6UQh2Bnmtx7uSgntHo"

print("=== 1) LOGIN denemesi ===")
login_url = IDENTITY_BASE.rstrip("/") + "/Identity/login"
payload = {
    "username": USERNAME,
    "password": PASSWORD,
    "clientId": CLIENT_ID,
    "clientSecret": CLIENT_SECRET,
}
r = requests.post(login_url, json=payload, timeout=20)
print("Status:", r.status_code)
print("Body  :", r.text[:1000])

if r.status_code != 200:
    print("\n>>> LOGIN BASARISIZ, burada duruyoruz.")
    raise SystemExit(1)

data = (r.json() or {}).get("data") or {}
token = data.get("access_token")
print("\nToken alindi mi?", bool(token))
if not token:
    print(">>> Token bos geldi, login yaniti:", r.json())
    raise SystemExit(1)

print("\n=== 2) LIST denemesi (token ile) ===")
xml_body = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    "<PARAMETERS>\n"
    "  <PARAM>53171c64-b9e5-498e-a9b7-cb422c0d9680</PARAM>\n"
    "  <PARAM>20925837</PARAM>\n"
    "</PARAMETERS>"
).encode("utf-8")

headers = {
    "Content-Type": "application/xml",
    "Accept": "*/*",
    "Authorization": f"Bearer {token}",
}

r2 = requests.request("GET", MW_BASE.rstrip("/") + "/erecon/list",
                       data=xml_body, headers=headers, timeout=120)
print("Status:", r2.status_code)

# Cevap base64 gelirse coz
import base64, xml.etree.ElementTree as ET
body = (r2.text or "").strip()
if body and not body.startswith("<"):
    try:
        body = base64.b64decode(body, validate=True).decode("utf-8")
        print(">>> (yanit base64'tu, cozuldu)")
    except Exception as e:
        print(">>> base64 cozulemedi:", e)

print("\n=== ERP'nin dondurdugu TUM alanlar (LINE altindaki etiketler) ===")
try:
    root = ET.fromstring(body)
    line = root.find(".//LINE")
    if line is None:
        print("LINE yok. Ham govde:", body[:500])
    else:
        for el in line:
            val = (el.text or "").strip()
            if len(val) > 80:
                val = val[:80] + f"... ({len(el.text)} karakter)"
            print(f"  <{el.tag}> = {val!r}")

        # SFILE (Mutabakat Mektubu) ve TFILE (Ekstre) -> PDF kaydet + incele
        def _onar(raw):
            try: return raw.decode("utf-8").encode("iso-8859-9")
            except Exception: return raw
        for etiket, ad in (("SFILE", "mektup_test.pdf"), ("TFILE", "ekstre_test.pdf")):
            v = (line.findtext(etiket) or "").strip()
            print(f"\n>>> {etiket}: {len(v)} karakter (base64)")
            if not v:
                print(f"    {etiket} bos geldi.")
                continue
            ham = base64.b64decode(v)
            onarilmis = _onar(ham)
            with open(ad, "wb") as f:
                f.write(onarilmis)
            print(f"    ham ilk8={ham[:8]!r}  onarilmis ilk8={onarilmis[:8]!r}")
            print(f"    -> {ad} ({len(onarilmis)} byte)  (b'%PDF' ile baslamali)")
except Exception as e:
    print("XML parse hatasi:", e)
    print("Ham govde:", body[:500])