from unittest.mock import AsyncMock, MagicMock

import pytest
from aiorwlock import RWLock

from app.db.models import Settings

from . import TestSession, client


@pytest.fixture(autouse=True)
def mock_db_session(monkeypatch: pytest.MonkeyPatch):
    db_session = MagicMock(spec=TestSession)
    monkeypatch.setattr("app.settings.GetDB", db_session)
    return db_session


@pytest.fixture(autouse=True)
def mock_lock(monkeypatch: pytest.MonkeyPatch):
    _lock = MagicMock(spec=RWLock(fast=True))
    monkeypatch.setattr("app.node.node_manager._lock", _lock)


@pytest.fixture(autouse=True)
def mock_settings(monkeypatch: pytest.MonkeyPatch):
    settings = {
        "telegram": {"enable": False, "token": "", "webhook_url": "", "webhook_secret": None, "proxy_url": None},
        "discord": None,
        "webhook": {
            "enable": False,
            "webhooks": [],
            "days_left": [3],
            "usage_percent": [80],
            "timeout": 180,
            "recurrent": 3,
            "proxy_url": None,
        },
        "notification_settings": {
            "notify_telegram": False,
            "notify_discord": False,
            "telegram_api_token": "",
            "telegram_admin_id": None,
            "telegram_channel_id": 0,
            "telegram_topic_id": 0,
            "discord_webhook_url": "",
            "proxy_url": None,
            "max_retries": 3,
        },
        "notification_enable": {
            "admin": {
                "create": True,
                "modify": True,
                "delete": True,
                "reset_usage": True,
                "login": True,
            },
            "core": {
                "create": True,
                "modify": True,
                "delete": True,
            },
            "group": {
                "create": True,
                "modify": True,
                "delete": True,
            },
            "host": {
                "create": True,
                "modify": True,
                "delete": True,
                "modify_hosts": True,
            },
            "node": {
                "create": True,
                "modify": True,
                "delete": True,
                "connect": True,
                "error": True,
            },
            "user": {
                "create": True,
                "modify": True,
                "delete": True,
                "status_change": True,
                "reset_data_usage": True,
                "data_reset_by_next": True,
                "subscription_revoked": True,
            },
            "user_template": {
                "create": True,
                "modify": True,
                "delete": True,
            },
            "days_left": True,
            "percentage_reached": True,
        },
        "subscription": {
            "url_prefix": "",
            "update_interval": 12,
            "support_url": "https://t.me/",
            "profile_title": "Subscription",
            "host_status_filter": False,
            "randomize_order": False,
            "rules": [
                {
                    "pattern": "^([Cc]lash[\\-\\.]?[Vv]erge|[Cc]lash[\\-\\.]?[Mm]eta|[Ff][Ll][Cc]lash|[Mm]ihomo)",
                    "target": "clash_meta",
                },
                {"pattern": "^([Cc]lash|[Ss]tash)", "target": "clash"},
                {
                    "pattern": "^(SFA|SFI|SFM|SFT|[Kk]aring|[Hh]iddify[Nn]ext)|.*[Ss]ing[\\-b]?ox.*",
                    "target": "sing_box",
                },
                {"pattern": "^(SS|SSR|SSD|SSS|Outline|Shadowsocks|SSconf)", "target": "outline"},
                {"pattern": "^v2rayN", "target": "links_base64"},
                {"pattern": "^v2rayNG", "target": "links_base64"},
                {"pattern": "^[Ss]treisand", "target": "links_base64"},
                {"pattern": "^Happ", "target": "links_base64"},
                {"pattern": "^ktor\\-client", "target": "links_base64"},
                {"pattern": "^.*", "target": "links_base64"},
            ],
            "manual_sub_request": {
                "links": True,
                "links_base64": True,
                "xray": True,
                "sing_box": True,
                "clash": True,
                "clash_meta": True,
                "outline": True,
            },
            "applications": [
                {
                    "name": "Streisand",
                    "icon_url": "https://is1-ssl.mzstatic.com/image/thumb/Purple211/v4/1e/29/e0/1e29e04f-273b-9186-5f12-9bbe48c0fce2/AppIcon-0-0-1x_U007epad-0-0-0-1-0-85-220.png/460x0w.webp",
                    "import_url": "streisand://import/{url}",
                    "description": {
                        "en": "Flexible proxy client with rule-based setup, multiple protocols, and custom DNS. Supports VLESS(Reality), VMess, Trojan, Shadowsocks, Socks, SSH, Hysteria(V2), TUIC, Wireguard.",
                        "fa": "کلاینت پراکسی انعطاف‌پذیر با قوانین، پشتیبانی از پروتکل‌های متعدد و DNS سفارشی. پشتیبانی از VLESS(Reality)، VMess، Trojan، Shadowsocks، Socks، SSH، Hysteria(V2)، TUIC، WireGuard.",
                        "ru": "Гибкий прокси‑клиент с правилами, поддержкой множества протоколов и кастомным DNS. Поддерживаются VLESS(Reality), VMess, Trojan, Shadowsocks, Socks, SSH, Hysteria(V2), TUIC, Wireguard.",
                        "zh": "灵活的代理客户端，支持基于规则的配置、多种协议以及自定义 DNS。支持 VLESS(Reality)、VMess、Trojan、Shadowsocks、Socks、SSH、Hysteria(V2)、TUIC、Wireguard。",
                    },
                    "recommended": True,
                    "platform": "ios",
                    "download_links": [
                        {
                            "name": "Download",
                            "url": "https://apps.apple.com/us/app/streisand/id6450534064",
                            "language": "en",
                        },
                        {
                            "name": "دانلود",
                            "url": "https://apps.apple.com/us/app/streisand/id6450534064",
                            "language": "fa",
                        },
                        {
                            "name": "Скачать",
                            "url": "https://apps.apple.com/us/app/streisand/id6450534064",
                            "language": "ru",
                        },
                        {
                            "name": "下载",
                            "url": "https://apps.apple.com/us/app/streisand/id6450534064",
                            "language": "zh",
                        },
                    ],
                },
                {
                    "name": "SingBox",
                    "icon_url": "https://raw.githubusercontent.com/SagerNet/sing-box/refs/heads/dev-next/docs/assets/icon.svg",
                    "import_url": "sing-box://import-remote-profile?url={url}",
                    "description": {
                        "en": "A client that provides a platform for routing traffic securely.",
                        "fa": "Sing-box یک کلاینت برای مسیریابی امن ترافیک فراهم می‌کند.",
                        "ru": "Клиент, обеспечивающий безопасную маршрутизацию трафика.",
                        "zh": "提供安全流量路由的平台客户端。",
                    },
                    "recommended": False,
                    "platform": "ios",
                    "download_links": [
                        {
                            "name": "Download",
                            "url": "https://apps.apple.com/us/app/sing-box-vt/id6673731168",
                            "language": "en",
                        },
                        {
                            "name": "دانلود",
                            "url": "https://apps.apple.com/us/app/sing-box-vt/id6673731168",
                            "language": "fa",
                        },
                        {
                            "name": "Скачать",
                            "url": "https://apps.apple.com/us/app/sing-box-vt/id6673731168",
                            "language": "ru",
                        },
                        {
                            "name": "下载",
                            "url": "https://apps.apple.com/us/app/sing-box-vt/id6673731168",
                            "language": "zh",
                        },
                    ],
                },
                {
                    "name": "Shadowrocket",
                    "icon_url": "https://shadowlaunch.com/static/icon.png",
                    "import_url": "",
                    "description": {
                        "en": "A rule-based proxy utility client for iOS.",
                        "fa": "Shadowrocket یک ابزار پروکسی قانون‌محور برای iOS است.",
                        "ru": "Прокси‑клиент для iOS с маршрутизацией по правилам.",
                        "zh": "基于规则的 iOS 代理工具客户端。",
                    },
                    "recommended": False,
                    "platform": "ios",
                    "download_links": [
                        {
                            "name": "Download",
                            "url": "https://apps.apple.com/us/app/shadowrocket/id932747118",
                            "language": "en",
                        },
                        {
                            "name": "دانلود",
                            "url": "https://apps.apple.com/us/app/shadowrocket/id932747118",
                            "language": "fa",
                        },
                        {
                            "name": "Скачать",
                            "url": "https://apps.apple.com/us/app/shadowrocket/id932747118",
                            "language": "ru",
                        },
                        {
                            "name": "下载",
                            "url": "https://apps.apple.com/us/app/shadowrocket/id932747118",
                            "language": "zh",
                        },
                    ],
                },
                {
                    "name": "V2rayNG",
                    "icon_url": "https://raw.githubusercontent.com/2dust/v2rayNG/refs/heads/master/V2rayNG/app/src/main/ic_launcher-web.png",
                    "import_url": "v2rayng://install-config?url={url}",
                    "description": {
                        "en": "A V2Ray client for Android devices.",
                        "fa": "V2rayNG یک کلاینت V2Ray برای دستگاه‌های اندرویدی است.",
                        "ru": "Клиент V2Ray для устройств Android.",
                        "zh": "适用于 Android 设备的 V2Ray 客户端。",
                    },
                    "recommended": True,
                    "platform": "android",
                    "download_links": [
                        {
                            "name": "Download",
                            "url": "https://github.com/2dust/v2rayNG/releases/latest",
                            "language": "en",
                        },
                        {"name": "دانلود", "url": "https://github.com/2dust/v2rayNG/releases/latest", "language": "fa"},
                        {
                            "name": "Скачать",
                            "url": "https://github.com/2dust/v2rayNG/releases/latest",
                            "language": "ru",
                        },
                        {"name": "下载", "url": "https://github.com/2dust/v2rayNG/releases/latest", "language": "zh"},
                    ],
                },
                {
                    "name": "SingBox",
                    "icon_url": "https://raw.githubusercontent.com/SagerNet/sing-box/refs/heads/dev-next/docs/assets/icon.svg",
                    "import_url": "sing-box://import-remote-profile?url={url}",
                    "description": {
                        "en": "A client that provides a platform for routing traffic securely.",
                        "fa": "Sing-box یک کلاینت برای مسیریابی امن ترافیک فراهم می‌کند.",
                        "ru": "Клиент, обеспечивающий безопасную маршрутизацию трафика.",
                        "zh": "提供安全流量路由的平台客户端。",
                    },
                    "recommended": False,
                    "platform": "android",
                    "download_links": [
                        {
                            "name": "Download",
                            "url": "https://play.google.com/store/apps/details?id=io.nekohasekai.sfa&hl=en",
                            "language": "en",
                        },
                        {
                            "name": "دانلود",
                            "url": "https://play.google.com/store/apps/details?id=io.nekohasekai.sfa&hl=en",
                            "language": "fa",
                        },
                        {
                            "name": "Скачать",
                            "url": "https://play.google.com/store/apps/details?id=io.nekohasekai.sfa&hl=en",
                            "language": "ru",
                        },
                        {
                            "name": "下载",
                            "url": "https://play.google.com/store/apps/details?id=io.nekohasekai.sfa&hl=en",
                            "language": "zh",
                        },
                    ],
                },
                {
                    "name": "V2rayN",
                    "icon_url": "https://raw.githubusercontent.com/2dust/v2rayN/refs/heads/master/v2rayN/v2rayN.Desktop/v2rayN.png",
                    "import_url": "",
                    "description": {
                        "en": "A Windows V2Ray client with GUI support.",
                        "fa": "v2rayN یک کلاینت V2Ray برای ویندوز با پشتیبانی از رابط کاربری است.",
                        "ru": "V2Ray клиент для Windows с графическим интерфейсом.",
                        "zh": "带有图形界面的 Windows V2Ray 客户端。",
                    },
                    "recommended": True,
                    "platform": "windows",
                    "download_links": [
                        {
                            "name": "Download",
                            "url": "https://github.com/2dust/v2rayN/releases/latest",
                            "language": "en",
                        },
                        {"name": "دانلود", "url": "https://github.com/2dust/v2rayN/releases/latest", "language": "fa"},
                        {"name": "Скачать", "url": "https://github.com/2dust/v2rayN/releases/latest", "language": "ru"},
                        {"name": "下载", "url": "https://github.com/2dust/v2rayN/releases/latest", "language": "zh"},
                    ],
                },
                {
                    "name": "FlClash",
                    "icon_url": "https://raw.githubusercontent.com/chen08209/FlClash/refs/heads/main/assets/images/icon.png",
                    "import_url": "",
                    "description": {
                        "en": "A cross-platform GUI client for clash core.",
                        "fa": "Flclash یک کلاینت GUI چندسکویی برای clash core است.",
                        "ru": "Кроссплатформенный GUI-клиент для clash core.",
                        "zh": "跨平台 clash core 图形界面客户端。",
                    },
                    "recommended": False,
                    "platform": "windows",
                    "download_links": [
                        {
                            "name": "Download",
                            "url": "https://github.com/chen08209/FlClash/releases/latest",
                            "language": "en",
                        },
                        {
                            "name": "دانلود",
                            "url": "https://github.com/chen08209/FlClash/releases/latest",
                            "language": "fa",
                        },
                        {
                            "name": "Скачать",
                            "url": "https://github.com/chen08209/FlClash/releases/latest",
                            "language": "ru",
                        },
                        {
                            "name": "下载",
                            "url": "https://github.com/chen08209/FlClash/releases/latest",
                            "language": "zh",
                        },
                    ],
                },
                {
                    "name": "FlClash",
                    "icon_url": "https://raw.githubusercontent.com/chen08209/FlClash/refs/heads/main/assets/images/icon.png",
                    "import_url": "",
                    "description": {
                        "en": "A cross-platform GUI client for clash core.",
                        "fa": "Flclash یک کلاینت GUI چندسکویی برای clash core است.",
                        "ru": "Кроссплатформенный GUI-клиент для clash core.",
                        "zh": "跨平台 clash core 图形界面客户端。",
                    },
                    "recommended": True,
                    "platform": "linux",
                    "download_links": [
                        {
                            "name": "Download",
                            "url": "https://github.com/chen08209/FlClash/releases/latest",
                            "language": "en",
                        },
                        {
                            "name": "دانلود",
                            "url": "https://github.com/chen08209/FlClash/releases/latest",
                            "language": "fa",
                        },
                        {
                            "name": "Скачать",
                            "url": "https://github.com/chen08209/FlClash/releases/latest",
                            "language": "ru",
                        },
                        {
                            "name": "下载",
                            "url": "https://github.com/chen08209/FlClash/releases/latest",
                            "language": "zh",
                        },
                    ],
                },
                {
                    "name": "SingBox",
                    "icon_url": "https://raw.githubusercontent.com/SagerNet/sing-box/refs/heads/dev-next/docs/assets/icon.svg",
                    "import_url": "sing-box://import-remote-profile?url={url}",
                    "description": {
                        "en": "A client that provides a platform for routing traffic securely.",
                        "fa": "Sing-box یک کلاینت برای مسیریابی امن ترافیک فراهم می‌کند.",
                        "ru": "Клиент, обеспечивающий безопасную маршрутизацию трафика.",
                        "zh": "提供安全流量路由的平台客户端。",
                    },
                    "recommended": False,
                    "platform": "linux",
                    "download_links": [
                        {
                            "name": "Download",
                            "url": "https://github.com/SagerNet/sing-box/releases/latest",
                            "language": "en",
                        },
                        {
                            "name": "دانلود",
                            "url": "https://github.com/SagerNet/sing-box/releases/latest",
                            "language": "fa",
                        },
                        {
                            "name": "Скачать",
                            "url": "https://github.com/SagerNet/sing-box/releases/latest",
                            "language": "ru",
                        },
                        {
                            "name": "下载",
                            "url": "https://github.com/SagerNet/sing-box/releases/latest",
                            "language": "zh",
                        },
                    ],
                },
            ],
        },
        "general": {"default_flow": "", "default_method": "chacha20-ietf-poly1305"},
    }
    db_settings = Settings(**settings)

    settings_mock = AsyncMock()
    settings_mock.return_value = db_settings

    monkeypatch.setattr("app.settings.get_settings", settings_mock)
    return settings


@pytest.fixture
def access_token() -> str:
    response = client.post(
        url="/api/admin/token",
        data={"username": "testadmin", "password": "testadmin", "grant_type": "password"},
    )
    return response.json()["access_token"]


@pytest.fixture
def disable_cache(monkeypatch: pytest.MonkeyPatch):
    def dummy_cached(*args, **kwargs):
        def wrapper(func):
            return func  # bypass caching

        return wrapper

    monkeypatch.setattr("app.settings.cached", dummy_cached)
