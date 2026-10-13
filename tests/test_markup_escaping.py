"""Values that admins control must stay inert in subscription pages and notifications."""

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.db.models import DataLimitResetStrategy, UserStatus
from app.models.admin import AdminModify
from app.templates import render_template
from app.utils.helpers import has_markup_unsafe_chars


def _render_subscription_page(**context) -> str:
    user = SimpleNamespace(
        username="page_user",
        status=UserStatus.active,
        data_limit=0,
        used_traffic=0,
        data_limit_reset_strategy=DataLimitResetStrategy.no_reset,
        on_hold_expire_duration=None,
        expire=None,
        on_hold_timeout=None,
    )
    return render_template(
        "subscription/index.html",
        {"user": user, "links": [], "announce": "", "announce_url": "", "apps": []} | context,
    )


def test_subscription_page_escapes_links():
    html = _render_subscription_page(links=["vless://id@host:443#a', alert(1), '\"><img src=x onerror=1>"])

    assert "<img src=x" not in html
    assert "copyLink('" not in html
    assert 'data-link="vless://id@host:443#a&#39;, alert(1), &#39;&#34;&gt;&lt;img src=x onerror=1&gt;"' in html
    assert 'onclick="copyLink(this.dataset.link, this)"' in html


def test_subscription_page_escapes_announce_but_keeps_line_breaks():
    html = _render_subscription_page(announce="first line\n<script>alert(1)</script>")

    assert "first line<br>&lt;script&gt;alert(1)&lt;/script&gt;" in html


def test_subscription_page_escapes_app_import_url():
    app = SimpleNamespace(
        icon_url="",
        name="App",
        recommended=False,
        platform=None,
        description={"en": ""},
        download_links=[],
        import_url="app://import/');alert(1);//",
    )
    html = _render_subscription_page(apps=[app])

    assert "importConfig('" not in html
    assert 'data-url="app://import/&#39;);alert(1);//" onclick="importConfig(this.dataset.url)"' in html


@pytest.mark.parametrize("value", ["a'b", 'a"b', "a<b", "a>b", "a`b", "a\\b", "a b", "a\tb", "a\nb", "a\x00b"])
def test_has_markup_unsafe_chars_rejects(value):
    assert has_markup_unsafe_chars(value)


@pytest.mark.parametrize("value", ["example.com", "*.example.com", "{SERVER_IP}", "[2001:db8::1]", "пример.рф", ""])
def test_has_markup_unsafe_chars_allows(value):
    assert not has_markup_unsafe_chars(value)


@pytest.mark.parametrize(
    "sub_domain",
    [
        "javascript:alert(1)//",
        "JavaScript:alert(1)",
        "data:text/html,x",
        "https://sub.example.com/'x",
        "https://a b.com",
    ],
)
def test_admin_sub_domain_rejects_unsafe_values(sub_domain):
    with pytest.raises(ValidationError):
        AdminModify(sub_domain=sub_domain)


@pytest.mark.parametrize(
    "sub_domain", ["https://sub.example.com", "https://*.example.com:8443/path", "sub.example.com", "", None]
)
def test_admin_sub_domain_allows_url_prefixes(sub_domain):
    assert AdminModify(sub_domain=sub_domain).sub_domain == sub_domain


def _notification_user(group_names: list[str]):
    return SimpleNamespace(
        username="notify_user",
        admin=None,
        data_limit=0,
        expire=None,
        data_limit_reset_strategy=DataLimitResetStrategy.no_reset,
        group_names=group_names,
        next_plan=None,
    )


async def test_telegram_user_messages_escape_group_names(monkeypatch):
    from app.notification.telegram import user as telegram_user

    sent: list[str] = []

    async def fake_send(data, chat_id=None, topic_id=None):
        sent.append(data)

    async def fake_settings():
        return SimpleNamespace(notify_telegram=True)

    monkeypatch.setattr(telegram_user, "send_telegram_message", fake_send)
    monkeypatch.setattr(telegram_user, "notification_settings", fake_settings)
    monkeypatch.setattr(telegram_user, "get_telegram_channel", lambda settings, entity: (1, None))

    user = _notification_user(['<a href="https://example.com">x</a>'])
    await telegram_user.create_user(user, "owner")
    await telegram_user.modify_user(user, "owner")

    assert len(sent) == 2
    for message in sent:
        assert "<a href" not in message
        assert "&lt;a href=&quot;https://example.com&quot;&gt;x&lt;/a&gt;" in message


async def test_discord_user_messages_escape_group_names(monkeypatch):
    from app.notification.discord import user as discord_user

    sent: list[dict] = []

    async def fake_send(data, webhook):
        sent.append(data)

    async def fake_settings():
        return SimpleNamespace(notify_discord=True)

    monkeypatch.setattr(discord_user, "send_discord_webhook", fake_send)
    monkeypatch.setattr(discord_user, "notification_settings", fake_settings)
    monkeypatch.setattr(discord_user, "get_discord_webhook", lambda settings, entity: "https://discord.invalid/hook")

    user = _notification_user(["*bold*_x_"])
    await discord_user.create_user(user, "owner")
    await discord_user.modify_user(user, "owner")

    assert len(sent) == 2
    for message in sent:
        assert "\\*bold\\*\\_x\\_" in message["embeds"][0]["description"]
