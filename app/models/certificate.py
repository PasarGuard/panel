from typing import Literal

from pydantic import BaseModel, Field, model_validator


class CertificateInspectRequest(BaseModel):
    certificate: str = Field(default="", max_length=1_048_576)
    key: str = Field(default="", max_length=65_536)
    certificate_file: str = Field(default="", max_length=4096)
    key_file: str = Field(default="", max_length=4096)
    serve_on_node: bool = False
    server_name: str = Field(default="", max_length=253)

    @model_validator(mode="after")
    def one_source(self):
        if (self.certificate or self.key) and (self.certificate_file or self.key_file):
            raise ValueError("Use certificate content or file paths, not both.")
        return self


class CertificateDetails(BaseModel):
    subject: str
    issuer: str
    domains: list[str]
    common_name: str | None
    not_before: str
    not_after: str
    fingerprint: str
    serial_number: str
    public_key_algorithm: str
    is_ca: bool
    self_signed: bool
    status: Literal["valid", "expiring", "expired", "not_yet_valid"]


class CertificateInspectResult(BaseModel):
    status: Literal["valid", "expiring", "expired", "not_yet_valid", "invalid", "unavailable", "empty"]
    certificates: list[CertificateDetails] = Field(default_factory=list)
    key_status: Literal["matched", "mismatch", "missing", "invalid", "unavailable"] = "missing"
    error: str | None = None
    key_error: str | None = None
    server_name_matches: bool | None = None
    chain_linked: bool | None = None
    checked_at: str
