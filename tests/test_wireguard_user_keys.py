"""User WireGuard public keys are stored in canonical base64, so the panel and node compare them as one key."""

from __future__ import annotations

import string

import pytest
from pydantic import ValidationError

from app.models.proxy import ProxyTable
from app.models.user import UserCreate, UserModify
from app.utils.crypto import generate_wireguard_keypair

_B64_ALPHABET = string.ascii_uppercase + string.ascii_lowercase + string.digits + "+/"


def _non_canonical(key: str) -> str:
    """Same 32 bytes, but with the two unused bits of the last base64 digit set (decoders ignore them)."""
    index = _B64_ALPHABET.index(key[42])
    assert index % 4 == 0
    return key[:42] + _B64_ALPHABET[index + 1] + key[43:]


def _create(wireguard: dict) -> UserCreate:
    return UserCreate(username="wg_user", group_ids=[1], proxy_settings={"wireguard": wireguard})


def test_non_canonical_public_key_is_stored_canonical():
    private_key, public_key = generate_wireguard_keypair()
    twin = _non_canonical(public_key)
    assert twin != public_key

    assert _create({"public_key": twin}).proxy_settings.wireguard.public_key == public_key
    assert _create({"private_key": private_key, "public_key": twin}).proxy_settings.wireguard.public_key == public_key
    assert UserModify(
        proxy_settings={"wireguard": {"public_key": f" {twin} "}}
    ).proxy_settings.wireguard.public_key == (public_key)


def test_public_key_alone_and_derived_public_key_still_work():
    private_key, public_key = generate_wireguard_keypair()
    assert _create({"public_key": public_key}).proxy_settings.wireguard.private_key is None
    assert _create({"private_key": private_key}).proxy_settings.wireguard.public_key == public_key


@pytest.mark.parametrize("public_key", ["not-a-key", "AAAA", "A" * 43 + "=" + "A"])
def test_invalid_public_key_is_rejected_on_input(public_key):
    with pytest.raises(ValidationError, match="public_key"):
        _create({"public_key": public_key})


def test_public_key_that_does_not_match_private_key_is_rejected():
    private_key, _ = generate_wireguard_keypair()
    _, other_public_key = generate_wireguard_keypair()
    with pytest.raises(ValidationError, match="does not match"):
        _create({"private_key": private_key, "public_key": other_public_key})


def test_stored_keys_still_load_for_responses():
    _, public_key = generate_wireguard_keypair()
    # Responses validate stored rows through ProxyTable: an old non-canonical key is shown canonical,
    # and a value accepted before keys were checked must not break loading the user.
    assert ProxyTable.model_validate(
        {"wireguard": {"public_key": _non_canonical(public_key)}}
    ).wireguard.public_key == (public_key)
    assert ProxyTable.model_validate({"wireguard": {"public_key": " legacy "}}).wireguard.public_key == "legacy"
