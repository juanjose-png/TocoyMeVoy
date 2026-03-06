import environ
from pathlib import Path

env = environ.Env(
    DEBUG=(bool, False),
    DB_NAME=(str, "cajamenor"),
    DB_USER=(str, "postgres"),
    DB_PASSWORD=(str, "postgres"),
    DB_HOST=(str, "postgres"),
    DB_PORT=(str, "5432"),
    REDIS_URL=(str, "redis://redis:6379/0"),
    ADMIN_CELLPHONE=(str, ""),
    MANTAINER_CELLPHONE=(str, ""),
    VERIFY_TOKEN=(str, ""),
    TOKEN=(str, ""),
    PHONE_NUMBER_ID=(str, ""),
    CSRF_TRUSTED_ORIGINS=(list, []),
)

BASE_DIR = Path(__file__).resolve().parent.parent

environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")

DEBUG = env("DEBUG")

ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS")
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
APPEND_SLASH = False

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "core",
]

AUTH_USER_MODEL = "core.CustomUser"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
]

ROOT_URLCONF = "solenium_project.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "solenium_project.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("DB_NAME"),
        "USER": env("DB_USER"),
        "PASSWORD": env("DB_PASSWORD"),
        "HOST": env("DB_HOST"),
        "PORT": env("DB_PORT"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-co"
TIME_ZONE = "America/Bogota"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
REDIS_URL = env("REDIS_URL")
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TIMEZONE = "America/Bogota"
CELERY_TASK_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]

from celery.schedules import crontab  # noqa: E402

CELERY_BEAT_SCHEDULE = {
    "monthly-write-headers": {
        "task": "core.tasks.monthly_write_headers",
        "schedule": crontab(day_of_month=1, hour=0, minute=0),
    },
    "monthly-create-folders": {
        "task": "core.tasks.monthly_create_folders",
        "schedule": crontab(day_of_month=1, hour=0, minute=10),
    },
}

# ---------------------------------------------------------------------------
# App settings — leídas aquí y exportadas para el resto del proyecto
# ---------------------------------------------------------------------------
GOOGLE_API_KEY = env("GOOGLE_API_KEY")
SHEET_ID = env("SHEET_ID")
MAIN_FOLDER_ID = env("MAIN_FOLDER_ID")
ADMIN_CELLPHONE = env("ADMIN_CELLPHONE")
MANTAINER_CELLPHONE = env("MANTAINER_CELLPHONE")
VERIFY_TOKEN = env("VERIFY_TOKEN")
TOKEN = env("TOKEN")
PHONE_NUMBER_ID = env("PHONE_NUMBER_ID")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
from solenium_project.logging_config import LOGGING  # noqa: E402, F401
