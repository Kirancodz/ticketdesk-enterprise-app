import io
import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import StatementError
from uvicorn.logging import AccessFormatter

from app.core.config import DEVELOPMENT_SECRET_KEY, Settings, load_settings, settings
from app.core.database import engine
from app.core.exceptions import register_exception_handlers
from app.core.logging_config import SecretSafeLogFilter, setup_logging


SIGNING_KEY = "fixture-Q5rmV3bRXpdyaxfwgD9tT6Mh6m8LJz4A"
DB_PASSWORD = "fixture-unique-db-secret"
DB_URL = f"postgresql+psycopg://app:{DB_PASSWORD}@db.example.com/ticketdesk"


@pytest.fixture
def production(monkeypatch):
    for name in Settings.model_fields:
        monkeypatch.delenv(name, raising=False)
    return {
        "APP_ENV": "production",
        "DEBUG": False,
        "SECRET_KEY": SIGNING_KEY,
        "DATABASE_URL": DB_URL,
        "BACKEND_CORS_ORIGINS": ["https://support.example.com"],
    }


@pytest.mark.parametrize("key", [
    None, "", DEVELOPMENT_SECRET_KEY, "short", "a" * 64,
    "abcdefghijklmnopqrstuvwxyz1234567890",
])
def test_production_rejects_missing_development_and_weak_keys(production, key):
    if key is None:
        del production["SECRET_KEY"]
    else:
        production["SECRET_KEY"] = key
    with pytest.raises(ValidationError, match="explicit SECRET_KEY") as error:
        Settings(_env_file=None, **production)
    if key:
        assert key not in str(error.value)
    assert DB_PASSWORD not in str(error.value)


@pytest.mark.parametrize("url", [
    None,
    "postgresql+psycopg://ticketdesk:ticketdesk_secret@db/ticketdesk_db",
    "postgresql+psycopg://app@db/ticketdesk_db",
    "sqlite://",
    "invalid-database-url",
    f"{DB_URL}?password=overridden",
])
def test_production_rejects_unsafe_database_settings(production, url):
    if url is None:
        del production["DATABASE_URL"]
    else:
        production["DATABASE_URL"] = url
    with pytest.raises(ValidationError, match="DATABASE_URL") as error:
        Settings(_env_file=None, **production)
    assert SIGNING_KEY not in str(error.value)
    assert DB_PASSWORD not in str(error.value)


def test_unsafe_environment_and_debug_are_rejected(production):
    with pytest.raises(ValidationError, match="APP_ENV"):
        Settings(_env_file=None, **{**production, "APP_ENV": "prod"})
    with pytest.raises(ValidationError, match="DEBUG=false"):
        Settings(_env_file=None, **{**production, "DEBUG": True})


@pytest.mark.parametrize("origin", [
    "*",
    "http://support.example.com",
    "https://*.example.com",
    "https://localhost",
    "https://127.0.0.1",
    "https://support.example.com/",
    "https://user:credential@support.example.com",
    "https://support.example.com?token=sensitive",
    "https://[2001:db8::1]suffix",
    "https://support.example.com:bad",
])
def test_production_rejects_invalid_cors_origins(production, origin):
    with pytest.raises(ValidationError, match="BACKEND_CORS_ORIGINS") as error:
        Settings(_env_file=None, **{**production, "BACKEND_CORS_ORIGINS": [origin]})
    assert origin not in str(error.value)
    assert SIGNING_KEY not in str(error.value)


def test_production_requires_explicit_cors_and_accepts_same_origin(production):
    assert Settings(_env_file=None, **production).APP_ENV == "production"
    del production["BACKEND_CORS_ORIGINS"]
    with pytest.raises(ValidationError, match="BACKEND_CORS_ORIGINS"):
        Settings(_env_file=None, **production)
    assert Settings(_env_file=None, BACKEND_CORS_ORIGINS=[], **production).BACKEND_CORS_ORIGINS == []


@pytest.mark.parametrize("environment", ["development", "test", "verification"])
def test_nonproduction_settings_remain_compatible(production, environment):
    config = Settings(_env_file=None, APP_ENV=environment, DATABASE_URL="sqlite://")
    assert config.APP_ENV == environment
    assert config.SECRET_KEY == DEVELOPMENT_SECRET_KEY
    assert config.DEBUG
    assert config.DATABASE_URL == "sqlite://"
    assert "http://localhost:5173" in config.BACKEND_CORS_ORIGINS


def test_startup_reports_validation_failures_without_secrets(production, monkeypatch):
    for name, value in production.items():
        if name != "BACKEND_CORS_ORIGINS":
            monkeypatch.setenv(name, str(value))
    monkeypatch.setenv("BACKEND_CORS_ORIGINS", '["https://support.example.com"]')
    monkeypatch.setenv("DEBUG", "true")
    with pytest.raises(RuntimeError, match="DEBUG=false") as error:
        load_settings()
    assert SIGNING_KEY not in str(error.value)
    assert DB_PASSWORD not in str(error.value)
    assert error.value.__suppress_context__

    monkeypatch.setenv("BACKEND_CORS_ORIGINS", f"invalid-json-{SIGNING_KEY}")
    with pytest.raises(RuntimeError, match="JSON syntax") as error:
        load_settings()
    assert SIGNING_KEY not in str(error.value)


