import json
import logging
import re
import sys
from datetime import datetime, timezone
from traceback import walk_tb
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError
from app.core.config import settings


_DATABASE_URL = re.compile(r"(?i)\bpostgres(?:ql)?(?:\+[\w]+)?://[^\s]+")
_JWT = re.compile(r"\beyJ[\w-]+\.[\w-]+\.[\w-]+\b")
_CREDENTIAL = re.compile(
    r"""(?i)(\b(?:[\w-]*password|secret_key|[\w-]*token|api_key|otp(?:_code)?)\b["']?\s*[:=]\s*)"""
    r"""(?:"[^"]*"|'[^']*'|[^\s,;]+)"""
)
_SENSITIVE_METADATA_KEY = re.compile(
    r"(?:password|passwd|secret|token|otp|databaseurl|dburl|dsn|authorization|apikey|credential)"
)
_LOG_NAMESPACES = ("ticketdesk", "uvicorn", "sqlalchemy", "boto3", "botocore")


class SecretSafeLogFilter(logging.Filter):
    def __init__(self) -> None:
        super().__init__()
        try:
            database_password = make_url(settings.DATABASE_URL).password
        except (ArgumentError, ValueError):
            database_password = None
        self.secrets = tuple(sorted(filter(None, (
            settings.SECRET_KEY,
            settings.POSTGRES_PASSWORD,
            settings.SMTP_PASSWORD,
            settings.DATABASE_URL,
            database_password,
        )), key=len, reverse=True))

    def redact(self, value: str) -> str:
        value = _DATABASE_URL.sub("[redacted database URL]", value)
        value = _JWT.sub("[redacted token]", value)
        value = _CREDENTIAL.sub(r"\1[redacted]", value)
        for secret in self.secrets:
            value = value.replace(secret, "[redacted]")
        return value

    def sanitize_metadata(self, value: object, depth: int = 0) -> object:
        if depth >= 10:
            return "[metadata depth limit]"
        if type(value) is dict:
            cleaned = {}
            for key, item in value.items():
                if type(key) is not str:
                    continue
                normalized_key = re.sub(r"[^a-z0-9]", "", key.lower())
                cleaned[self.redact(key)] = (
                    "[redacted]" if _SENSITIVE_METADATA_KEY.search(normalized_key)
                    else self.sanitize_metadata(item, depth + 1)
                )
            return cleaned
        if type(value) in (list, tuple):
            return [self.sanitize_metadata(item, depth + 1) for item in value]
        if type(value) is str:
            return self.redact(value)
        if value is None or type(value) in (bool, int, float):
            return value
        return "[unsupported metadata]"

    def filter(self, record: logging.LogRecord) -> bool:
        if getattr(record, "_ticketdesk_sanitized", False):
            return True
        message = record.getMessage()
        if message.startswith("[OTP AUTHENTICATOR]"):
            message = "Password reset verification code generated"
        # Existing startup and storage callers embed raw driver exception text.
        for event in (
            "Database initialization/seeding error",
            "Health check DB error",
            "S3 upload failed",
            "S3 download failed",
            "Failed to generate presigned URL",
        ):
            if message.startswith(event):
                message = event
                break

        if record.exc_info and record.exc_info[0]:
            exception_type, _, traceback = record.exc_info
            location = ""
            for frame, line in walk_tb(traceback):
                location = f" at {frame.f_code.co_filename}:{line} in {frame.f_code.co_name}"
            message = f"{message} ({exception_type.__name__}{location})"
        if record.name == "uvicorn.access" and isinstance(record.args, tuple) and len(record.args) == 5:
            # Uvicorn's access formatter unpacks the original five fields.
            record.args = tuple(self.redact(arg) if isinstance(arg, str) else arg for arg in record.args)
        else:
            record.msg = self.redact(message)
            record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        if hasattr(record, "extra_data"):
            record.extra_data = self.sanitize_metadata(record.extra_data)
        record._ticketdesk_sanitized = True
        return True


class StructuredFormatter(logging.Formatter):
    """JSON-compatible structured log formatter suitable for AWS CloudWatch and local logs."""

    def format(self, record: logging.LogRecord) -> str:
        log_record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "environment": settings.APP_ENV,
        }
        if hasattr(record, "extra_data"):
            log_record["metadata"] = (
                record.extra_data if getattr(record, "_ticketdesk_sanitized", False)
                else "[unavailable metadata]"
            )
        try:
            return json.dumps(log_record, allow_nan=False)
        except (TypeError, ValueError, OverflowError):
            log_record["metadata"] = "[unavailable metadata]"
            return json.dumps(log_record)


def setup_logging() -> logging.Logger:
    root_logger = logging.getLogger("ticketdesk")
    root_logger.setLevel(logging.DEBUG if settings.DEBUG else logging.INFO)
    if not root_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        if settings.APP_ENV == "production":
            handler.setFormatter(StructuredFormatter())
        else:
            formatter = logging.Formatter(
                "[%(asctime)s] %(levelname)-8s %(name)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    # A parent logger's filters do not run on propagated records. Cover the
    # configured console handlers, including Uvicorn's non-propagating handlers.
    handlers = set(logging.getLogger().handlers)
    for name, configured_logger in logging.Logger.manager.loggerDict.copy().items():
        if isinstance(configured_logger, logging.Logger) and any(
            name == namespace or name.startswith(f"{namespace}.") for namespace in _LOG_NAMESPACES
        ):
            handlers.update(configured_logger.handlers)
    log_filter = SecretSafeLogFilter()
    for handler in handlers:
        if not any(isinstance(installed, SecretSafeLogFilter) for installed in handler.filters):
            handler.addFilter(log_filter)

    return root_logger


logger = setup_logging()
