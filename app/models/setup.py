from pydantic import BaseModel


class OwnerCreateRequest(BaseModel):
    key: str
    username: str
    password: str


class OwnerResetRequest(BaseModel):
    key: str
    password: str


class OwnerDeleteRequest(BaseModel):
    key: str
