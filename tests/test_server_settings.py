import pytest
from pydantic import ValidationError

from config import ServerSettings


@pytest.mark.parametrize(
    "explicit,platform,expected", [(None, None, 8000), (None, "9000", 9000), ("8080", "9000", 8080)]
)
def test_server_port_precedence(monkeypatch, explicit, platform, expected):
    for key, value in [("UVICORN_PORT", explicit), ("PORT", platform)]:
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    assert ServerSettings(_env_file=None).port == expected


@pytest.mark.parametrize("port", [0, 65536, -1])
def test_server_rejects_invalid_port(port):
    with pytest.raises(ValidationError):
        ServerSettings(_env_file=None, UVICORN_PORT=port)


def test_plain_http_is_explicit_opt_in(monkeypatch):
    monkeypatch.delenv("UVICORN_ALLOW_INSECURE_HTTP", raising=False)
    assert ServerSettings(_env_file=None).allow_insecure_http is False
    assert ServerSettings(_env_file=None, UVICORN_ALLOW_INSECURE_HTTP="true").allow_insecure_http is True


@pytest.mark.parametrize("provided", ["UVICORN_SSL_CERTFILE", "UVICORN_SSL_KEYFILE"])
def test_partial_tls_configuration_is_rejected(monkeypatch, provided):
    monkeypatch.delenv("UVICORN_SSL_CERTFILE", raising=False)
    monkeypatch.delenv("UVICORN_SSL_KEYFILE", raising=False)
    with pytest.raises(ValidationError, match="configured together"):
        ServerSettings(_env_file=None, **{provided: "/missing.pem"})


def test_complete_tls_pair_is_accepted():
    settings = ServerSettings(_env_file=None, UVICORN_SSL_CERTFILE="/cert.pem", UVICORN_SSL_KEYFILE="/key.pem")
    assert settings.has_ssl
