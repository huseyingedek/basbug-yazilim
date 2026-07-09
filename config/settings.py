"""
Başbuğ E-Mutabakat — Django ayarları.

Bu proje bir FRONTEND / görüntü katmanıdır: kendi veritabanı YOKTUR.
Veri ileride servisten istekle çekilecek; müşteri kararı da servise iletilecek.
Ortama bağlı tüm değerler .env dosyasından okunur; kodda değişiklik gerekmez.
"""
from pathlib import Path
import os

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# .env dosyasını yükle (varsa)
load_dotenv(BASE_DIR / ".env")


def env(key, default=None):
    return os.environ.get(key, default)


def env_bool(key, default=False):
    return str(os.environ.get(key, default)).lower() in ("1", "true", "yes", "on")


def env_list(key, default=""):
    raw = os.environ.get(key, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


# === Temel ===
SECRET_KEY = env("SECRET_KEY", "gelistirme-anahtari-uretimde-degistir")
DEBUG = env_bool("DEBUG", True)
ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "127.0.0.1,localhost")

# === Uygulamalar ===
# Veritabanı gerektiren uygulamalar (auth, contenttypes, admin) KULLANILMIYOR.
INSTALLED_APPS = [
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "mutabakat",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # WhiteNoise: statik dosyaları Django'nun kendisi servis eder (IIS sanal
    # dizin kurmadan da çalışır). SecurityMiddleware'den hemen sonra gelmeli.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# === Veritabanı ===
# YOK. Bu proje veritabanı kullanmaz. Oturum bilgisi imzalı çerezde tutulur
# (aşağıdaki SESSION_ENGINE). Sunucuda ayrı bir veritabanı kurmaya gerek yoktur.
DATABASES = {}

# Oturum verisini DB yerine imzalı çerezde sakla (login akışı için yeterli).
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"

# Mesaj çerçevesi: oturum yerine doğrudan çerez kullan; DB gerektirmez.
MESSAGE_STORAGE = "django.contrib.messages.storage.cookie.CookieStorage"

# === Yerelleştirme ===
LANGUAGE_CODE = "tr"
TIME_ZONE = "Europe/Istanbul"
USE_I18N = True
USE_TZ = True

# === Statik ve medya dosyaları ===
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
# Statik dosya deposu:
#  - Geliştirmede (DEBUG) düz depo -> 'collectstatic' gerekmeden runserver çalışır.
#  - Üretimde WhiteNoise sıkıştırılmış + hash'li ('collectstatic' sonrası) sunum.
_staticfiles_backend = (
    "django.contrib.staticfiles.storage.StaticFilesStorage"
    if DEBUG
    else "whitenoise.storage.CompressedManifestStaticFilesStorage"
)
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": _staticfiles_backend},
}

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# === Mutabakat uygulaması ayarları ===
# Veri kaynağı: "mock" (geliştirme) veya "erp" (gerçek servis)
MUTABAKAT_DATA_SOURCE = env("MUTABAKAT_DATA_SOURCE", "mock")
# Servisin adresi (veriyi buradan çekeceğiz / kararı buraya ileteceğiz).
SERVIS_URL = env("SERVIS_URL", "")

# === Üretim güvenlik ayarları (DEBUG=False iken) ===
# Ters vekil (IIS/Nginx) arkasında HTTPS'i doğru algılamak için.
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    # https://alanadi... biçiminde, virgülle ayrılmış güvenilir kaynaklar
    CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS", "")
