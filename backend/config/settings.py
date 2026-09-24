from datetime import timedelta
from pathlib import Path

import django_stubs_ext
import environ

# Lets Django classes such as ModelAdmin take type parameters at runtime
# (ModelAdmin[Region]), as the type stubs expect.
django_stubs_ext.monkeypatch()

BASE_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BASE_DIR.parent

env = environ.Env()
environ.Env.read_env(REPO_DIR / ".env", overwrite=False)

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost"])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "drf_spectacular",
    "corsheaders",
    "core",
    "crs",
    "projects",
    "basemaps",
    "transfer",
]

MIDDLEWARE = [
    "core.tenancy.ResetDbContextMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

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

# The running app connects as the non-superuser app role so row-level security
# applies (Phase 1). Migrations and tests override DB_USER/DB_PASSWORD with the
# owner role (see docker-compose.yml and the Makefile).
APP_DB_USER: str = env("APP_DB_USER", default="spatial_app")

DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": env("POSTGRES_DB", default="spatial"),
        "USER": env("DB_USER", default=APP_DB_USER),
        "PASSWORD": env("DB_PASSWORD", default=env("APP_DB_PASSWORD", default="")),
        "HOST": env("DB_HOST", default="db"),
        "PORT": env("DB_PORT", default="5432"),
        # Required by tenancy: the district context is SET LOCAL per transaction.
        "ATOMIC_REQUESTS": True,
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "core.User"

# Failed sign-ins allowed before the account is locked, and for how long.
AUTH_LOCKOUT_THRESHOLD = env.int("AUTH_LOCKOUT_THRESHOLD", default=5)
AUTH_LOCKOUT_MINUTES = env.int("AUTH_LOCKOUT_MINUTES", default=15)

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-gb"
TIME_ZONE = "Africa/Accra"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = Path(env("MEDIA_ROOT", default=str(REPO_DIR / "media")))

CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])

REST_FRAMEWORK = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": ["core.auth.TenantJWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=env.int("JWT_ACCESS_MINUTES", default=15)),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=env.int("JWT_REFRESH_DAYS", default=7)),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": False,  # core.auth.attempt_login records it
}

# Links in password-reset and invitation emails point at the web app.
WEB_APP_URL = env("WEB_APP_URL", default="http://localhost:5173").rstrip("/")
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="no-reply@spatial.local")

SPECTACULAR_SETTINGS = {
    "TITLE": "Spatial Planning Platform API",
    "COMPONENT_SPLIT_REQUEST": True,
    # Several models have a "kind" choice field; give each enum its own name.
    "ENUM_NAME_OVERRIDES": {
        "DistrictKindEnum": "core.models.District.Kind",
        "CrsKindEnum": "crs.models.CoordinateSystem.Kind",
    },
    "DESCRIPTION": "Community planning GIS platform for Ghanaian MMDAs.",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

REDIS_URL: str = env("REDIS_URL", default="redis://redis:6379/0")

# Cache (Google map sessions, import progress). A separate Redis database from
# Celery's broker, so clearing the cache never touches queued jobs.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env("CACHE_URL", default="redis://redis:6379/1"),
    }
}
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL
CELERY_TASK_TRACK_STARTED = True

# Phase 2 seeds the system default CRS from this on a new installation only.
INITIAL_DEFAULT_CRS: str = env("INITIAL_DEFAULT_CRS", default="EPSG:2136")

# Encrypts third-party API keys at rest (e.g. basemap keys). If empty, a key is
# derived from SECRET_KEY; set it explicitly in production so SECRET_KEY can be
# rotated without losing stored keys.
FIELD_ENCRYPTION_KEY: str = env("FIELD_ENCRYPTION_KEY", default="")

# Phase 8: organisation keys for .spp files. Parsed there; reserved here so the
# setting exists in every environment from the start.
SPP_ORG_KEYS: str = env("SPP_ORG_KEYS", default="")

# Documentation; tests check some docs against the code (e.g. permissions).
DOCS_DIR = Path(env("DOCS_DIR", default=str(REPO_DIR / "docs")))

# Shared test datasets (see fixtures/README.md).
FIXTURES_DIR = Path(env("FIXTURES_DIR", default=str(REPO_DIR / "fixtures")))
