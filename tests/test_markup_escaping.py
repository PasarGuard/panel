"""Values that admins control must stay inert in subscription pages and notifications."""

import re
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.db.models import AdminStatus, DataLimitResetStrategy, UserStatus
from app.models.admin import AdminModify
from app.models.group import GroupResponse
from app.models.node import NodeNotification
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


_TELEGRAM_TAGS = re.compile(r"</?(b|i|u|s|code|pre|a|blockquote|tg-spoiler)(\s[^>]*)?>")


def _raw_markup(text: str) -> list[str]:
    """What Telegram's HTML parser rejects: '<' outside supported tags, or '&' that starts no entity."""
    text = _TELEGRAM_TAGS.sub("", text)
    return re.findall(r"<.{0,12}", text) + re.findall(r"&(?![a-zA-Z]+;|#\d+;|#x[0-9a-fA-F]+;)", text)


def _capture_telegram(monkeypatch, module) -> list[str]:
    sent: list[str] = []

    async def fake_send(data, chat_id=None, topic_id=None):
        sent.append(data)

    async def fake_settings():
        return SimpleNamespace(notify_telegram=True)

    monkeypatch.setattr(module, "send_telegram_message", fake_send)
    monkeypatch.setattr(module, "notification_settings", fake_settings)
    monkeypatch.setattr(module, "get_telegram_channel", lambda settings, entity: (1, None))
    return sent


async def test_telegram_group_messages_escape_fallback_inbound_tags(monkeypatch):
    from app.notification.telegram import group as telegram_group

    sent = _capture_telegram(monkeypatch, telegram_group)
    # XRayConfig names fallback inbounds "<inbound><=><fallback>".
    group = GroupResponse(id=1, name="all", inbound_tags=["VLESS TCP", "VLESS TCP<=>VLESS WS"])
    await telegram_group.create_group(group, "owner")
    await telegram_group.modify_group(group, "owner")

    assert len(sent) == 2
    for message in sent:
        assert _raw_markup(message) == []
        assert "VLESS TCP, VLESS TCP&lt;=&gt;VLESS WS" in message


async def test_telegram_admin_messages_escape_role_name_and_client_ip(monkeypatch):
    from app.notification.telegram import admin as telegram_admin

    sent = _capture_telegram(monkeypatch, telegram_admin)
    admin = SimpleNamespace(
        username="reseller", role=SimpleNamespace(name="<b>Resellers & co"), status=AdminStatus.active, used_traffic=0
    )
    await telegram_admin.create_admin(admin, "owner")
    await telegram_admin.modify_admin(admin, "owner")
    await telegram_admin.admin_login("reseller", "secret", "<x", success=False)

    assert len(sent) == 3
    for message in sent:
        assert _raw_markup(message) == []
    assert "&lt;b&gt;Resellers &amp; co" in sent[0]
    assert "<code>&lt;x</code>" in sent[2]


async def test_telegram_node_messages_escape_reported_values(monkeypatch):
    from app.notification.telegram import node as telegram_node

    sent = _capture_telegram(monkeypatch, telegram_node)
    reported = NodeNotification(id=1, name="node", node_version="1.0 <beta>", xray_version="26 & up")
    await telegram_node.connect_node(reported)
    await telegram_node.recovered_node(reported)
    node = SimpleNamespace(id=1, name="node", address="<edge>", port=62050)
    await telegram_node.create_node(node, "owner")
    await telegram_node.modify_node(node, "owner")

    assert len(sent) == 4
    for message in sent:
        assert _raw_markup(message) == []
    assert "1.0 &lt;beta&gt;" in sent[0] and "26 &amp; up" in sent[0]
    assert "&lt;edge&gt;" in sent[2]


def _bot_user(**fields):
    user = SimpleNamespace(
        username="alice",
        status=UserStatus.active,
        data_limit=None,
        used_traffic=0,
        data_limit_reset_strategy=DataLimitResetStrategy.no_reset,
        expire=None,
        on_hold_timeout=None,
        on_hold_expire_duration=None,
        online_at=None,
        admin=SimpleNamespace(username="a<b", telegram_id=7),
        note=None,
        subscription_url="https://example.com/sub/token?a=1&b=2",
    )
    user.__dict__.update(fields)
    return user


def test_bot_user_details_escape_group_and_admin_names():
    from app.telegram.utils.texts import Message as Texts

    text = Texts.user_details(_bot_user(), [SimpleNamespace(name="R&D <test>")])

    assert _raw_markup(text) == []
    assert "<code>R&amp;D &lt;test&gt;</code>" in text
    assert ">a&lt;b</a>" in text


def test_bot_client_user_details_escape_subscription_url():
    from app.telegram.utils.texts import Message as Texts

    text = Texts.client_user_details(_bot_user())

    assert _raw_markup(text) == []
    assert "token?a=1&amp;b=2" in text


async def test_telegram_group_messages_accept_a_group_without_inbound_tags(monkeypatch):
    from app.notification.telegram import group as telegram_group

    sent = _capture_telegram(monkeypatch, telegram_group)
    group = GroupResponse(id=2, name="empty", inbound_tags=None)
    await telegram_group.create_group(group, "owner")
    await telegram_group.modify_group(group, "owner")

    assert len(sent) == 2
    assert all("None" not in message for message in sent)
