# Başbuğ E-Mutabakat — Windows Server + IIS Kurulum Rehberi

Bu proje bir **frontend / görüntü katmanıdır ve veritabanı kullanmaz.**
Oturum imzalı çerezde tutulur, statikler WhiteNoise ile Django üzerinden sunulur.
DB kurmaya, `migrate` çalıştırmaya veya statik için IIS sanal dizini açmaya
gerek yoktur.

Çalışma modeli: **IIS + httpPlatformHandler**. IIS, Python (Waitress) sürecini
kendisi başlatır ve `HTTP_PLATFORM_PORT` ile bir port atar; `serve.py` o portu
dinler. (NSSM veya ARR gerekmez.)

---

## 1. Sunucuda gerekenler

| Bileşen | Not |
|---------|-----|
| Python 3.10+ (pip ile) | Kurulumda "Add to PATH" |
| **httpPlatformHandler** modülü | IIS'e kurulu olmalı |
| Site için IIS + App Pool | .NET CLR: "No Managed Code" olabilir |
| SSL sertifikası | HTTPS binding |

`requirements.txt` şunları getirir: Django, python-dotenv, whitenoise, waitress.

---

## 2. Temiz kurulum (git clone)

Site klasörü (örn. `C:\inetpub\emutabakat`) BOŞ olmalı. Eski/bozuk içerik ve
`index.html` silinir, sonra klonlanır.

    :: Site klasörüne gir ve içini temizle (eski proje kalmasın)
    cd C:\inetpub\emutabakat

    :: Bu klasöre klonla (repo içeriği doğrudan klasöre gelsin)
    git clone <REPO_URL> .

    :: Sanal ortam + bağımlılıklar
    python -m venv .venv
    .venv\Scripts\activate
    pip install -r requirements.txt

    :: Ortam dosyası
    copy .env.example .env
    ::   .env'i uretime gore doldur (asagi, bolum 3)

    :: Statikleri topla
    python manage.py collectstatic --noinput

    :: stdout log klasoru (web.config buraya yazacak)
    mkdir logs

    :: Django saglik kontrolu
    python manage.py check

---

## 3. Üretim ayarları (.env)

    SECRET_KEY=uzun-rastgele-bir-anahtar
    DEBUG=False
    ALLOWED_HOSTS=mutabakat.basbug.com.tr

    MUTABAKAT_DATA_SOURCE=mock        # servis hazir olunca: erp
    SERVIS_URL=

    :: ILK KURULUMDA kapali tutun (asagidaki 502 notuna bakin), calisinca acin:
    SECURE_SSL_REDIRECT=False
    CSRF_TRUSTED_ORIGINS=https://mutabakat.basbug.com.tr

> `ALLOWED_HOSTS` tam olarak tarayıcıdaki alan adı olmalı: **mutabakat.basbug.com.tr**

---

## 4. web.config (httpPlatformHandler)

Repo kökündeki **`web.config`** zaten httpPlatformHandler için hazır. Sadece
şunları kontrol edin:

1. `processPath` sunucudaki venv python'una işaret etmeli. Emin olmak için TAM
   yol yazın:
   `processPath="C:\inetpub\emutabakat\.venv\Scripts\python.exe"`
2. `logs` klasörü site kökünde var olmalı (bkz. `mkdir logs`).
3. App Pool kimliğinin klasöre **okuma + yazma** izni olmalı.

Değişiklikten sonra App Pool'u **Recycle** edin (veya `iisreset`).

---

## 5. 502 hatası — sorun giderme

502 = IIS Python sürecini başlattı ama geçerli cevap alamadı. Sıra:

1. **stdout log'a bak:** `logs\stdout.log`. Django/Python hatası burada görünür.
   En hızlı teşhis budur.
2. **Port:** `serve.py` `HTTP_PLATFORM_PORT`'u okumalı (bu sürümde okuyor).
   Eski sürüm sabit 8000 dinliyordu — 502'nin klasik sebebi buydu.
3. **venv yolu:** `web.config` içindeki `processPath` yanlışsa süreç hiç
   başlamaz. TAM yol verin ve `python.exe`'nin var olduğunu doğrulayın.
4. **Bağımlılık eksik:** venv'de `pip install -r requirements.txt` çalıştı mı?
   `logs\stdout.log`'ta `ModuleNotFoundError` varsa budur.
5. **ALLOWED_HOSTS:** `.env`'de `mutabakat.basbug.com.tr` yoksa Django 400/500
   döndürür. Doğru alan adını yazın.
6. **HTTPS yönlendirme döngüsü:** `SECURE_SSL_REDIRECT=True` iken httpPlatform
   arkasında sonsuz yönlendirme olabilir. İlk kurulumda `False` tutun; site
   açıldıktan sonra, IIS proxy'sinin `X-Forwarded-Proto` başlığını ilettiğinden
   emin olup `True` yapın.
7. **Elle test:** venv aktifken `set PORT=8001 & python serve.py` çalıştırıp
   başka pencerede `http://127.0.0.1:8001` açın. Burada çalışıyorsa sorun IIS
   tarafındadır (web.config / izin / port), Django'da değildir.

Her değişiklikten sonra App Pool Recycle / `iisreset`.

---

## 6. Domain / SSL

Alan adı `mutabakat.basbug.com.tr` sunucuya A kaydıyla zaten yönlendirilmiş.
IIS site'ına HTTPS binding + kurumsal SSL sertifikası tanımlanır.

---

## Özet kontrol listesi

- [ ] Site klasörü boş; eski proje ve index.html silindi
- [ ] `git clone <REPO_URL> .`
- [ ] `python -m venv .venv` + `pip install -r requirements.txt`
- [ ] `.env` (DEBUG=False, ALLOWED_HOSTS=mutabakat.basbug.com.tr, SECRET_KEY, SECURE_SSL_REDIRECT=False)
- [ ] `python manage.py collectstatic --noinput`  (migrate YOK)
- [ ] `mkdir logs`
- [ ] `web.config` -> processPath TAM venv yolu
- [ ] `python manage.py check` temiz
- [ ] App Pool Recycle / iisreset
- [ ] 502 olursa -> `logs\stdout.log` oku
