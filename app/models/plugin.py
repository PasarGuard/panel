from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class PluginStatus(StrEnum):
    loaded = "loaded"
    failed = "failed"


class PluginResponse(BaseModel):
    id: str
    name: str
    version: str = ""
    description: str = ""
    status: PluginStatus
    error: str | None = None
    has_ui: bool = False
    settings_schema: dict[str, Any] | None = None


class PluginsResponse(BaseModel):
    plugins: list[PluginResponse] = Field(default_factory=list)
