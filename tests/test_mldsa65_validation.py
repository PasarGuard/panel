import base64

import pytest

from app.core.xray import XRayConfig
from app.utils.crypto import (
    MLDSA65_SEED_LENGTH,
    MLDSA65_VERIFY_LENGTH,
    validate_mldsa65_seed,
    validate_mldsa65_verify,
)


def _b64url(length: int) -> str:
    return base64.urlsafe_b64encode(b"\x01" * length).decode().rstrip("=")


def test_validate_mldsa65_seed_accepts_32_bytes() -> None:
    seed = _b64url(MLDSA65_SEED_LENGTH)
    assert validate_mldsa65_seed(seed) == seed


def test_validate_mldsa65_seed_rejects_wrong_length() -> None:
    with pytest.raises(ValueError, match="mldsa65Seed length"):
        validate_mldsa65_seed(_b64url(16))


def test_validate_mldsa65_verify_accepts_1952_bytes() -> None:
    verify = _b64url(MLDSA65_VERIFY_LENGTH)
    assert validate_mldsa65_verify(verify) == verify


def test_validate_mldsa65_verify_rejects_wrong_length() -> None:
    with pytest.raises(ValueError, match="mldsa65Verify length"):
        validate_mldsa65_verify(_b64url(32))


def _reality_inbound(*, seed: str | None = None, verify: str | None = None) -> dict:
    reality = {
        "serverNames": ["www.example.com"],
        "privateKey": "MMX7m0Mj3faUstoEm5NBdegeXkHG6ZB78xzBv2n3ZUA",
        "shortIds": ["6ba85179e30d4fc2"],
    }
    if seed is not None:
        reality["mldsa65Seed"] = seed
    if verify is not None:
        reality["mldsa65Verify"] = verify
    return {
        "tag": "vless-reality",
        "listen": "0.0.0.0",
        "port": 443,
        "protocol": "vless",
        "settings": {"clients": [], "decryption": "none"},
        "streamSettings": {
            "network": "tcp",
            "security": "reality",
            "realitySettings": reality,
        },
    }


def test_xray_config_rejects_mldsa65_verify_without_seed() -> None:
    config = {
        "inbounds": [_reality_inbound(verify=_b64url(MLDSA65_VERIFY_LENGTH))],
        "outbounds": [{"protocol": "freedom", "tag": "DIRECT"}],
    }
    with pytest.raises(ValueError, match="mldsa65Verify is set without mldsa65Seed"):
        XRayConfig(config)


def test_xray_config_accepts_matching_length_mldsa65_pair() -> None:
    seed = _b64url(MLDSA65_SEED_LENGTH)
    verify = _b64url(MLDSA65_VERIFY_LENGTH)
    config = {
        "inbounds": [_reality_inbound(seed=seed, verify=verify)],
        "outbounds": [{"protocol": "freedom", "tag": "DIRECT"}],
    }
    parsed = XRayConfig(config)
    assert parsed.inbounds_by_tag["vless-reality"]["mldsa65Verify"] == verify


def test_xray_config_accepts_seed_only_mldsa65() -> None:
    seed = _b64url(MLDSA65_SEED_LENGTH)
    config = {
        "inbounds": [_reality_inbound(seed=seed)],
        "outbounds": [{"protocol": "freedom", "tag": "DIRECT"}],
    }
    parsed = XRayConfig(config)
    assert parsed.inbounds_by_tag["vless-reality"].get("mldsa65Verify") is None
