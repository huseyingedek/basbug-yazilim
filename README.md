# Başbuğ E-Mutabakat

Online cari hesap mutabakat portalı. Müşteriye e-posta ile gönderilen bağlantı
üzerinden mutabakat bilgilerini görüntüleyip onaylama / itiraz etme akışı.

## Teknoloji

- Python + Django 5
- Django template + saf CSS/JS (menüsüz, birkaç ekranlık akış)
- **Veritabanı yok** — bu bir frontend / görüntü katmanı; veri ileride servisten çekilir
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

# migrate GEREKMEZ — proje veritabanı kullanmaz.
python manage.py runserver
```

Sunucuya kurulum (Windows Server + IIS) için: [DEPLOY.md](DEPLOY.md)

## Akış / URL'ler

| URL | Ekran |
|-----|-------|
| `/` | Şifre giriş ekranı |
| `/m/<token>/` | Şifre giriş ekranı (maildeki link) |
| `/m/<token>/detay/` | Mutabakat bilgileri + karar |
| `/m/<token>/cevap/` | Kararın işlendiği uç (POST) |

## Demo

`MUTABAKAT_DATA_SOURCE=mock` iken örnek veri gelir.
Deneme bağlantısı: `http://127.0.0.1:8000/m/demo/` — **şifre: 1234**

## Gerçek veriye geçiş

İbrahim'in ERP servisi hazır olunca:

1. `.env` içinde `MUTABAKAT_DATA_SOURCE=erp` yapılır, `SERVIS_URL` doldurulur.
2. `mutabakat/services.py` içindeki `ErpDataSource.get_kayit()` doldurulur (servis çağrısı → `Mutabakat` nesnesi).
3. Aynı dosyadaki `gonder_cevap()` içinde müşteri kararı servise POST edilir.

View'lar ve template'ler değişmez — sadece veri kaynağı adaptörü değişir.
Veritabanı gerekmez.

## Marka / tema

Renkler `static/css/styles.css` içinde `:root` altında CSS değişkeni olarak tanımlı.
Başbuğ logosu, arka plan görseli ve kurumsal renkler netleşince buradan güncellenir.
