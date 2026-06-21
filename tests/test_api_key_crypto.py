from app.utils.crypto import (
    API_KEY_BCRYPT_ALGORITHM,
    API_KEY_HASH_VERSION,
    api_key_lookup_id,
    hash_api_key,
    verify_api_key,
)

TEST_SECRET_KEY = "test-secret-key"


def test_hash_api_key_uses_bcrypt_algorithm() -> None:
    raw_api_key = "test-api-key"

    stored_hash = hash_api_key(raw_api_key, TEST_SECRET_KEY)
    version, lookup_id, algorithm, key_hash = stored_hash.split("$", 3)

    assert version == API_KEY_HASH_VERSION
    assert lookup_id == api_key_lookup_id(raw_api_key, TEST_SECRET_KEY)
    assert algorithm == API_KEY_BCRYPT_ALGORITHM
    assert key_hash.startswith("$2")
    assert verify_api_key(raw_api_key, stored_hash, TEST_SECRET_KEY)
    assert not verify_api_key("wrong-key", stored_hash, TEST_SECRET_KEY)
    assert not verify_api_key(raw_api_key, stored_hash, "wrong-secret-key")


def test_verify_api_key_rejects_non_bcrypt_algorithm() -> None:
    raw_api_key = "test-api-key"
    stored_hash = f"v2${api_key_lookup_id(raw_api_key, TEST_SECRET_KEY)}$hmac_sha256$invalid"

    assert not verify_api_key(raw_api_key, stored_hash, TEST_SECRET_KEY)
