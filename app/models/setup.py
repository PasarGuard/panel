from pydantic import BaseModel


class BaseSetupRequest(BaseModel):
    key: str


class OwnerDeleteRequest(BaseSetupRequest):
    pass


class OwnerResetRequest(BaseSetupRequest):
    password: str


class OwnerCreateRequest(OwnerResetRequest):
    username: str


class OwnerUpgradeRequest(BaseSetupRequest):
    username: str
