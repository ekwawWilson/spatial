"""Phase 13: production settings are checked before the server will run."""

from django.core.checks import run_checks

GOOD_KEY = "k" * 60


def ids(settings):
    return sorted(e.id for e in run_checks() if e.id and e.id.startswith("spatial."))


def test_development_runs_with_the_example_values(settings):
    settings.DEBUG = True
    settings.SECRET_KEY = "CHANGE_ME-dev"
    assert ids(settings) == []


def test_production_refuses_example_secrets_and_development_keys(settings):
    settings.DEBUG = False
    settings.SECRET_KEY = "CHANGE_ME-dev-only-secret-key-not-for-production-use-0123456789"
    settings.DATABASES["default"]["PASSWORD"] = "CHANGE_ME-app"
    settings.SPP_ORG_KEYS = "dev-20261006:AAAA"
    settings.ALLOWED_HOSTS = ["*"]
    assert ids(settings) == ["spatial.E001", "spatial.E002", "spatial.E003", "spatial.E004"]


def test_production_with_real_values_passes(settings):
    settings.DEBUG = False
    settings.SECRET_KEY = GOOD_KEY
    settings.DATABASES["default"]["PASSWORD"] = "a-real-password"
    settings.SPP_ORG_KEYS = "assembly-2026:AAAA"
    settings.ALLOWED_HOSTS = ["planning.example.gov.gh"]
    assert ids(settings) == []


def test_https_settings_follow_the_environment(settings):
    assert settings.SECURE_PROXY_SSL_HEADER == ("HTTP_X_FORWARDED_PROTO", "https")
    assert settings.X_FRAME_OPTIONS == "DENY"
    assert settings.SECURE_REDIRECT_EXEMPT == [r"^api/health/$"]
