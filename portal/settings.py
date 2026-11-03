"""
BelajarHub IoT Lab Portal 설정.
운영 환경 값은 환경변수(또는 /etc/belajarhub/portal.env)로 넣는다.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    return env(name, str(default)).lower() in ("1", "true", "yes", "on")


SECRET_KEY = env("PORTAL_SECRET_KEY", "dev-insecure-change-me")
DEBUG = env_bool("PORTAL_DEBUG", False)
ALLOWED_HOSTS = [h.strip() for h in env("PORTAL_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in env("PORTAL_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

if not DEBUG and SECRET_KEY.startswith("dev-"):
    raise RuntimeError("PORTAL_SECRET_KEY 를 설정하세요 (또는 PORTAL_DEBUG=1)")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "labs",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "portal.urls"

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
                "labs.context_processors.lab_settings",
            ],
        },
    },
]

WSGI_APPLICATION = "portal.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": env("PORTAL_DB_PATH", str(BASE_DIR / "db.sqlite3")),
        "OPTIONS": {"timeout": 20},
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("PORTAL_TIME_ZONE", "Asia/Jakarta")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = env("PORTAL_STATIC_ROOT", str(BASE_DIR / "staticfiles"))

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "home"
LOGOUT_REDIRECT_URL = "login"

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# ---------------------------------------------------------------------------
# 실습 환경 설정
# ---------------------------------------------------------------------------
LAB_DOMAIN = env("LAB_DOMAIN", "belajarhub.id")
LAB_MQTT_HOST = env("LAB_MQTT_HOST", "mqtt.belajarhub.id")
LAB_MQTT_PORT = int(env("LAB_MQTT_PORT", "8883"))
LAB_MQTT_TOPIC_PREFIX = env("LAB_MQTT_TOPIC_PREFIX", "unsia")
LAB_SSH_HOST = env("LAB_SSH_HOST", "belajarhub.id")

# 헬퍼의 node_port_range / spring_port_range 와 일치해야 한다
LAB_NODE_PORT_RANGE = (int(env("LAB_NODE_PORT_MIN", "9001")), int(env("LAB_NODE_PORT_MAX", "9999")))
LAB_SPRING_PORT_RANGE = (int(env("LAB_SPRING_PORT_MIN", "8001")), int(env("LAB_SPRING_PORT_MAX", "8999")))

# root 헬퍼 호출 명령. 개발 PC 에서는 샌드박스로 실행:
#   LAB_PROVISION_CMD="python3 provisioner/belajarhub-provision" BELAJARHUB_SANDBOX=/tmp/sb
LAB_PROVISION_CMD = env("LAB_PROVISION_CMD", "/usr/bin/sudo -n /usr/local/sbin/belajarhub-provision").split()

# 초기 비밀번호: "random" (권장) 또는 "{username}*01" 같은 템플릿
LAB_PASSWORD_MODE = env("LAB_PASSWORD_MODE", "random")
LAB_FORCE_PASSWORD_CHANGE = env_bool("LAB_FORCE_PASSWORD_CHANGE", False)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"labs": {"handlers": ["console"], "level": "INFO"}},
}
