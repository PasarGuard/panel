import re
from ipaddress import ip_address

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CertificateFingerprintRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pem: str | None = Field(
        default=None,
        min_length=1,
        max_length=1048576,
        description="PEM certificate or chain; the first certificate is used.",
    )
    file_path: str | None = Field(
        default=None,
        min_length=1,
        max_length=4096,
        description="Certificate file path on the panel server, containing PEM or DER.",
    )
    server: str | None = Field(
        default=None,
        min_length=1,
        max_length=253,
        description="TLS server hostname or IP address, without a scheme or port.",
    )
    port: int = Field(default=443, ge=1, le=65535)
    server_name: str | None = Field(
        default=None, min_length=1, max_length=253, description="Optional TLS SNI override for server probes."
    )
    timeout: float = Field(default=10, ge=1, le=20, allow_inf_nan=False)

    @field_validator("server", "server_name")
    @classmethod
    def validate_host(cls, value: str | None) -> str | None:
        if value is None:
            return value
        value = value.strip()
        try:
            ip_address(value)
            return value
        except ValueError:
            pass
        try:
            hostname = value.encode("idna").decode("ascii").rstrip(".")
        except UnicodeError as exc:
            raise ValueError("Enter a hostname or IP address without a scheme or port") from exc
        if (
            not hostname
            or len(hostname) > 253
            or any(
                not re.fullmatch(r"[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?", label)
                for label in hostname.split(".")
            )
        ):
            raise ValueError("Enter a hostname or IP address without a scheme or port")
        return hostname

    @model_validator(mode="after")
    def validate_source(self):
        if sum(value is not None for value in (self.pem, self.file_path, self.server)) != 1:
            raise ValueError("Provide exactly one of pem, file_path, or server")
        if self.server is None and self.model_fields_set & {"port", "server_name", "timeout"}:
            raise ValueError("port, server_name, and timeout are only supported with server")
        return self


class CertificateFingerprintResponse(BaseModel):
    sha256: str = Field(
        description="SHA-256 of the complete leaf certificate DER, as 64 lowercase hexadecimal characters."
    )