def test_log_filter_omits_credentials_and_raw_exception_chains(monkeypatch, caplog):
    monkeypatch.setattr(settings, "SECRET_KEY", SIGNING_KEY)
    monkeypatch.setattr(settings, "DATABASE_URL", DB_URL)
    logger = logging.getLogger("test.secret-safe")
    log_filter = SecretSafeLogFilter()
    logger.addFilter(log_filter)
    try:
        try:
            raise ValueError("unlabelled exception sentinel")
        except ValueError:
            logger.exception(
                "Connection failed for %s with %s, password=%s, otp_code=%s, db password %s",
                DB_URL, SIGNING_KEY, "fixture-login-password", "726491", DB_PASSWORD,
            )
    finally:
        logger.removeFilter(log_filter)
    for value in (DB_URL, SIGNING_KEY, DB_PASSWORD, "fixture-login-password", "726491", "unlabelled exception sentinel"):
        assert value not in caplog.text
    assert "Connection failed" in caplog.text
    assert "ValueError" in caplog.text
    assert "test_log_filter_omits_credentials_and_raw_exception_chains" in caplog.text


def test_configured_handlers_sanitize_propagated_records(monkeypatch, capsys):
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "DEBUG", False)
    monkeypatch.setattr(settings, "SECRET_KEY", SIGNING_KEY)
    monkeypatch.setattr(settings, "DATABASE_URL", DB_URL)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", "fixture-smtp-password")

    app_logger = logging.getLogger("ticketdesk")
    child = logging.getLogger("ticketdesk.integration")
    server_logger = logging.getLogger("uvicorn")
    access_logger = logging.getLogger("uvicorn.access")
    root_logger = logging.getLogger()
    third_party = logging.getLogger("sqlalchemy.integration")
    monkeypatch.setattr(app_logger, "handlers", [])
    monkeypatch.setattr(app_logger, "level", app_logger.level)
    monkeypatch.setattr(app_logger, "propagate", False)
    monkeypatch.setattr(server_logger, "propagate", False)
    monkeypatch.setattr(access_logger, "propagate", False)
    monkeypatch.setattr(access_logger, "level", logging.INFO)
    server_stream = io.StringIO()
    access_stream = io.StringIO()
    root_stream = io.StringIO()
    monkeypatch.setattr(server_logger, "handlers", [logging.StreamHandler(server_stream)])
    monkeypatch.setattr(root_logger, "handlers", [logging.StreamHandler(root_stream)])
    access_handler = logging.StreamHandler(access_stream)
    access_handler.setFormatter(AccessFormatter('%(request_line)s %(status_code)s'))
    monkeypatch.setattr(access_logger, "handlers", [access_handler])

    setup_logging()
    setup_logging()
    for owner in (app_logger, server_logger, access_logger, root_logger):
        assert len(owner.handlers) == 1
        assert sum(isinstance(item, SecretSafeLogFilter) for item in owner.handlers[0].filters) == 1

    cyclic = []
    cyclic.append(cyclic)
    try:
        raise RuntimeError("unlabelled-exception-sentinel")
    except RuntimeError:
        child.exception(
            "Database request failed for %s", SIGNING_KEY,
            extra={"extra_data": {
                "event": "connection_failed",
                "nested": [{"dbUrl": DB_URL, "otpCode": 826491, "accessToken": "opaque-token-sentinel"}],
                "note": f"Dependency rejected fixture-smtp-password and {DB_PASSWORD}",
                "object": object(),
                "cycle": cyclic,
            }},
        )
        logging.getLogger("uvicorn.error").error("ASGI request failed", exc_info=True)
    third_party.warning("Connection rejected, password=%s", "driver-password-sentinel")
    access_logger.info(
        '%s - "%s %s HTTP/%s" %d',
        "127.0.0.1", "GET", "/health?token=query-token-sentinel", "1.1", 200,
    )
    child.warning("Invalid metadata", extra={"extra_data": {"metric": float("nan")}})

    stdout = capsys.readouterr().out
    event, malformed_event = map(json.loads, stdout.splitlines())
    assert event["metadata"]["event"] == "connection_failed"
    assert event["metadata"]["nested"] == [{
        "dbUrl": "[redacted]", "otpCode": "[redacted]", "accessToken": "[redacted]",
    }]
    assert event["metadata"]["object"] == "[unsupported metadata]"
    assert malformed_event["metadata"] == "[unavailable metadata]"
    assert "Database request failed" in event["message"]
    assert "RuntimeError" in event["message"]
    assert "test_production_configuration.py:" in event["message"]
    assert "ASGI request failed (RuntimeError" in server_stream.getvalue()
    assert "Connection rejected, password=[redacted]" in root_stream.getvalue()
    assert "GET /health?token=[redacted] HTTP/1.1 200 OK" in access_stream.getvalue()
    output = stdout + server_stream.getvalue() + access_stream.getvalue() + root_stream.getvalue()
    for secret in (
        SIGNING_KEY, DB_URL, DB_PASSWORD, "fixture-smtp-password", "826491",
        "opaque-token-sentinel", "driver-password-sentinel", "unlabelled-exception-sentinel",
        "query-token-sentinel",
    ):
        assert secret not in output


def test_unhandled_request_logs_use_route_template_and_omit_exception_details(caplog):
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/throw/{value}")
    def error_route(value: str):
        raise RuntimeError(f"private exception value: {value}")

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/throw/route-secret-sentinel")
    assert response.status_code == 500
    assert "Unhandled error on GET /throw/{value}" in caplog.text
    assert "RuntimeError" in caplog.text
    assert "route-secret-sentinel" not in caplog.text
    assert "route-secret-sentinel" not in response.text


def test_database_errors_hide_bound_parameters():
    assert engine.hide_parameters
    if engine.dialect.name != "sqlite":
        pytest.skip("This regression check exercises the SQLite test engine.")
    with engine.connect() as connection:
        with pytest.raises(StatementError) as error:
            connection.execute(text("SELECT nonexistent_function(:value)"), {"value": "sql-secret-sentinel"})
    assert "sql-secret-sentinel" not in str(error.value)
    assert "SQL parameters hidden" in str(error.value)
