import pytest
from pydantic import ValidationError

from factful.config import Settings, load_settings, load_web_settings


def test_web_defaults() -> None:
    web = Settings().web
    assert web.database_url == "sqlite:///./factful.db"
    assert web.auth_mode == "google"
    assert web.session_secret
    assert web.google_client_id == ""
    assert web.google_client_secret == ""


def test_web_settings_load_from_yaml() -> None:
    settings = load_settings("config/settings.yaml")
    assert settings.web.database_url == "sqlite:///./factful.db"
    assert settings.web.auth_mode == "google"


def test_web_env_overrides_defaults() -> None:
    web = load_web_settings(
        env={
            "DATABASE_URL": "libsql://my-db.turso.io",
            "AUTH_MODE": "mock",
            "SESSION_SECRET": "abc123",
            "GOOGLE_CLIENT_ID": "id.apps.googleusercontent.com",
            "GOOGLE_CLIENT_SECRET": "xyz789",
        }
    )
    assert web.database_url == "libsql://my-db.turso.io"
    assert web.auth_mode == "mock"
    assert web.session_secret == "abc123"
    assert web.google_client_id == "id.apps.googleusercontent.com"
    assert web.google_client_secret == "xyz789"


def test_web_env_partial_override_keeps_defaults() -> None:
    web = load_web_settings(env={"AUTH_MODE": "mock"})
    assert web.auth_mode == "mock"
    assert web.database_url == "sqlite:///./factful.db"


def test_web_env_overrides_yaml_settings() -> None:
    settings = load_settings("config/settings.yaml")
    web = load_web_settings(settings, env={"AUTH_MODE": "mock"})
    assert web.auth_mode == "mock"
    assert web.database_url == settings.web.database_url


def test_web_rejects_invalid_auth_mode() -> None:
    with pytest.raises(ValidationError):
        load_web_settings(env={"AUTH_MODE": "facebook"})


def test_web_rejects_blank_session_secret() -> None:
    with pytest.raises(ValidationError):
        load_web_settings(env={"SESSION_SECRET": ""})
