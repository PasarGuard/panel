import hashlib

from app.utils.crypto import (
    API_KEY_HASH_VERSION,
    API_KEY_SHA256_ALGORITHM,
    api_key_lookup_id,
    hash_api_key,
    verify_api_key,
)


def test_hash_api_key_uses_sha256_algorithm() -> None:
    raw_api_key = "test-api-key"

    stored_hash = hash_api_key(raw_api_key)
    version, lookup_id, algorithm, hash_hex = stored_hash.split("$")
    expected_hash = hashlib.sha256(raw_api_key.encode("utf-8")).hexdigest()

    assert version == API_KEY_HASH_VERSION
    assert lookup_id == api_key_lookup_id(raw_api_key)
    assert algorithm == API_KEY_SHA256_ALGORITHM
    assert hash_hex == expected_hash
    assert verify_api_key(raw_api_key, stored_hash)
    assert not verify_api_key("wrong-key", stored_hash)


def test_verify_api_key_rejects_non_sha256_algorithm() -> None:
    raw_api_key = "test-api-key"
    stored_hash = f"v1${api_key_lookup_id(raw_api_key)}$hmac_sha256$invalid"

    assert not verify_api_key(raw_api_key, stored_hash)
