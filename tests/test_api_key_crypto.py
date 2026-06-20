from app.utils.crypto import (
    API_KEY_BCRYPT_ALGORITHM,
    API_KEY_HASH_VERSION,
    api_key_trimmed,
    hash_api_key,
    verify_api_key,
)


def test_hash_api_key_uses_bcrypt_algorithm() -> None:
    raw_api_key = "pg_key_12345678-1234-4234-9234-123456789abc"

    stored_hash = hash_api_key(raw_api_key)
    version, algorithm, key_hash = stored_hash.split("$", 2)

    assert version == API_KEY_HASH_VERSION
    assert algorithm == API_KEY_BCRYPT_ALGORITHM
    assert key_hash.startswith("$2")
    assert verify_api_key(raw_api_key, stored_hash)
    assert not verify_api_key("pg_key_12345678-1234-4234-9234-123456789abd", stored_hash)


def test_verify_api_key_rejects_non_bcrypt_algorithm() -> None:
    raw_api_key = "pg_key_12345678-1234-4234-9234-123456789abc"
    stored_hash = "v2$hmac_sha256$invalid"

    assert not verify_api_key(raw_api_key, stored_hash)


def test_api_key_trimmed_uses_existing_display_shape() -> None:
    raw_api_key = "pg_key_12345678-1234-4234-9234-123456789abc"

    assert api_key_trimmed(raw_api_key) == "pg_key_123***abc"
    assert api_key_trimmed("not-an-api-key") is None
