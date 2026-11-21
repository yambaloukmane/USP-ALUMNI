"""Réglages Django pour AEPS-ALUMNI.

Toute la configuration sensible vient de variables d'environnement
(voir .env.example). Aucun secret n'est écrit dans le code.
"""
import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


DEBUG = env_bool("DJANGO_DEBUG", True)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = "dev-only-insecure-key-do-not-use-in-production"  # noqa: S105
    else:
        raise ImproperlyConfigured("DJANGO_SECRET_KEY est obligatoire quand DJANGO_DEBUG=0.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "alumni",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
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
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
                "alumni.context_processors.site",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# Les données vivent dans Supabase : Django n'a pas besoin de base locale.
DATABASES = {}

# Sessions dans un cookie signé : aucune base de données requise.
# On n'y met que de petites informations (id, email, nom) jamais l'avatar.
SESSION_ENGINE = "django.contrib.sessions.backends.signed_cookies"
SESSION_COOKIE_AGE = 60 * 60 * 24 * 30
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Africa/Abidjan"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
WHITENOISE_USE_FINDERS = True
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("DJANGO_SSL_REDIRECT", True)
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30

# --- Supabase ---
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "").strip()

# --- Espace Responsable ---
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

# --- Emails ---
_smtp_ready = bool(os.environ.get("EMAIL_HOST_USER") and os.environ.get("EMAIL_HOST_PASSWORD"))
EMAIL_BACKEND = os.environ.get("EMAIL_BACKEND") or (
    "django.core.mail.backends.smtp.EmailBackend" if _smtp_ready
    else "django.core.mail.backends.console.EmailBackend"
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587") or 587)
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "").replace(" ", "")  # le mot de passe d'application Gmail s'affiche avec des espaces
EMAIL_TIMEOUT = 15  # secondes : évite de bloquer la page si le serveur mail ne répond pas
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "AEPS-ALUMNI <noreply@example.com>")

CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "yambaloukmane1@gmail.com")
CONTACT_PHONE = os.environ.get("CONTACT_PHONE", "+225 74 70 35 88")

# Code de vérification à l'inscription
REGISTRATION_CODE_TTL_SECONDS = 15 * 60
REGISTRATION_CODE_MAX_ATTEMPTS = 5
REGISTRATION_RESEND_DELAY_SECONDS = 30

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"alumni": {"handlers": ["console"], "level": "INFO"}},
}

# --- Cache : mémoire locale par défaut, Redis si REDIS_URL est défini (recommandé avec plusieurs processus) ---
REDIS_URL = os.environ.get("REDIS_URL", "").strip()
if REDIS_URL:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.redis.RedisCache", "LOCATION": REDIS_URL}}
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# --- Site ---
# Adresse publique du site (utilisée dans les e-mails et pour le retour de paiement).
SITE_URL = os.environ.get("SITE_URL", "http://127.0.0.1:8000").strip().rstrip("/")
# Derrière un proxy (Render, Railway, Nginx...) : lire l'IP réelle dans X-Forwarded-For.
TRUST_PROXY_HEADERS = env_bool("TRUST_PROXY_HEADERS", False)
# 1 = un responsable doit valider chaque nouvelle inscription.
REQUIRE_APPROVAL = env_bool("REQUIRE_APPROVAL", False)

# --- Notifications e-mail ---
NOTIFY_ASYNC = env_bool("NOTIFY_ASYNC", True)
NOTIFY_BATCH_SIZE = int(os.environ.get("NOTIFY_BATCH_SIZE", "40") or 40)

# --- Cotisations et paiement en ligne (CinetPay) ---
DUES_AMOUNT = int(os.environ.get("DUES_AMOUNT", "5000") or 5000)  # doit être un multiple de 5 pour CinetPay
DUES_CURRENCY = os.environ.get("DUES_CURRENCY", "XOF")
PAYMENT_INSTRUCTIONS = os.environ.get(
    "PAYMENT_INSTRUCTIONS",
    "Payez par Wave ou Orange Money au numéro communiqué par le bureau, puis un responsable validera votre cotisation.",
)
CINETPAY_API_KEY = os.environ.get("CINETPAY_API_KEY", "").strip()
CINETPAY_SITE_ID = os.environ.get("CINETPAY_SITE_ID", "").strip()

# --- Supabase Storage (buckets créés par la migration SQL) ---
BUCKET_AVATARS = "avatars"
BUCKET_VOICE = "voice"
BUCKET_GALLERY = "gallery"
