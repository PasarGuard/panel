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
    recovered: bool = Field(default=True)
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


class OwnerNotificationEnable(UserNotificationEnable):
    """An admin's own preferences. Reminders about their users are opt-in."""

    percentage_reached: bool = Field(default=False)
    days_left: bool = Field(default=False)


class NotificationEnable(BaseModel):
    admin: AdminNotificationEnable = Field(default_factory=AdminNotificationEnable)
    admin_role: BaseNotificationEnable = Field(default_factory=BaseNotificationEnable)
    core: BaseNotificationEnable = Field(default_factory=BaseNotificationEnable)
    group: BaseNotificationEnable = Field(default_factory=BaseNotificationEnable)
    host: HostNotificationEnable = Field(default_factory=HostNotificationEnable)
    node: NodeNotificationEnable = Field(default_factory=NodeNotificationEnable)
    user: UserNotificationEnable = Field(default_factory=UserNotificationEnable)
    user_template: BaseNotificationEnable = Field(default_factory=BaseNotificationEnable)
    api_key: BaseNotificationEnable = Field(default_factory=BaseNotificationEnable)
    # Telegram/Discord reminders; webhooks have their own thresholds in the webhook settings.
    days_left: bool = Field(default=False)
    days_left_thresholds: list[int] = Field(default_factory=list)
    percentage_reached: bool = Field(default=False)
    percentage_reached_thresholds: list[int] = Field(default_factory=list)

    @field_validator("days_left_thresholds")
    @classmethod
    def validate_days_left_thresholds(cls, value: list[int]) -> list[int]:
        if any(days < 1 for days in value):
            raise ValueError("days left values must be at least 1")
        return sorted(set(value))

    @field_validator("percentage_reached_thresholds", mode="before")
    @classmethod
    def validate_percentage_reached_thresholds(cls, value):
        return ListValidator.normalize_percentage_list_input(value)
