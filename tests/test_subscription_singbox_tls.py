from app.models.subscription import TLSConfig
from app.subscription.singbox import SingBoxConfiguration


def test_unsafe_fingerprint_uses_native_tls_in_singbox():
    tls = SingBoxConfiguration()._apply_tls(TLSConfig(tls="tls", sni="example.com", fingerprint="unsafe"))

    assert "utls" not in tls


def test_unsafe_fingerprint_falls_back_to_chrome_for_singbox_reality():
    tls = SingBoxConfiguration()._apply_tls(
        TLSConfig(
            tls="reality",
            sni="example.com",
            fingerprint="unsafe",
            reality_public_key="public-key",
            reality_short_id="12345678",
        )
    )

    assert tls["utls"] == {"enabled": True, "fingerprint": "chrome"}
