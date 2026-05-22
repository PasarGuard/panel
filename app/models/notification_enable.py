from pydantic import BaseModel, Field, field_validator

from app.models.validators import ListValidator


class BaseNotificationEnable(BaseModel):
    create: bool = Field(default=True)
    modify: bool = Field(default=True)
    delete: bool = Field(default=True)


class AdminNotificationEnable(BaseNotificationEnable):
    reset_usage: bool = Field(default=True)
    login: bool = Field(default=True)
    usage_limit_warning: bool = Field(default=True)
    usage_limit_warning_percentages: list[int] = Field(default_factory=list)

    @field_validator("usage_limit_warning_percentages", mode="before")
    @classmethod
    def validate_usage_limit_warning_percentages(cls, value):
        return ListValidator.normalize_percentage_list_input(value)


class NodeNotificationEnable(BaseNotificationEnable):
    connect: bool = Field(default=True)
    error: bool = Field(default=True)
    limited: bool = Field(default=True)
    reset_usage: bool = Field(default=True)


class HostNotificationEnable(BaseNotificationEnable):
    modify_hosts: bool = Field(default=True)


class UserNotificationEnable(BaseNotificationEnable):
    status_change: bool = Field(default=True)
    reset_data_usage: bool = Field(default=True)
    data_reset_by_next: bool = Field(default=True)
    subscription_revoked: bool = Field(default=True)


class NotificationEnable(BaseModel):
    admin: AdminNotificationEnable = Field(default_factory=AdminNotificationEnable)
    admin_role: BaseNotificationEnable = Field(default_factory=BaseNotificationEnable)
    core: BaseNotificationEnable = Field(default_factory=BaseNotificationEnable)
    group: BaseNotificationEnable = Field(default_factory=BaseNotificationEnable)
    host: HostNotificationEnable = Field(default_factory=HostNotificationEnable)
    node: NodeNotificationEnable = Field(default_factory=NodeNotificationEnable)
    user: UserNotificationEnable = Field(default_factory=UserNotificationEnable)
    user_template: BaseNotificationEnable = Field(default_factory=BaseNotificationEnable)
    days_left: bool = Field(default=True)
    percentage_reached: bool = Field(default=True)
