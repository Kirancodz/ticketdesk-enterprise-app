import json
from ipaddress import ip_address
from pathlib import Path
import re
from typing import List, Literal, Union
from urllib.parse import urlsplit
from pydantic import ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict, SettingsError
from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


DEVELOPMENT_SECRET_KEY = "change-this-in-production-to-a-secure-256-bit-hex-secret-key-0987654321"
DEVELOPMENT_DB_PASSWORD = "ticketdesk_secret"
COMMON_SECRET_PLACEHOLDERS = ("change-this", "changeme", "replace-me", "your-secret")


def is_production_origin(origin: str) -> bool:
    if not origin.startswith("https://") or any(
        char.isspace() or char in "/*?#@\\" for char in origin[len("https://"):]
    ):
        return False
    try:
        parsed = urlsplit(origin)
        host = parsed.hostname
        port = parsed.port
    except ValueError:
        return False
    if parsed.scheme != "https" or not host or origin.endswith(":") or port == 0:
        return False
    authority = f"[{host}]" if ":" in host else host
    if parsed.netloc.lower() != (authority if port is None else f"{authority}:{port}"):
        return False
    if host.rstrip(".") == "localhost" or host.rstrip(".").endswith(".localhost"):
        return False
    try:
        address = ip_address(host)
    except ValueError:
        return bool(re.fullmatch(
            r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?",
            host,
        ))
    return not (address.is_loopback or address.is_unspecified)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        hide_input_in_errors=True,
    )

    APP_NAME: str = "TicketDesk Enterprise"
    APP_ENV: Literal["development", "test", "verification", "production"] = "development"
    DEBUG: bool = True
    API_V1_STR: str = "/api/v1"

    # Security & JWT
    SECRET_KEY: str = DEVELOPMENT_SECRET_KEY
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    ALGORITHM: str = "HS256"

    # PostgreSQL Database
    POSTGRES_SERVER: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "ticketdesk"
    POSTGRES_PASSWORD: str = DEVELOPMENT_DB_PASSWORD
    POSTGRES_DB: str = "ticketdesk_db"
    DATABASE_URL: str = "postgresql+psycopg://ticketdesk:ticketdesk_secret@localhost:5432/ticketdesk_db"

    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]

    @field_validator("BACKEND_CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> Union[List[str], str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, str) and v.startswith("["):
            return json.loads(v)
        return v

    # File Storage Configuration (local | s3)
    STORAGE_PROVIDER: str = "local"
    LOCAL_UPLOAD_DIR: str = str(Path(__file__).resolve().parent.parent.parent / "uploads")
    MAX_UPLOAD_SIZE_MB: int = 10
    ALLOWED_EXTENSIONS: str = "pdf,png,jpg,jpeg,txt"

    # AWS S3 Settings
    AWS_REGION: str = "us-east-1"
    S3_BUCKET_NAME: str = "ticketdesk-enterprise-attachments"
    S3_PRESIGNED_URL_EXPIRATION: int = 3600

    # Optional SMTP Settings
    SMTP_ENABLED: bool = False
    SMTP_HOST: str = "smtp.example.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM_EMAIL: str = "noreply@ticketdesk.enterprise"

    @model_validator(mode="after")
    def validate_production(self) -> "Settings":
        if self.APP_ENV != "production":
            return self

        key = self.SECRET_KEY
        if (
            "SECRET_KEY" not in self.model_fields_set
            or key == DEVELOPMENT_SECRET_KEY
            or key != key.strip()
            or len(key.encode("utf-8")) < 32
            or len(set(key)) < 12
            or key.lower().startswith(COMMON_SECRET_PLACEHOLDERS)
            or key.lower().startswith(("abcdefghijklmnopqrstuvwxyz", "1234567890", "qwertyuiop"))
        ):
            raise ValueError("Production requires an explicit SECRET_KEY without known weak patterns.")

        if "DATABASE_URL" not in self.model_fields_set:
            raise ValueError("Production requires an explicit PostgreSQL DATABASE_URL.")
        try:
            database = make_url(self.DATABASE_URL)
        except (ArgumentError, ValueError):
            raise ValueError("Production requires a valid PostgreSQL DATABASE_URL.") from None

        password = database.password or ""
        if (
            database.get_backend_name() != "postgresql"
            or not all((database.host, database.database, database.username))
            or len(password) < 12
            or password.lower() in {DEVELOPMENT_DB_PASSWORD, database.username.lower()}
            or password.lower().startswith(COMMON_SECRET_PLACEHOLDERS)
            or {"user", "password", "passfile", "service", "servicefile"}.intersection(database.query)
            or (
                "POSTGRES_PASSWORD" in self.model_fields_set
                and self.POSTGRES_PASSWORD.lower() == DEVELOPMENT_DB_PASSWORD
            )
        ):
            raise ValueError("Production DATABASE_URL requires explicit, non-default PostgreSQL credentials.")
        if self.DEBUG:
            raise ValueError("Production requires DEBUG=false.")
        if (
            "BACKEND_CORS_ORIGINS" not in self.model_fields_set
            or not all(is_production_origin(origin) for origin in self.BACKEND_CORS_ORIGINS)
        ):
            raise ValueError("Production BACKEND_CORS_ORIGINS must be an explicit list of HTTPS origins or [].")
        return self

    @property
    def allowed_extensions_set(self) -> set[str]:
        return {ext.strip().lower() for ext in self.ALLOWED_EXTENSIONS.split(",") if ext.strip()}

    @property
    def max_upload_size_bytes(self) -> int:
        return self.MAX_UPLOAD_SIZE_MB * 1024 * 1024


def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        # Error inputs and contexts can contain the entire settings dictionary.
        details = "; ".join(
            f"{'.'.join(map(str, error['loc'])) or 'settings'}: {error['msg']}"
            for error in exc.errors(include_input=False, include_context=False, include_url=False)
        )
        raise RuntimeError(f"Invalid TicketDesk configuration: {details}") from None
    except SettingsError:
        raise RuntimeError("Invalid TicketDesk configuration. Check environment variable and JSON syntax.") from None


settings = load_settings()
