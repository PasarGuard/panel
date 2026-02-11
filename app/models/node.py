import re
from enum import Enum
from ipaddress import ip_address
from uuid import UUID

from cryptography.x509 import load_pem_x509_certificate
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.db.models import DataLimitResetStrategy, NodeConnectionType, NodeStatus

# Basic PEM format validation
CERT_PATTERN = r"-----BEGIN CERTIFICATE-----(.*?)-----END CERTIFICATE-----"
KEY_PATTERN = r"-----BEGIN (?:RSA )?PRIVATE KEY-----"

SECONDS_IN_DAY = 86400
SECONDS_IN_WEEK = 604800
SECONDS_IN_MONTH = 2678400  # 31 days
SECONDS_IN_YEAR = 31536000  # 365 days


class UsageTable(str, Enum):
    node_user_usages = "node_user_usages"
    node_usages = "node_usages"


class GeoFilseRegion(str, Enum):
    iran = "iran"
    china = "china"
    russia = "russia"


class NodeSettings(BaseModel):
    min_node_version: str = "v1.0.0"


class Node(BaseModel):
    name: str
    address: str
    port: int = 62050
    api_port: int = 62051
    usage_coefficient: float = Field(gt=0, default=1.0)
    connection_type: NodeConnectionType
    server_ca: str
    keep_alive: int
    core_config_id: int
    api_key: str
    data_limit: int = Field(default=0)
    data_limit_reset_strategy: DataLimitResetStrategy = Field(default=DataLimitResetStrategy.no_reset)
    reset_time: int = Field(default=-1)
    default_timeout: int = Field(default=10, ge=3, le=60)
    internal_timeout: int = Field(default=15, ge=3, le=60)


class NodeCreate(Node):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "DE node",
                "address": "192.168.1.1",
                "port": 62050,
                "usage_coefficient": 1,
                "server_ca": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
                "connection_type": "grpc",
                "keep_alive": 60,
                "core_config_id": 1,
                "api_key": "valid uuid",
            }
        }
    )

    @field_validator("address")
    @classmethod
    def validate_address(cls, v: str) -> str:
        if not v:
            return v
        try:
            ip_address(v)
            return v
        except ValueError:
            # Regex for domain validation
            if re.match(r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,14}$", v):
                return v
            raise ValueError("Invalid address format, must be a valid IPv4/IPv6 or domain")

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not v:
            return v
        if not 1 <= v <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        return v

    @field_validator("server_ca")
    @classmethod
    def validate_certificate(cls, v: str | None) -> str | None:
        if v is None:
            return None

        v = v.strip()

        # Check for PEM certificate format
        if not re.search(CERT_PATTERN, v, re.DOTALL):
            raise ValueError("Invalid certificate format - must contain PEM certificate blocks")

        # Check for private key material
        if re.search(KEY_PATTERN, v):
            raise ValueError("Certificate contains private key material")

        if len(v) > 2048:
            raise ValueError("Certificate too large (max 2048 characters)")

        try:
            load_pem_x509_certificate(v.encode("utf-8"))
            pass
        except Exception:
            raise ValueError("Invalid certificate structure")

        return v

    @field_validator("api_key", mode="before")
    @classmethod
    def validate_api_key(cls, v) -> str:
        if not v:
            return
        try:
            UUID(v)
        except ValueError:
            raise ValueError("Invalid UUID format for api_key")
        return v

    @model_validator(mode="after")
    def validate_reset_time_for_strategy(self):
        if self.data_limit_reset_strategy is None:
            return self

        # Skip validation for no_reset strategy or -1 (interval-based)
        if self.data_limit_reset_strategy == DataLimitResetStrategy.no_reset or self.reset_time == -1:
            return self

        # Define max values for each strategy
        max_values = {
            DataLimitResetStrategy.day: SECONDS_IN_DAY,
            DataLimitResetStrategy.week: SECONDS_IN_WEEK,
            DataLimitResetStrategy.month: SECONDS_IN_MONTH,
            DataLimitResetStrategy.year: SECONDS_IN_YEAR,
        }

        max_value = max_values.get(self.data_limit_reset_strategy)
        if max_value and self.reset_time >= max_value:
            raise ValueError(
                f"reset_time must be less than {max_value} for {self.data_limit_reset_strategy.value} strategy, "
                f"got {self.reset_time}"
            )

        return self


class NodeModify(NodeCreate):
    name: str | None = Field(default=None)
    address: str | None = Field(default=None)
    port: int | None = Field(default=None)
    status: NodeStatus | None = Field(default=None)
    usage_coefficient: float | None = Field(default=None)
    server_ca: str | None = Field(default=None)
    connection_type: NodeConnectionType | None = Field(default=None)
    keep_alive: int | None = Field(default=None)
    core_config_id: int | None = Field(default=None)
    api_key: str | None = Field(default=None)
    data_limit: int | None = None
    data_limit_reset_strategy: DataLimitResetStrategy | None = None
    reset_time: int | None = None
    default_timeout: int | None = Field(default=None, ge=3, le=60)
    internal_timeout: int | None = Field(default=None, ge=3, le=60)

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "DE node",
                "address": "192.168.1.1",
                "port": 62050,
                "status": "disabled",
                "usage_coefficient": 1.0,
                "connection_type": "grpc",
                "server_ca": "-----BEGIN CERTIFICATE-----\n...\n-----END CERTIFICATE-----",
                "keep_alive": 60,
                "core_config_id": 1,
                "api_key": "valid uuid",
            }
        }
    )


class NodeResponse(Node):
    id: int
    api_key: str | None
    core_config_id: int | None
    xray_version: str | None
    node_version: str | None
    status: NodeStatus
    message: str | None
    uplink: int = 0
    downlink: int = 0
    lifetime_uplink: int | None = None
    lifetime_downlink: int | None = None

    model_config = ConfigDict(from_attributes=True)


class NodesResponse(BaseModel):
    nodes: list[NodeResponse]
    total: int


class NodeSimple(BaseModel):
    """Lightweight node model with only id and name for performance."""

    id: int
    name: str
    model_config = ConfigDict(from_attributes=True)


class NodesSimpleResponse(BaseModel):
    """Response model for lightweight node list."""

    nodes: list[NodeSimple]
    total: int


class NodeNotification(BaseModel):
    """Lightweight node model for sending notifications without database fetch."""

    id: int
    name: str
    xray_version: str | None = None
    node_version: str | None = None
    message: str | None = None

    model_config = ConfigDict(from_attributes=True)


class UserIPList(BaseModel):
    """User IP list - mapping of IP addresses to connection counts"""

    ips: dict[str, int]  # {ip_address: connection_count}


class UserIPListAll(BaseModel):
    """User IP lists for all nodes"""

    nodes: dict[int, UserIPList | None]  # {node_id: UserIPList | None}


class NodeCoreUpdate(BaseModel):
    core_version: str = Field(default="latest", pattern=r"^(latest|v?\d+\.\d+\.\d+)$", examples=["v25.8.31"])


class NodeGeoFilesUpdate(BaseModel):
    region: GeoFilseRegion = Field(default=GeoFilseRegion.iran, examples=["iran"])
