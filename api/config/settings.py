"""
GSA HRMS settings. Every environment-specific value comes from the environment (.env in Compose).
No secrets are stored in this file.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(name, default)


def env_bool(name: str, default: bool = False) -> bool:
    return str(env(name, "1" if default else "0")).lower() in {"1", "true", "yes"}


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-only-insecure-change-me")
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = [h for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]
CSRF_TRUSTED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS if h not in {"localhost", "127.0.0.1", "api"}]

# Key for application-layer encryption of NIS number, TIN and national ID (people app).
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY", "")

INSTALLED_APPS = [
    # The admin, with sign-in only through the web app (lockout and authenticator): iam/admin_site.py
    "iam.admin_apps.HrmsAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    "procrastinate.contrib.django",
    # shared
    "core",
    "audit",
    "iam",
    # Release 1 modules
    "org",
    "people",
    "leave",
    "reports",
    "notifications",
    "privacy",
    "letters",
    "signing",
    "approvals",
    "cases",
    "incidents",
    "integration",
    # Release 2 scaffolds
    "attendance",
    "performance",
    "training",
    "payroll",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "iam.middleware.SessionActivityMiddleware",  # idle and absolute time-outs; the session list
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
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# PostgreSQL in every real environment. SQLite is used only when DB_HOST is unset,
# so that `manage.py check` and unit tests can run without a database server.
if env("DB_HOST"):
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "HOST": env("DB_HOST"),
            "PORT": env("DB_PORT", "5432"),
            "NAME": env("DB_NAME", "hrms"),
            "USER": env("DB_USER", "hrms"),
            "PASSWORD": env("DB_PASSWORD", ""),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 12}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 50,
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.UserRateThrottle"],
    "DEFAULT_THROTTLE_RATES": {"user": "600/minute"},
    "EXCEPTION_HANDLER": "core.exceptions.api_exception_handler",
}

# The OpenAPI schema and Swagger UI: public in development, signed-in people only elsewhere.
API_DOCS_PUBLIC = env_bool("API_DOCS_PUBLIC", DEBUG)

SPECTACULAR_SETTINGS = {
    "TITLE": "GSA HRMS API",
    "DESCRIPTION": "Human Resource Management System, Guyana School of Agriculture",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # Choice sets that appear under the same field name in several places get one stable name each.
    "ENUM_NAME_OVERRIDES": {
        "EmployeeStatusEnum": "people.models.Employee.Status",
        "PasswordLinkKindEnum": "iam.accounts.LINK_KINDS",
        "CareerChangeKindEnum": "people.models.CareerEvent.Kind",
        "LetterKindEnum": "letters.models.LetterTemplate.Kind",
        "LeavingReasonEnum": "people.models.Separation.Reason",
        "SignatureKindEnum": "signing.models.SignatureRequest.Kind",
        "CaseKindEnum": "cases.models.Case.Kind",
        "CaseOutcomeEnum": "cases.models.Case.Outcome",
        "CaseAppealOutcomeEnum": "cases.models.Case.AppealOutcome",
        "CaseStepEnum": "cases.models.CaseEntry.Kind",
        "IncidentKindEnum": "incidents.models.Incident.Kind",
        "IncidentStateEnum": "incidents.models.Incident.State",
        "IncidentPersonWhoEnum": "incidents.models.Person.Who",
        "InjuryTreatmentEnum": "incidents.models.Person.Treatment",
        "SafetyNoticeDutyEnum": "incidents.models.Notice.Duty",
        "SafetyNoticeRecipientEnum": "incidents.models.Notice.Recipient",
        "RecordPartEnum": "privacy.models.CorrectionRequest.Subject",
    },
}

CORS_ALLOWED_ORIGINS = [f"https://{h}" for h in ALLOWED_HOSTS if h not in {"localhost", "127.0.0.1", "api"}]
CORS_ALLOW_CREDENTIALS = True

# Email: SMTP when configured, otherwise printed to the log (development).
if env("SMTP_HOST"):
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_HOST = env("SMTP_HOST")
    EMAIL_PORT = int(env("SMTP_PORT", "587"))
    EMAIL_HOST_USER = env("SMTP_USER", "")
    EMAIL_HOST_PASSWORD = env("SMTP_PASSWORD", "")
    EMAIL_USE_TLS = True
elif env("EMAIL_FILE_PATH"):
    # One file per message in that folder: the browser journeys read invitations from it (compose.e2e.yml).
    EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
    EMAIL_FILE_PATH = env("EMAIL_FILE_PATH")
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = env("SMTP_FROM", "hrms@localhost")

LANGUAGE_CODE = "en-gb"
TIME_ZONE = env("TZ", "America/Guyana")
USE_I18N = True
USE_TZ = True
DATE_FORMAT = "d/m/Y"
SHORT_DATE_FORMAT = "d/m/Y"

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "files/"
MEDIA_ROOT = Path(env("FILES_ROOT", "/srv/files")) if env("DB_HOST") else BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Security hardening applied whenever DEBUG is off.
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_AGE = 8 * 60 * 60  # working day: the absolute limit, enforced by iam.middleware
SESSION_IDLE_MINUTES = int(env("SESSION_IDLE_MINUTES", "30"))

# `manage.py check --deploy` runs in CI and must pass with no warnings. These three are deliberate:
SILENCED_SYSTEM_CHECKS = [
    # W008 SECURE_SSL_REDIRECT: Caddy redirects HTTP to HTTPS in every deployment; a redirect here
    # would also break the container health checks, which call gunicorn directly over HTTP.
    "security.W008",
    # W005 and W021 (HSTS subdomains and preload): GSA's domain and its other services are not known
    # yet. Caddy sends a one-year HSTS header for this host; widen it once the domain is confirmed.
    "security.W005",
    "security.W021",
]

# Upload limits in megabytes, checked with the file's type in core.uploads. Caddy refuses any request body
# over 25 MB before it reaches the application.
UPLOAD_LIMIT_EVIDENCE_MB = int(env("UPLOAD_LIMIT_EVIDENCE_MB", "10"))
UPLOAD_LIMIT_DOCUMENT_MB = int(env("UPLOAD_LIMIT_DOCUMENT_MB", "20"))

# Account lockout: this many consecutive failed logins inside the window locks the account for the window.
LOGIN_MAX_FAILURES = int(env("LOGIN_MAX_FAILURES", "5"))
LOGIN_LOCKOUT_MINUTES = int(env("LOGIN_LOCKOUT_MINUTES", "15"))
# Failed sign-ins from one network address, across all accounts, before that address waits out the window.
LOGIN_MAX_FAILURES_PER_ADDRESS = int(env("LOGIN_MAX_FAILURES_PER_ADDRESS", "20"))

# Links that set a password (iam/accounts.py): an invitation to a new account, or a reset. Each works once.
PUBLIC_URL = (env("PUBLIC_URL") or f"https://{ALLOWED_HOSTS[0]}").rstrip("/")
INVITATION_DAYS = int(env("INVITATION_DAYS", "7"))
PASSWORD_RESET_MINUTES = int(env("PASSWORD_RESET_MINUTES", "60"))
# Django's own limit is the longest of the two; each kind of link then applies its own, stricter one.
PASSWORD_RESET_TIMEOUT = max(INVITATION_DAYS * 24 * 3600, PASSWORD_RESET_MINUTES * 60)
# Days HR has to answer a request to correct a record (GSA's own standard until regulations set one).
PRIVACY_RESPONSE_DAYS = int(env("PRIVACY_RESPONSE_DAYS", "30"))
# Reset requests from one address, and for one account, inside the lockout window.
PASSWORD_RESETS_PER_ADDRESS = int(env("PASSWORD_RESETS_PER_ADDRESS", "5"))
PASSWORD_RESETS_PER_ACCOUNT = 3

# A change of sign-in email address waits this many hours for the link sent to the new address (item 1.42).
EMAIL_CHANGE_HOURS = int(env("EMAIL_CHANGE_HOURS", "48"))

# Time limits on decisions (item 1.33), in working days: a reminder when a request has waited this long at a
# step, and it goes on up the line (or to the HR Manager) when it has waited this many more.
DECISION_DAYS = int(env("DECISION_DAYS", "3"))
ESCALATE_AFTER_DAYS = int(env("ESCALATE_AFTER_DAYS", "2"))

# Home (item 2.30) lists contracts and probation periods ending this many days ahead: the first contract alert
# goes out 90 days before the end (people.tasks), so Home shows everything already alerted on.
HOME_ENDING_DAYS = int(env("HOME_ENDING_DAYS", "90"))

# Accidents and incidents (item 1.16): whether GSA has a safety and health committee, representative or trade
# union to be told alongside the Occupational Safety and Health Authority. The Act says "if any": set "no" if
# there is none.
SAFETY_TELL_WORKERS = env("SAFETY_TELL_WORKERS", "yes").strip().lower() != "no"

# Letters (letters/pdf.py): the name at the head of every letter, and the start of every reference.
LETTER_ORGANISATION = env("LETTER_ORGANISATION", "Guyana School of Agriculture")
LETTER_REFERENCE_PREFIX = env("LETTER_REFERENCE_PREFIX", "GSA/HR")
# Checking a letter (item 1.47): the page named at the foot of every letter, and how many wrong answers one
# network address, or one reference, may give in the lockout window before checks from it wait.
LETTER_CHECK_URL = env("LETTER_CHECK_URL", f"{PUBLIC_URL}/#/check-letter")
LETTER_CHECK_FAILURES = int(env("LETTER_CHECK_FAILURES", "10"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
    # The PDF engine's font tools report every font they trim at INFO: a letter is not worth twenty lines.
    "loggers": {"fontTools": {"level": "WARNING"}},
}
