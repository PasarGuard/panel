import asyncio
import time
from base64 import b64encode
from hashlib import sha256
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import middlewares
from app.utils import jwt as jwt_utils


def _legacy_v2_token(user_id: int, secret: str) -> str:
    data_b64 = b64encode(f"v2,{user_id},{int(time.time())}".encode(), altchars=b"-_").decode().rstrip("=")
    return data_b64 + b64encode(sha256((data_b64 + secret).encode()).digest(), altchars=b"-_").decode()[:10]


@pytest.fixture
def secret(monkeypatch):
    async def fake_get_secret_key():
        return "test-secret"

    monkeypatch.setattr(jwt_utils, "get_secret_key", fake_get_secret_key)
    return "test-secret"


def test_legacy_subscription_token_rejects_bad_signatures_without_errors(secret):
    token = _legacy_v2_token(789, secret)

    assert asyncio.run(jwt_utils.get_subscription_payload(token))["user_id"] == 789
    for signature in ("A" * 10, "é" * 10):
        assert asyncio.run(jwt_utils.get_subscription_payload(token[:-10] + signature)) is None


@pytest.mark.parametrize(
    ("origins", "credentials"),
    [("*", None), ("https://panel.example.com", "true")],
)
def test_cors_credentials_only_for_explicit_origins(monkeypatch, origins, credentials):
    monkeypatch.setattr(middlewares, "cors_settings", SimpleNamespace(allowed_origins=[origins]))
    app = FastAPI()
    middlewares.setup_middleware(app)
    app.get("/ping")(lambda: {"ok": True})

    response = TestClient(app).get("/ping", headers={"Origin": "https://panel.example.com", "Cookie": "session=1"})

    assert response.headers.get("access-control-allow-credentials") == credentials
    expected_origin = "*" if origins == "*" else "https://panel.example.com"
    assert response.headers.get("access-control-allow-origin") == expected_origin
