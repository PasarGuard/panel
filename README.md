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
    <strong>Unified GUI Censorship Resistant Solution</strong>
</p>

---

<br/>
<p align="center">
    <a href="#">
        <img src="https://img.shields.io/github/actions/workflow/status/PasarGuard/panel/build.yml?style=flat-square" />
    </a>
    <a href="https://hub.docker.com/r/PasarGuard/panel" target="_blank">
        <img src="https://img.shields.io/docker/pulls/PasarGuard/panel?style=flat-square&logo=docker" />
    </a>
    <a href="#">
        <img src="https://img.shields.io/github/license/PasarGuard/panel?style=flat-square" />
    </a>
    <a href="https://t.me/Pasar_Guard" target="_blank">
        <img src="https://img.shields.io/badge/telegram-group-blue?style=flat-square&logo=telegram" />
    </a>
    <a href="#">
        <img src="https://img.shields.io/badge/twitter-commiunity-blue?style=flat-square&logo=twitter" />
    </a>
    <a href="#">
        <img src="https://img.shields.io/github/stars/PasarGuard/panel?style=social" />
    </a>
</p>

<p align="center">
 <a href="./README.md">
 English
 </a>
 /
 <a href="./README-fa.md">
 فارسی
 </a>
  /
  <a href="./README-zh-cn.md">
 简体中文
 </a>
   /
  <a href="./README-ru.md">
 Русский
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
-   [⚙️ Configuration](#-configuration)
-   [📚 Documentation](#-documentation)
-   [💖 Donation](#-donation)
-   [📄 License](#-license)
-   [🌟 Contributors](#-contributors)

---

# 📖 Overview

> **What is PasarGuard?**

PasarGuard is a powerful proxy management tool that makes it easy to manage hundreds of proxy accounts. Built with Python and React, it's powered by [Xray-core](https://github.com/XTLS/Xray-core) for maximum performance.

---

## 🤔 Why using PasarGuard?

> **Simple, Powerful, Reliable**

PasarGuard is user-friendly, feature-rich, and reliable. You can create different proxies for your users without complicated configuration. The built-in web UI lets you easily monitor, modify, and limit users.

---

### ✨ Features

<div align="center">

| 🌐 **Web UI** | 🔌 **REST API** | 🌍 **Multi-Node** |
|:---:|:---:|:---:|
| Built-in dashboard | Full backend API | Infrastructure distribution |

| 🔐 **Protocols** | 👥 **Multi-User** | 📊 **Traffic Control** |
|:---:|:---:|:---:|
| VMess, VLESS, Trojan, Shadowsocks | Single inbound support | Limits & expiry dates |

| 🔗 **Subscriptions** | 🤖 **Automation** | 📈 **Monitoring** |
|:---:|:---:|:---:|
| V2Ray, Clash, ClashMeta | Share links & QR codes | Real-time statistics |

| 🔒 **Security** | 💻 **CLI/TUI** | 🌐 **Multi-Language** |
|:---:|:---:|:---:|
| TLS & REALITY support | Command line tools | Multiple languages |

</div>

---

# 🚀 Installation guide

> **Quick Start** - Get PasarGuard running in minutes

### ⚠️ These commands install pre-release versions (alpha/beta)

---

**SQLite (Default):**
```bash
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --pre-release
```

**MySQL:**
```bash
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --database mysql --pre-release
```

**MariaDB:**
```bash
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --database mariadb --pre-release
```

**PostgreSQL:**
```bash
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --database postgresql --pre-release
```

### 📋 After installation:

<div align="left">

| Step | Action | Details |
|:---:|:---|:---|
| 📋 | **Watch logs** | Press `Ctrl+C` to stop |
| 📁 | **Files location** | `/opt/pasarguard` |
| ⚙️ | **Config file** | `/opt/pasarguard/.env` |
| 💾 | **Data files** | `/var/lib/pasarguard` |
| 🔒 | **SSL Required** | [Get certificate](https://PasarGuard.github.io/PasarGuard/en/examples/issue-ssl-certificate) |
| 🌐 | **Access dashboard** | `https://YOUR_DOMAIN:8000/dashboard/` |
| 🔗 | **Testing mode** | SSH port forwarding (see below) |

</div>

---

```bash
ssh -L 8000:localhost:8000 user@serverip
```

Then access: `http://localhost:8000/dashboard/`

> ⚠️ **Testing only** - You'll lose access when you close the SSH terminal.

### 🔧 Next Steps:

```bash
# Create admin account
pasarguard cli admin create --sudo

# Get help
pasarguard --help
```

> 📖 **Advanced users:** See manual installation section below

---

<details markdown="1">
<summary><h3>🏗️ Manual install (advanced)</h3></summary>

> **For developers and advanced users**

---

### **1. Install Xray:**

> Use [Xray-install](https://github.com/XTLS/Xray-install)

```bash
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
```

### **2. Clone and setup:**

> **Requires Python >= 3.12.7**

```bash
git clone https://github.com/PasarGuard/panel.git
cd PasarGuard
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
```

### **3. Database migration:**

```bash
uv run alembic upgrade head
```

### **4. Setup CLI (optional):**

```bash
sudo ln -s $(pwd)/pasarguard-cli.py /usr/bin/pasarguard-cli
sudo chmod +x /usr/bin/pasarguard-cli
pasarguard-cli completion install
```

### **5. Configuration:**

> Copy and edit the config file (modify admin credentials):

```bash
cp .env.example .env
nano .env
```

> 📖 Check [configurations](#-configuration) section for more information

### **6. Launch the application:**

```bash
uv run main.py
```

### **7. Run as service (optional):**

> Copy PasarGuard.service to `/var/lib/pasarguard/PasarGuard.service`

```
systemctl enable /var/lib/pasarguard/PasarGuard.service
systemctl start PasarGuard
```

### **8. Nginx configuration:**

```
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name  example.com;

    ssl_certificate      /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key  /etc/letsencrypt/live/example.com/privkey.pem;

    location ~* /(dashboard|statics|sub|api|docs|redoc|openapi.json) {
        proxy_pass http://0.0.0.0:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    # xray-core ws-path: /
    # client ws-path: /PasarGuard/me/2087
    #
    # All traffic is proxed through port 443, and send to the xray port(2087, 2088 etc.).
    # The '/PasarGuard' in location regex path can changed any characters by yourself.
    #
    # /${path}/${username}/${xray-port}
    location ~* /PasarGuard/.+/(.+)$ {
        proxy_redirect off;
        proxy_pass http://127.0.0.1:$1/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $http_host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

or

```
server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name  PasarGuard.example.com;

    ssl_certificate      /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key  /etc/letsencrypt/live/example.com/privkey.pem;

    location / {
        proxy_pass http://0.0.0.0:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

### **Default Settings:**

| Setting | Value | Customize |
|:---:|:---|:---|
| **URL** | `http://localhost:8000/dashboard` | Change `UVICORN_HOST` and `UVICORN_PORT` in `.env` |

---

</details>

# ⚙️ Configuration

> **Environment Variables** - Configure these settings using environment variables or by adding them to your `.env` file.

---



| Variable                                 | Description                                                                                                              |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| SUDO_USERNAME                            | Superuser's username                                                                                                     |
| SUDO_PASSWORD                            | Superuser's password                                                                                                     |
| SQLALCHEMY_DATABASE_URL                  | Database URL ([SQLAlchemy's docs](https://docs.sqlalchemy.org/en/20/core/engines.html#database-urls))                    |
| SQLALCHEMY_POOL_SIZE                     | (default: `10`)                                                                                                          |
| SQLALCHEMY_MAX_OVERFLOW                  | (default: `30`)                                                                                                          |
| UVICORN_HOST                             | Bind application to this host (default: `0.0.0.0`)                                                                       |
| UVICORN_PORT                             | Bind application to this port (default: `8000`)                                                                          |
| UVICORN_UDS                              | Bind application to a UNIX domain socket                                                                                 |
| UVICORN_SSL_CERTFILE                     | SSL certificate file to have application on https                                                                        |
| UVICORN_SSL_KEYFILE                      | SSL key file to have application on https                                                                                |
| UVICORN_SSL_CA_TYPE                      | Type of authority SSL certificate. Use `private` for testing self-signed CA (default: `public`)                          |
| XRAY_JSON                                | Path of Xray's json config file (default: `xray_config.json`)                                                            |
| CUSTOM_TEMPLATES_DIRECTORY               | Customized templates directory (default: `app/templates`)                                                                |
| CLASH_SUBSCRIPTION_TEMPLATE              | The template that will be used for generating clash configs (default: `clash/default.yml`)                               |
| SUBSCRIPTION_PAGE_TEMPLATE               | The template used for generating subscription info page (default: `subscription/index.html`)                             |
| XRAY_SUBSCRIPTION_TEMPLATE               | The template that will be used for generating xray configs (default: `xray/default.yml`)                                 |
| SINGBOX_SUBSCRIPTION_TEMPLATE            | The template that will be used for generating xray configs (default: `xray/default.yml`)                                 |
| HOME_PAGE_TEMPLATE                       | Decoy page template (default: `home/index.html`)                                                                         |
| JWT_ACCESS_TOKEN_EXPIRE_MINUTES          | Expire time for the Access Tokens in minutes, `0` considered as infinite (default: `1440`)                               |
| DOCS                                     | Whether API documents should be available on `/docs` and `/redoc` or not (default: `False`)                              |
| DEBUG                                    | Debug mode for development (default: `False`)                                                                            |
| USERS_AUTODELETE_DAYS                    | Delete expired (and optionally limited users) after this many days (Negative values disable this feature, default: `-1`) |
| USER_AUTODELETE_INCLUDE_LIMITED_ACCOUNTS | Whether to include limited accounts in the auto-delete feature (default: `False`)                                        |
| XRAY_SUBSCRIPTION_PATH                   | You can change your api path for subscrtiption (default: `sub`)                                                          |
| ENABLE_RECORDING_NODES_STATS             | Due to high amount of data, this job is only available for postgresql and timescaledb                                    |

# 📚 Documentation

<div align="center">

| Language | Documentation |
|:---:|:---|
| 🇺🇸 | [English](https://PasarGuard.github.io/PasarGuard) |
| 🇮🇷 | [فارسی](https://PasarGuard.github.io/PasarGuard) |
| 🇷🇺 | [Русский](https://PasarGuard.github.io/PasarGuard) |

</div>

> **Contributing:** Help improve documentation on [GitHub](https://github.com/PasarGuard/PasarGuard.github.io)

---

# 💖 Donation

<div align="center">

> **Support PasarGuard Development**

If PasarGuard helps you, consider supporting its development:

[![Donate](https://img.shields.io/badge/Donate-Support%20Us-green?style=for-the-badge)](http://donate.pasarguard.org)

**Thank you for your support!** 💖

</div>

---

# 📄 License

<div align="center">

| License | Status |
|:---:|:---|
| [AGPL-3.0](./LICENSE) | ✅ Open Source |

**Made with ❤️**

</div>

---

# 🌟 Contributors

<div align="center">

> **We ❤️ contributors!**

| Action | Link |
|:---:|:---|
| 🐛 **Report Issues** | [GitHub Issues](https://github.com/PasarGuard/panel/issues) |
| 📝 **Contribute Code** | [Contributing Guide](CONTRIBUTING.md) |
| 💬 **Get Support** | [Telegram Group](https://t.me/Pasar_Guard) |

</div>

---

<p align="center">
Thanks to the all contributors who have helped improve PasarGuard:
</p>
<p align="center">
<a href="https://github.com/PasarGuard/panel/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=PasarGuard/panel" />
</a>
</p>
<p align="center">
  Made with <a rel="noopener noreferrer" target="_blank" href="https://contrib.rocks">contrib.rocks</a>
</p>
