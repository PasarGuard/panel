<p align="center">
  <a href="https://github.com/PasarGuard/panel" target="_blank" rel="noopener noreferrer">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://github.com/PasarGuard/PasarGuard.github.io/raw/main/public/logos/PasarGuard-white-logo.png">
      <img width="160" height="160" src="https://github.com/PasarGuard/PasarGuard.github.io/raw/main/public/logos/PasarGuard-black-logo.png">
    </picture>
  </a>
</p>

<h1 align="center">🛡️ PasarGuard</h1>

<p align="center">
    <strong>Unified & Censorship-Resistant Proxy Management Solution</strong>
</p>

---

<br/>
<p align="center">
    <a href="https://github.com/PasarGuard/panel/actions/workflows/build.yml" target="_blank">
        <img src="https://img.shields.io/github/actions/workflow/status/PasarGuard/panel/build.yml?style=flat-square" />
    </a>
    <a href="https://hub.docker.com/r/PasarGuard/panel" target="_blank">
        <img src="https://img.shields.io/docker/pulls/pasarguard/panel?style=flat-square&logo=docker" />
    </a>
    <a href="https://github.com/PasarGuard/panel/blob/main/LICENSE" target="_blank">
        <img src="https://img.shields.io/github/license/PasarGuard/panel?style=flat-square" />
    </a>
    <a href="https://t.me/Pasar_Guard" target="_blank">
        <img src="https://img.shields.io/badge/telegram-group-blue?style=flat-square&logo=telegram" />
    </a>
    <a href="https://github.com/PasarGuard/panel" target="_blank">
        <img src="https://img.shields.io/github/stars/PasarGuard/panel?style=social" />
    </a>
</p>

<p align="center">
 <a href="./README-fa.md">
 🇮🇷 فارسی
 </a>
  /
  <a href="./README-zh-cn.md">
 🇨🇳 简体中文
 </a>
   /
  <a href="./README-ru.md">
 🇷🇺 Русский
 </a>
</p>

<p align="center">
  <a href="https://github.com/PasarGuard/panel" target="_blank" rel="noopener noreferrer" >
    <img src="https://github.com/PasarGuard/PasarGuard.github.io/raw/main/public/logos/screenshot.png" alt="PasarGuard screenshots" width="600" height="auto">
  </a>
</p>

## 📋 Table of Contents

> **Quick Navigation** - Jump to any section below

