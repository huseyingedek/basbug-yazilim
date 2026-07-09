# Başbuğ E-Mutabakat

Online cari hesap mutabakat portalı. Müşteriye e-posta ile gönderilen bağlantı
üzerinden mutabakat bilgilerini görüntüleyip onaylama / itiraz etme akışı.

## Teknoloji

- Python + Django 5
- Django template + saf CSS/JS (menüsüz, birkaç ekranlık akış)
- Veri katmanı soyut: şimdilik `mock`, ileride ERP servisi (`erp`)

## Kurulum

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
copy .env.example .env        # Windows  (macOS/Linux: cp .env.example .env)

python manage.py migrate
python manage.py runserver
```

## Akış / URL'ler

| URL | Ekran |
|-----|-------|
| `/` | Ana karşılama sayfası (boş, görsel) |
| `/m/<token>/` | Şifre giriş ekranı (maildeki link) |
| `/m/<token>/detay/` | Mutabakat bilgileri + karar |
| `/m/<token>/cevap/` | Kararın işlendiği uç (POST) |
| `/m/<token>/tesekkur/` | Bildirim alındı ekranı |

## Demo

`MUTABAKAT_DATA_SOURCE=mock` iken örnek veri gelir.
Deneme bağlantısı: `http://127.0.0.1:8000/m/demo/` — **şifre: 1234**

## Gerçek veriye geçiş

İbrahim'in ERP servisi/DB'si hazır olunca:

1. `.env` içinde `MUTABAKAT_DATA_SOURCE=erp` yapılır, `ERP_SERVICE_URL` / `ERP_SERVICE_TOKEN` doldurulur.
2. `mutabakat/services.py` içindeki `ErpDataSource.get()` doldurulur (servis çağrısı → `Mutabakat` nesnesi).
3. Gerekirse DB bağlantısı `.env`'deki `DB_*` değerleriyle ayarlanır.

View'lar ve template'ler değişmez — sadece veri kaynağı adaptörü değişir.

## Marka / tema

Renkler `static/css/styles.css` içinde `:root` altında CSS değişkeni olarak tanımlı.
Başbuğ logosu, arka plan görseli ve kurumsal renkler netleşince buradan güncellenir.
