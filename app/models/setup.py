from pydantic import BaseModel


class BaseSetupRequest(BaseModel):
    key: str


class OwnerResetRequest(BaseSetupRequest):
    password: str


class OwnerCreateRequest(OwnerResetRequest):
    username: str


class OwnerUpgradeRequest(BaseSetupRequest):
    username: str