-   [📖 Overview](#-overview)
    -   [🤔 Why using PasarGuard?](#-why-using-pasarguard)
        -   [✨ Features](#-features)
-   [🚀 Installation guide](#-installation-guide)
-   [📚 Documentation](#-documentation)
-   [🧩 Plugins](#-plugins)
-   [💖 Donation](#-donation)

---

# 📖 Overview

> **What is PasarGuard?**

PasarGuard is a powerful proxy management tool that offers an intuitive and efficient interface for handling hundreds of proxy accounts. Built with Python and React.js it combines performance, scalability, and ease of use to simplify large-scale proxy management. It supports both [Xray-core](https://github.com/XTLS/Xray-core) and [WireGuard](https://www.wireguard.com/) for maximum performance.

---

## 🤔 Why using PasarGuard?

> **Simple, Powerful, Reliable**

PasarGuard is a user-friendly, feature-rich, and reliable proxy management tool. It allows you to create and manage multiple proxies for your users without the need for complex configuration. With its built-in web interface, you can easily monitor activity, modify settings, and control user access limits — all from one convenient dashboard.

---

### ✨ Features

<div align="left">

**🌐 Web Interface & API**
- Built-in **Web UI** dashboard
- Fully **REST API** backend
- **Multi-Node** support for infrastructure distribution

**🔐 Protocols & Security**
- Supports **Vmess**, **VLESS**, **Trojan**, **Shadowsocks**, **WireGuard** and **Hysteria2**
- **TLS** and **REALITY** support
- **Multi-protocol** for a single user

**👥 User Management**
- **Multi-user** on a single inbound
- **Multi-inbound** on a **single port** (fallbacks support)
- **Traffic** and **expiry date** limitations
- **Periodic** traffic limit (daily, weekly, etc.)
- **HWID/device limits** for hardware-bound access control

**🔗 Subscriptions & Sharing**
- **Subscription link** compatible with **V2ray**, **Clash** and **ClashMeta**
- Automated **Share link** and **QRcode** generator
- System monitoring and **traffic statistics**

**🛠️ Tools & Customization**
- Customizable xray configuration
- Integrated **Telegram Bot**
- **Command Line Interface (CLI)**
- **Multi-language** support
- **Multi-admin** support with **RBAC** for granular permissions and scoped access

</div>

---

# 🚀 Installation guide

> **Quick Start** - Get PasarGuard running in minutes

### For a quick setup, use the following commands based on your preferred database.

---

**TimescaleDB (Recommended):**
```bash
sudo bash -c "$(curl -fsSL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --database timescaledb
```

**SQLite:**
```bash
sudo bash -c "$(curl -fsSL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install
```

**MySQL:**
```bash
sudo bash -c "$(curl -fsSL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --database mysql
```

**MariaDB:**
```bash
sudo bash -c "$(curl -fsSL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --database mariadb
```

**PostgreSQL:**
```bash
sudo bash -c "$(curl -fsSL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --database postgresql
```

### 📋 After installation:

<div align="left">

**📋 Watch the logs** (press `Ctrl+C` to stop)

**📁 Files are located at** `/opt/pasarguard`

**⚙️ Config file:** `/opt/pasarguard/.env` (see [Configuration](#-configuration) for details)

**💾 Data files:** `/var/lib/pasarguard`

**🔒 Important:** Dashboard requires SSL certificate for security
- Get SSL certificate: [Guide](https://docs.pasarguard.org/en/examples/issue-ssl-certificate)
- Access: `https://YOUR_DOMAIN:8000/dashboard/`

**🔗 For testing without domain:** Use SSH port forwarding (see below)

</div>

---

```bash
ssh -L 8000:localhost:8000 user@serverip
```

Then access: `http://localhost:8000/dashboard/`

> ⚠️ **Testing only** - You'll lose access when you close the SSH terminal.

### 🔧 Next Steps:

```bash
# Generate a one-time setup key for owner account setup
pasarguard cli generate-temp-key

# Use the key on the dashboard login page to create the owner account

# Get help
pasarguard --help
```



# 📚 Documentation

<div align="left">

**📖 Official Documentation** - Complete guides available in:

🇺🇸 **[English](https://docs.pasarguard.org/en)**

🇮🇷 **[فارسی](https://docs.pasarguard.org/fa)**

🇷🇺 **[Русский](https://docs.pasarguard.org/ru)**

🇨🇳 **[简体中文](https://docs.pasarguard.org/zh-cn)**

</div>

> **Contributing:** Help improve documentation on [GitHub](https://github.com/PasarGuard/PasarGuard.github.io)

---

# 🧩 Plugins

Plugins ("sub-modules") are small Python packages that you install on the server yourself. A plugin can
react to panel events, add API endpoints, change subscriptions before they are sent, run periodic jobs,
have settings edited in the dashboard and, optionally, show its own page in the dashboard sidebar.

> **Plugins are trusted code.** They run inside the panel process with full access to the database and
> every panel module. Install only plugins you have read. There is no install button in the dashboard:
> a plugin is a folder on disk, enabled by an environment variable.

### Install and enable

1. Put the plugin folder into `PLUGINS_DIR` (default `/var/lib/pasarguard/plugins`), e.g.
   `/var/lib/pasarguard/plugins/expiring-report/plugin.json`.
2. List enabled plugin ids in `PLUGINS` (comma separated) and restart the panel:

```env
PLUGINS_DIR = "/var/lib/pasarguard/plugins"
PLUGINS = "expiring-report,sub-banner"
```

With `PLUGINS` empty the plugin system is off: no plugin code is imported and no plugin routes are added.
The panel's own `/api/plugins` endpoints stay mounted; `GET /api/plugins` (owner only, requested by the
dashboard once on load for the owner) then returns an empty list. A plugin that
fails to load (bad manifest, wrong panel version, exception in `setup`) is skipped and logged; the panel
always starts. Owners see loaded and failed plugins (with the error) under **Plugins** in the sidebar;
the item is hidden while no plugin is enabled.

### Folder layout and manifest

```text
expiring-report/
├── plugin.json
├── plugin.py          # entry module, may import sibling modules: from . import helpers
└── ui/index.html      # optional dashboard page
```

```json
{
  "id": "expiring-report",
  "name": "Expiring users report",
  "version": "1.0.0",
  "panel": ">=5.5.0",
  "entry": "plugin:setup",
  "description": "Users expiring within N days",
  "ui": "ui/index.html",
  "settings_schema": {
    "type": "object",
    "properties": { "days": { "type": "integer", "minimum": 1, "default": 7 } },
    "additionalProperties": false
  }
}
```

- `id` must match the folder name (`a-z 0-9 - _`, up to 64 chars). The folder is imported as package
  `pasarguard_plugins.<id>`; `sys.path` is not changed.
- `panel` is a version constraint (`>=5.5.0`, `>=5.5,<6`); a plugin for another panel version is refused.
- `entry` is `module:function`, default `plugin:setup`.

### Plugin API

`setup(ctx)` (sync or `async`) receives a `PluginContext`. This is the whole public API:

| Name | What it is |
|---|---|
| `ctx.id`, `ctx.version`, `ctx.logger` | plugin id, manifest version, a logger named `plugin.<id>` |
| `ctx.router` | FastAPI `APIRouter`, mounted at `/api/plugins/<id>` |
| `ctx.deps.admin`, `ctx.deps.owner`, `ctx.deps.public` | FastAPI dependencies for plugin routes |
| `ctx.on(event, handler)` | async `handler(payload: dict)` for an event or `"*"` |
| `ctx.subscription.transform(fn, cache=True)` | `fn(user, config_format, content)` returns new content or `None` |
| `ctx.subscription.headers(fn)` | `fn(user, config_format, headers)` returns headers to add or `None` (sync) |
| `ctx.subscription.variables(fn)` | `fn(user)` returns extra format variables `{"PLAN": "Gold"}` (sync) |
| `ctx.job(fn, seconds=...)` or `ctx.job(fn, cron="0 9 * * *")` | periodic job, sync or async, UTC |
| `ctx.settings.get()`, `ctx.settings.on_change(fn)` | current settings (validated, defaults applied) |
| `ctx.db()` | `async with ctx.db() as db:` SQLAlchemy session (full access) |

Plugins may import other panel modules (`app.*`), but those are internal and can change in any release.
Register everything inside `setup()`: routes and jobs added later are not picked up. An invalid
`cron` expression makes `setup()` fail, so the plugin is skipped with that error. An `async def setup`
runs at startup, after the plugin settings are read from the database. In a sync `setup()` the settings
are still the schema defaults; read them inside handlers, not at setup time.

```python
def setup(ctx):
    @ctx.router.get("/hello")              # GET /api/plugins/<id>/hello, admin only
    async def hello():
        return {"days": ctx.settings.get()["days"]}

    @ctx.on("user.status_changed")
    async def on_status(payload):
        if payload["user"]["status"] in ("expired", "limited"):
            ctx.logger.info(f"{payload['user']['username']} is {payload['user']['status']}")

    ctx.job(lambda: ctx.logger.info("tick"), seconds=3600)
```

**Routes.** Every route on `ctx.router` requires an authenticated admin. Add
`dependencies=[Depends(ctx.deps.owner)]` for owner-only routes. A route that does its own authentication
(for example a webhook with a secret) must say so explicitly with `dependencies=[Depends(ctx.deps.public)]`.
`/api/plugins/<id>/settings`, `/api/plugins/<id>/ui/...` and `/api/plugins/<id>/ui-session` are reserved
by the panel. Only HTTP routes declared with `@ctx.router.get/post/put/patch/delete/api_route` (or included
sub-routers made of them) are allowed: websocket routes, `mount()`, `add_route()` and `@ctx.router.route`
would not run the panel's auth dependency, so a plugin that adds them is refused with an error.

**Events.** Names are dotted versions of the panel notification events: `user.created`, `user.modified`,
`user.removed`, `user.status_changed` (expired, limited, disabled, active, on_hold), `user.usage_reset`,
`user.data_reset_by_next`, `user.subscription_revoked`, `node.created`, `node.modified`, `node.removed`,
`node.connected`, `node.recovered`, `node.error`, `node.limited`, `node.usage_reset`, `host.created`,
`host.modified`, `host.removed`, `hosts.modified`, `group.*`, `user_template.*`, `core.*`, `admin_role.*`,
`api_key.*` (`created` / `modified` / `removed`), `admin.created`, `admin.modified`, `admin.removed`,
`admin.usage_reset`, `admin.usage_limit_reached`, `admin.login`. The payload is the event's data as JSON,
for example `{"event": "user.created", "user": {...}, "by": "admin-username"}`. Admin passwords and API
keys are never included (`admin.login` has `username`, `client_ip`, `success`). The payloads are otherwise
the same data webhook notifications carry: user payloads contain the proxy credentials (VLESS/VMess UUIDs,
Trojan and Shadowsocks passwords) and the subscription URL with its token, admin payloads contain contact
fields such as the Discord webhook. Treat them as secrets. Plugin events fire even when Telegram,
Discord and webhook notifications are turned off. Each handler runs in the background with a 10 second
timeout; errors and timeouts are logged and never affect the action that caused the event.

**Subscriptions.** `user` is the subscription user as a dict, `config_format` is one of `links`,
`links_base64`, `xray`, `sing_box`, `clash`, `clash_meta`, `outline`, `wireguard`. Transforms get the
decoded content (the panel encodes `links_base64` afterwards). By default (`cache=True`) a transform runs
while the subscription is rendered and its output is kept in the short subscription cache, so it must
depend only on the user, the format and the plugin settings. Register it with `cache=False` to run it on
every request after the cache. Header hooks run before the admin's subscription response headers, which
win on conflicts. Variables must be UPPERCASE; built-in variables (`{USERNAME}`, `{DAYS_LEFT}`, ...) cannot
be overridden, the admin's custom variables can override plugin ones. They work in host remarks, the
profile title and the other places where format variables are used.

**Settings.** `settings_schema` is a JSON Schema object. The panel validates `type`, `properties`,
`required`, `enum`, `default`, `minimum`, `maximum`, `items` and `additionalProperties: false` (other
keywords are ignored). Settings are stored in the `plugin_settings` table and edited in the dashboard
(owner only; strings, numbers, booleans, enums and string lists get form fields, anything else a JSON box)
or via `GET/PUT /api/plugins/<id>/settings`.

**Dashboard page.** If the manifest has `ui`, the plugin gets a sidebar entry that opens the UI folder in a
iframe (`/api/plugins/<id>/ui/`, owner only). The iframe is same-origin with
`sandbox="allow-scripts allow-forms allow-same-origin"`, which does **not** isolate the plugin: the page can
reach the dashboard window and storage and gets the owner's token, so plugin UI is trusted code with full
owner access, like the plugin's Python code. Include `/api/plugins/sdk.js` in the page:

```html
<script src="/api/plugins/sdk.js"></script>
<script>
  PasarGuard.ready().then(({ token, theme, lang }) => {
    PasarGuard.api('/api/plugins/expiring-report/users').then(data => console.log(data))
  })
</script>
```

`PasarGuard.api(path, options)` is `fetch` with the admin token added and JSON handling. The dashboard
passes the token with `postMessage` after the page reports it is ready; both sides check the window and the
origin. To load the files without an `Authorization` header the dashboard first sets an HttpOnly,
`SameSite=Strict` cookie limited to `/api/plugins/<id>/ui/`, holding the same token; it is `Secure` unless the
panel is opened over plain HTTP on `localhost`. The panel has no logout endpoint, so logging out of the
dashboard does not clear this cookie: it expires together with the token (`JWT_ACCESS_TOKEN_EXPIRE_MINUTES`).
Theme colors are copied to the page as CSS variables (`hsl(var(--background))`, `--foreground`,
`--primary`, ...) and the `dark` class is set in dark mode. Plugins cannot change existing dashboard screens
(slots in existing dialogs are planned for a later version).

### Several workers and roles

Every process (all-in-one, each uvicorn worker, and the legacy backend / node / scheduler roles) loads the
enabled plugins and runs `setup()`, so install the same plugins with the same `PLUGINS` everywhere.

- Routes are served only by processes that run the panel API.
- Jobs run only in the scheduler role and only on the current job leader, so a job runs once per cluster.
- Each event reaches plugins once, in the process where it happened (the same deduplication as panel
  notifications; two identical events for the same object within 15 seconds are merged in a multi-worker
  setup).
- Saving settings updates the database and tells the other workers over NATS; `on_change` runs in every
  worker.

### Examples

Two example plugins live in [`examples/plugins`](examples/plugins): `expiring-report` (settings, owner-only
endpoint, dashboard page with CSV export, daily job) and `sub-banner` (subscription transform that adds an
info line such as `⏳ 12 days left · Premium` to links subscriptions, and a `{PLAN}` variable by group).

---

# 💖 Donation

<div align="left">

> **Support PasarGuard Development**

If PasarGuard helps you, consider supporting its development:

[![Donate](https://img.shields.io/badge/Donate-Support%20Us-green?style=for-the-badge)](https://donate.pasarguard.org)

**Thank you for your support!** 💖

</div>

---

<p align="center">
  Made with ❤️ for Internet freedom
</p>

