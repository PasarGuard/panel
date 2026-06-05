from pydantic import BaseModel, field_validator

from app.models.validators import PasswordValidator


class BaseSetupRequest(BaseModel):
    key: str


class OwnerResetRequest(BaseSetupRequest):
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str):
        return PasswordValidator.validate_password(value)


class OwnerCreateRequest(OwnerResetRequest):
    username: str


class OwnerUpgradeRequest(BaseSetupRequest):
    username: str
