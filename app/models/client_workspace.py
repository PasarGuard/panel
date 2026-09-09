from typing import Any, Literal

from pydantic import BaseModel, Field

from app.models.client_template import ClientTemplateCreate, ClientTemplateResponse
from app.models.settings import Subscription


class ClientWorkspaceTemplate(ClientTemplateCreate):
    id: int | None = Field(default=None, ge=1)


class ClientWorkspaceApply(BaseModel):
    expected_revision: str = Field(min_length=1)
    template: ClientWorkspaceTemplate | None = None
    rules: list[dict[str, Any]]
    bind_rule_indices: list[int] = Field(default_factory=list)


class ClientWorkspacePreview(ClientWorkspaceApply):
    user_id: int = Field(ge=1)
    user_agent: str = Field(max_length=1024)


class ClientWorkspaceResponse(BaseModel):
    revision: str
    subscription: Subscription
    templates: list[ClientTemplateResponse]
    sync_warning: Literal["worker_notification_failed"] | None = None
