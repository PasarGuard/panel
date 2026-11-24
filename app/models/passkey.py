from pydantic import BaseModel, Field


class PasskeyOptionsRequest(BaseModel):
    username: str | None = Field(default=None, max_length=128)


class PasskeyRegistrationRequest(BaseModel):
    credential: dict
    name: str = Field(default="This device", max_length=128)


class PasskeyInfo(BaseModel):
    id: int
    name: str


class PasskeyAuthenticationRequest(BaseModel):
    username: str | None = Field(default=None, max_length=128)
    credential: dict
