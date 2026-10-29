"""Webhooks go to public http(s) destinations unless WEBHOOK_ALLOW_PRIVATE_DESTINATIONS is set."""

import asyncio
from unittest.mock import MagicMock

import pytest

from app.jobs import send_notifications as webhook_job
from app.models.settings import WebhookInfo
from app.utils.net import is_http_url, is_public_http_url, url_host_for_log
from config import ServerSettings, server_settings

PRIVATE_URL = "http://user:hunter2@10.0.0.5:8080/hook?token=SECRET#frag"


class _Response:
    status = 200

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _Client:
    def __init__(self):
        self.posted = []

    def post(self, url, **kwargs):
        self.posted.append(url)
        return _Response()


@pytest.fixture
def private_destinations_off(monkeypatch):
    monkeypatch.setattr(server_settings, "webhook_allow_private_destinations", False)


def test_flag_defaults_to_off():
    assert ServerSettings.model_fields["webhook_allow_private_destinations"].default is False


def test_webhook_destinations_must_be_public():
    assert is_public_http_url("https://1.1.1.1/hook")
    for url in (
        "http://127.0.0.1:8000/health",
        "http://localhost/hook",
        "http://10.1.2.3/hook",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/hook",
        "ftp://1.1.1.1/hook",
    ):
        assert not is_public_http_url(url), url


@pytest.mark.parametrize(
    "url",
    [
        "http://8.8.8.8:99999/hook",
        "http://" + "a" * 70 + ".com/hook",
        "http://[::1/hook",
        "http://\udcff.example/hook",
    ],
)
def test_is_public_http_url_returns_false_for_malformed_urls(url):
    assert is_public_http_url(url) is False


def test_private_webhook_is_skipped_and_logged_by_host_only(monkeypatch, private_destinations_off):
    logger = MagicMock()
    monkeypatch.setattr(webhook_job, "logger", logger)
    client = _Client()

    assert asyncio.run(webhook_job._send_webhook(client, WebhookInfo(url=PRIVATE_URL, secret="s"), [{"x": 1}])) is False
    assert client.posted == []

    logger.warning.assert_called_once()
    message, *args = logger.warning.call_args.args
    logged = message % tuple(args)
    assert "10.0.0.5" in logged
    assert "WEBHOOK_ALLOW_PRIVATE_DESTINATIONS" in logged
    for hidden in ("hunter2", "user", "SECRET", "/hook", "8080", "frag"):
        assert hidden not in logged, hidden


def test_link_local_webhook_is_skipped_without_posting(private_destinations_off):
    client = _Client()
    webhook = WebhookInfo(url="http://169.254.169.254/latest/meta-data/", secret="s")

    assert asyncio.run(webhook_job._send_webhook(client, webhook, [{"x": 1}])) is False
    assert client.posted == []


def test_send_webhook_survives_a_malformed_stored_url(private_destinations_off):
    webhook = WebhookInfo.model_construct(url="http://8.8.8.8:99999/hook", secret=None)
    assert asyncio.run(webhook_job._send_webhook(object(), webhook, [{"x": 1}])) is False


def test_private_webhook_is_sent_when_allowed(monkeypatch):
    monkeypatch.setattr(server_settings, "webhook_allow_private_destinations", True)

    def must_not_resolve(url):
        raise AssertionError("the destination check is off when private destinations are allowed")

    monkeypatch.setattr(webhook_job, "is_public_http_url", must_not_resolve)
    client = _Client()

    assert asyncio.run(webhook_job._send_webhook(client, WebhookInfo(url=PRIVATE_URL, secret="s"), [{"x": 1}])) is True
    assert client.posted == [PRIVATE_URL]


@pytest.mark.parametrize(
    "url, host",
    [
        ("https://hooks.example.com/a?b=c", "hooks.example.com"),
        ("http://[::1]:9000/x", "::1"),
        ("http://[::1/x", "<invalid>"),
        ("not a url", "<invalid>"),
    ],
)
def test_url_host_for_log(url, host):
    assert url_host_for_log(url) == host


@pytest.mark.parametrize("url", ["ftp://10.0.0.5/hook", "not a url", "http:///hook", "http://[::1/hook"])
def test_http_url_check_used_when_private_destinations_are_allowed(url):
    assert is_http_url(url) is False


def test_http_url_check_accepts_private_http_destinations():
    assert is_http_url("http://10.0.0.5:5000/hook") is True
