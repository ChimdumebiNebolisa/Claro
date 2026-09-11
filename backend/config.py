"""Environment configuration with production fail-closed checks."""

from __future__ import annotations

import ipaddress
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

MAX_ORIGIN_LENGTH = 512
MIN_PRODUCTION_SECRET_BYTES = 32
MIN_PRODUCTION_SECRET_UNIQUE_BYTES = 8
_HOST_LABEL = re.compile(r"^(?!-)[a-z0-9-]{1,63}(?<!-)$", re.IGNORECASE)
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class CanonicalOrigin:
    scheme: Literal["http", "https"]
    host: str
    port: int


def canonical_origin(value: str) -> CanonicalOrigin:
    """Parse one serialized HTTP origin without accepting URL-only syntax."""

    if (
        not isinstance(value, str)
        or not value
        or len(value) > MAX_ORIGIN_LENGTH
        or value == "null"
        or not value.isascii()
        or value != value.strip()
        or any(ord(character) < 0x20 or ord(character) == 0x7F for character in value)
        or any(character in value for character in ("\\", "?", "#", "[", "]", ","))
    ):
        raise ValueError("origin must be one exact HTTP(S) origin")

    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise ValueError("origin must be one exact HTTP(S) origin") from exc

    host = parsed.hostname
    if (
        parsed.scheme not in {"http", "https"}
        or host is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path
        or parsed.query
        or parsed.fragment
        or port == 0
        or ":" in host
        or host.endswith(".")
    ):
        raise ValueError("origin must be one exact HTTP(S) origin")

    normalized_host = host.casefold()
    if normalized_host.replace(".", "").isdigit():
        try:
            normalized_host = str(ipaddress.IPv4Address(normalized_host))
        except ipaddress.AddressValueError as exc:
            raise ValueError("origin must contain a valid host") from exc
    elif len(normalized_host) > 253 or any(
        _HOST_LABEL.fullmatch(label) is None for label in normalized_host.split(".")
    ):
        raise ValueError("origin must contain a valid host")

    expected_authority = normalized_host if port is None else f"{normalized_host}:{port}"
    if parsed.netloc.casefold() != expected_authority:
        raise ValueError("origin must be one exact HTTP(S) origin")

    effective_port = port or (443 if parsed.scheme == "https" else 80)
    return CanonicalOrigin(parsed.scheme, normalized_host, effective_port)


def _validate_signing_secret(secret: str, *, label: str) -> bytes:
    try:
        encoded = secret.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError(f"production {label} secret must be valid UTF-8") from exc
    if len(encoded) < MIN_PRODUCTION_SECRET_BYTES:
        raise ValueError(
            f"production {label} secret must be at least {MIN_PRODUCTION_SECRET_BYTES} UTF-8 bytes"
        )
    if len(set(encoded)) < MIN_PRODUCTION_SECRET_UNIQUE_BYTES:
        raise ValueError(f"production {label} secret must use high-entropy signing material")
    return encoded


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CLAROS_",
        extra="ignore",
    )

    environment: Literal["development", "test", "production"] = "development"
    storage_backend: Literal["local", "gcs"] = "local"
    local_storage_path: Path = Path(".local/claros-v2")
    gcs_bucket: str | None = None
    public_origin: str = "http://127.0.0.1:5173"
    owner_cookie_name: str = "claros_owner"
    cookie_secret: SecretStr = SecretStr("dev-only-change-me")
    review_token_secret: SecretStr = SecretStr("dev-only-review-secret")
    assignment_ttl_seconds: int = Field(default=86_400, ge=60, le=86_400)
    review_ttl_seconds: int = Field(default=600, ge=60, le=600)
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1)
    max_pages: int = Field(default=8, ge=1, le=8)
    max_questions: int = Field(default=40, ge=1, le=40)
    # Cloud Run is configured for 300 seconds. Keep application work inside a
    # smaller envelope so durable failure/cleanup and the HTTP response have
    # headroom before the platform terminates the request.
    request_timeout_seconds: int = Field(default=270, ge=1, le=285)
    upload_rate_limit: int = Field(default=10, ge=1, le=1_000)
    upload_rate_window_seconds: int = Field(default=3_600, ge=1, le=86_400)
    realtime_rate_limit: int = Field(default=20, ge=1, le=1_000)
    realtime_rate_window_seconds: int = Field(default=60, ge=1, le=3_600)
    pdf_engine: Literal["current", "openpdf"] = "current"
    openpdf_jar_path: Path = (
        _REPOSITORY_ROOT
        / "workers"
        / "openpdf"
        / "target"
        / "claros-openpdf-worker-0.1.0-SNAPSHOT-all.jar"
    )
    openpdf_font_root: Path = _REPOSITORY_ROOT / "assets" / "fonts" / "noto-sans"
    openpdf_qpdf_path: Path | None = None
    openpdf_java_command: str = "java"
    openpdf_jvm_heap_mib: int = Field(default=192, ge=32, le=1_024)
    openpdf_max_output_bytes: int = Field(default=64 * 1024 * 1024, ge=1)

    @field_validator("openpdf_java_command")
    @classmethod
    def validate_openpdf_java_command(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("OpenPDF Java command cannot be empty")
        return value

    @field_validator("public_origin")
    @classmethod
    def validate_public_origin(cls, value: str) -> str:
        canonical_origin(value)
        return value

    @property
    def secure_cookie(self) -> bool:
        return self.environment == "production"

    @property
    def trusted_hosts(self) -> tuple[str, ...]:
        public_host = canonical_origin(self.public_origin).host
        if self.environment == "production":
            return (public_host,)
        return tuple(dict.fromkeys((public_host, "testserver", "localhost", "127.0.0.1")))

    @model_validator(mode="after")
    def validate_production_boundaries(self) -> Settings:
        if self.environment == "production":
            if self.storage_backend != "gcs":
                raise ValueError("production requires GCS storage")
            if not self.gcs_bucket:
                raise ValueError("production requires CLAROS_GCS_BUCKET")
            cookie_secret = _validate_signing_secret(
                self.cookie_secret.get_secret_value(), label="cookie"
            )
            review_secret = _validate_signing_secret(
                self.review_token_secret.get_secret_value(), label="review token"
            )
            if cookie_secret == review_secret:
                raise ValueError("production cookie and review token secrets must be distinct")
            if canonical_origin(self.public_origin).scheme != "https":
                raise ValueError("production requires an HTTPS public origin")
        return self
