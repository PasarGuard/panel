<div align="center">

# 🛡️ PasarGuard

[![PasarGuard Logo](https://github.com/PasarGuard/docs/blob/main/logos/PasarGuard-black-logo.png)](https://github.com/PasarGuard/panel)

### Unified GUI Censorship Resistant Solution

</div>

<div align="center">

## 📊 Project Status

[![Build Status](https://img.shields.io/github/actions/workflow/status/PasarGuard/panel/build.yml?style=for-the-badge&label=Build&logo=github)](https://github.com/PasarGuard/panel/actions)
[![Docker Pulls](https://img.shields.io/docker/pulls/PasarGuard/panel?style=for-the-badge&label=Docker%20Pulls&logo=docker)](https://hub.docker.com/r/PasarGuard/panel)
[![License](https://img.shields.io/github/license/PasarGuard/panel?style=for-the-badge&label=License&logo=opensourceinitiative)](https://github.com/PasarGuard/panel/blob/main/LICENSE)
[![Telegram](https://img.shields.io/badge/Telegram-Group-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/Pasar_Guard)
[![GitHub Stars](https://img.shields.io/github/stars/PasarGuard/panel?style=for-the-badge&label=Stars&logo=github)](https://github.com/PasarGuard/panel)

</div>

<div align="center">

## 🌍 Languages

[![English](https://img.shields.io/badge/English-🇺🇸-blue?style=for-the-badge)](./README.md)
[![فارسی](https://img.shields.io/badge/فارسی-🇮🇷-green?style=for-the-badge)](./README-fa.md)
[![简体中文](https://img.shields.io/badge/简体中文-🇨🇳-red?style=for-the-badge)](./README-zh-cn.md)
[![Русский](https://img.shields.io/badge/Русский-🇷🇺-orange?style=for-the-badge)](./README-ru.md)

</div>

<div align="center">

## 🖼️ Preview

[![PasarGuard Dashboard Preview](https://github.com/PasarGuard/docs/raw/master/screenshots/preview.png)](https://github.com/PasarGuard/panel)

*Click to view larger image*

</div>

## 📋 Table of Contents

-   [📖 Overview](#overview)
    -   [❓ Why using PasarGuard?](#why-using-PasarGuard)
        -   [✨ Features](#features)
-   [🚀 Installation guide](#installation-guide)
-   [⚙️ Configuration](#configuration)
-   [📚 Documentation](#documentation)
-   [🔌 API](#api)
-   [💾 Backup](#backup)
-   [🤖 Telegram Bot](#telegram-bot)
-   [💻 PasarGuard CLI](#PasarGuard-cli)
-   [🌐 PasarGuard Node](#node)
-   [🔔 Webhook notifications](#webhook-notifications)
-   [💝 Donation](#donation)
-   [📄 License](#license)
-   [👥 Contributors](#contributors)

# 📖 Overview

<div align="center">

**PasarGuard** is a powerful proxy management tool that provides a simple and easy-to-use user interface for managing hundreds of proxy accounts. Built on [Xray-core](https://github.com/XTLS/Xray-core) and developed using Python and Reactjs.

</div>

## ❓ Why using PasarGuard?

<div align="center">

PasarGuard is user-friendly, feature-rich and reliable. It lets you create different proxies for your users without any complicated configuration. Using its built-in web UI, you are able to monitor, modify and limit users.

</div>

### ✨ Features

<div align="center">

| 🎯 **Core Features** | 🔧 **Technical Features** | 🌐 **Protocol Support** |
|:---:|:---:|:---:|
| 🌐 Built-in **Web UI** | 🔌 Fully **REST API** backend | 📡 **Vmess** Protocol |
| 📊 System monitoring | 🏗️ [**Multiple Nodes**](#node) support | 🚀 **VLESS** Protocol |
| 📈 **Traffic statistics** | ⚙️ Customizable xray configuration | 🛡️ **Trojan** Protocol |
| 🔗 **Subscription links** | 🔐 **TLS** and **REALITY** support | 🌙 **Shadowsocks** Protocol |
| 📱 **QRcode** generator | 🤖 Integrated **Telegram Bot** | 🔄 **Multi-protocol** support |
| 📅 **Traffic limitations** | 💻 Integrated **CLI** | 👥 **Multi-user** support |
| ⏰ **Periodic limits** | 🌍 **Multi-language** | 🔀 **Multi-inbound** support |
| 👨‍💼 **Multi-admin** support | 📦 **Docker** ready | 🎯 **Single port** fallbacks |

</div>

#### 🎯 **Key Capabilities:**

- ✅ **Built-in Web UI**
- ✅ **Fully REST API** backend
- ✅ **[Multiple Nodes](#node)** support
- ✅ **Multi-protocol** for a single user
- ✅ **Multi-user** on a single inbound
- ✅ **Multi-inbound** on a **single port**
- ✅ **Traffic** and **expiry date** limitations
- ✅ **Periodic** traffic limit (daily, weekly, etc.)
- ✅ **Subscription link** compatible with **V2ray**, **Clash** and **ClashMeta**
- ✅ Automated **Share link** and **QRcode** generator
- ✅ System monitoring and **traffic statistics**
- ✅ Customizable xray configuration
- ✅ **TLS** and **REALITY** support
- ✅ Integrated **Telegram Bot**
- ✅ Integrated **Command Line Interface (CLI)**
- ✅ **Multi-language** support
- ✅ **Multi-admin** support (WIP)

# 🚀 Installation guide

<div align="center">

## ⚠️ Warning

The following commands will install the pre-release versions (alpha/beta)

</div>

## 📦 Install with SQLite Database

```bash
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --pre-release
```

## 🗄️ Install with MySQL Database

```bash
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --database mysql --pre-release
```

## 🗃️ Install with MariaDB Database

```bash
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --database mariadb --pre-release
```

## 🐘 Install with PostgreSQL Database

```bash
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --database postgresql --pre-release
```

## ✅ After Installation Complete

<div align="center">

### 📋 Next Steps

</div>

- ✅ **Logs**: You will see the logs that you can stop watching them by closing the terminal or pressing `Ctrl+C`
- 📁 **Files Location**: The PasarGuard files will be located at `/opt/pasarguard`
- ⚙️ **Configuration**: The configuration file can be found at `/opt/pasarguard/.env`
- 💾 **Data Files**: The data files will be placed at `/var/lib/pasarguard`
- 🔒 **Security**: For security reasons, the PasarGuard dashboard is not accessible via IP address
- 🌐 **SSL Required**: You must [obtain SSL certificate](https://PasarGuard.github.io/PasarGuard/en/examples/issue-ssl-certificate) and access your PasarGuard dashboard by opening a web browser and navigating to `https://YOUR_DOMAIN:8000/dashboard/`

### 🔗 Local Access via SSH

```bash
ssh -L 8000:localhost:8000 user@serverip
```

Then navigate to the following link in your browser:

```
http://localhost:8000/dashboard/
```

⚠️ **Note**: You will lose access to the dashboard as soon as you close the SSH terminal. Therefore, this method is recommended only for testing purposes.

### 👨‍💼 Create Admin

```bash
pasarguard cli admin create --sudo
```

### ❓ Help

```bash
pasarguard --help
```

## 🔧 Manual Install (Advanced)

<div align="center">

If you are eager to run the project using the source code, check the section below

</div>

<details markdown="1">
<summary><h3>🔧 Manual install (advanced)</h3></summary>

### 🚀 Step 1: Install Xray

```bash
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
```

### 📥 Step 2: Clone Project

```bash
git clone https://github.com/PasarGuard/panel.git
cd PasarGuard
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
```

> **Note**: You need Python >= 3.12.7

### 🗄️ Step 3: Database Migration

```bash
uv run alembic upgrade head
```

### 💻 Step 4: Install CLI

```bash
sudo ln -s $(pwd)/PasarGuard-cli.py /usr/bin/pasarguard-cli
sudo chmod +x /usr/bin/pasarguard-cli
pasarguard-cli completion install
```

### ⚙️ Step 5: Configuration

```bash
cp .env.example .env
nano .env
```

> 📖 Check [configurations](#configuration) section for more information

### 🚀 Step 6: Run Application

```bash
uv run main.py
```

### 🔧 Run with systemctl

```bash
systemctl enable /var/lib/pasarguard/PasarGuard.service
systemctl start PasarGuard
```

### 🌐 Nginx Configuration

```nginx
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

### 🌐 Simple Nginx Configuration

```nginx
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

### 🌐 Dashboard Access

By default the app will be run on `http://localhost:8000/dashboard`. You can configure it using changing the `UVICORN_HOST` and `UVICORN_PORT` environment variables.

</details>

# ⚙️ Configuration

<div align="center">

You can set settings below using environment variables or placing them in `.env` file.

</div>

## 📋 Configuration Variables Table

| Variable | Description |
|:---:|:---:|
| `SUDO_USERNAME` | Superuser's username |
| `SUDO_PASSWORD` | Superuser's password |
| `SQLALCHEMY_DATABASE_URL` | Database URL |
| `SQLALCHEMY_POOL_SIZE` | Pool size (default: 10) |
| `SQLALCHEMY_MAX_OVERFLOW` | Max overflow (default: 30) |
| `UVICORN_HOST` | Bind host (default: 0.0.0.0) |
| `UVICORN_PORT` | Bind port (default: 8000) |
| `UVICORN_UDS` | UNIX domain socket |
| `UVICORN_SSL_CERTFILE` | SSL certificate file |
| `UVICORN_SSL_KEYFILE` | SSL key file |
| `UVICORN_SSL_CA_TYPE` | CA type (default: public) |
| `XRAY_JSON` | Xray config file path |
| `CUSTOM_TEMPLATES_DIRECTORY` | Custom templates directory |
| `CLASH_SUBSCRIPTION_TEMPLATE` | Clash subscription template |
| `SUBSCRIPTION_PAGE_TEMPLATE` | Subscription page template |
| `XRAY_SUBSCRIPTION_TEMPLATE` | Xray subscription template |
| `SINGBOX_SUBSCRIPTION_TEMPLATE` | SingBox subscription template |
| `HOME_PAGE_TEMPLATE` | Home page template |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Token expire time (minutes) |
| `DOCS` | Show API docs |
| `DEBUG` | Debug mode |
| `USERS_AUTODELETE_DAYS` | Auto-delete expired users |
| `USER_AUTODELETE_INCLUDE_LIMITED_ACCOUNTS` | Include limited accounts |
| `XRAY_SUBSCRIPTION_PATH` | Subscription API path |
| `ENABLE_RECORDING_NODES_STATS` | Record node statistics |

# 📚 Documentation

<div align="center">

The [PasarGuard Documentation](https://PasarGuard.github.io/PasarGuard) provides all the essential guides to get you started, available in three languages: Farsi, English, and Russian.

</div>

## 🤝 Contributing to Documentation

This documentation requires significant effort to cover all aspects of the project comprehensively. We welcome and appreciate your contributions to help us improve it.

[Documentation GitHub Repository](https://github.com/PasarGuard/PasarGuard.github.io)

# 🔌 API

<div align="center">

PasarGuard provides a REST API that enables developers to interact with PasarGuard services programmatically.

</div>

## 📖 View API Documentation

To view the API documentation in Swagger UI or ReDoc, set the configuration variable `DOCS=True` and navigate to the `/docs` and `/redoc`.

# 💾 Backup

<div align="center">

## 🔄 Automated Backup Service

It's always a good idea to backup your PasarGuard files regularly to prevent data loss in case of system failures or accidental deletion.

</div>

## 📋 Backup Steps

1. **📁 Important Files**: By default, all PasarGuard important files are saved in `/var/lib/pasarguard`
2. **⚙️ Configuration Files**: Make sure to backup your env file and Xray config file
3. **📂 Configuration Path**: If you installed PasarGuard using PasarGuard-scripts, configurations should be inside `/opt/pasarguard/` directory

## 🤖 Telegram Backup Service

PasarGuard's backup service efficiently zips all necessary files and sends them to your specified Telegram bot.

### ✨ Features

- ✅ Supports SQLite, MySQL and MariaDB
- ✅ Automation with hourly backup scheduling
- ✅ No Telegram upload limits (large files are split)
- ✅ Immediate backup at any time

### 🚀 Installation & Setup

```bash
# Install latest PasarGuard script
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install-script

# Setup backup service
pasarguard backup-service

# Get immediate backup
pasarguard backup
```

## 💡 Important Notes

- 🔄 Update your backups regularly
- 📁 Backup all data and configuration files
- 🔐 Don't forget env files and Xray configuration

# 🤖 Telegram Bot

<div align="center">

PasarGuard comes with an integrated Telegram bot that can handle server management, user creation and removal, and send notifications.

</div>

## ⚙️ Enable Telegram Bot

This bot can be easily enabled by following a few simple steps, and it provides a convenient way to interact with PasarGuard without having to log in to the server every time.

### 🔧 Setup Steps

1. **🔑 Set API Token**: Set `TELEGRAM_API_TOKEN` to your bot's API Token
2. **👤 Set Admin ID**: Set `TELEGRAM_ADMIN_ID` to your Telegram account's numeric ID

### 📱 Get Telegram ID

You can get your ID from [@userinfobot](https://t.me/userinfobot).

# 💻 PasarGuard CLI

<div align="center">

PasarGuard comes with an integrated CLI named `PasarGuard-cli` which allows administrators to have direct interaction with it.

</div>

## 🚀 Using CLI

If you've installed PasarGuard using easy install script, you can access the cli commands by running:

```bash
pasarguard cli [OPTIONS] COMMAND [ARGS]...
```

## 📖 CLI Documentation

For more information, You can read [PasarGuard CLI's documentation](./cli/README.md).

# 🖥️ PasarGuard TUI

<div align="center">

PasarGuard also provides a Terminal User Interface (TUI) for interactive management directly within your terminal.

</div>

## 🚀 Using TUI

If you've installed PasarGuard using the easy install script, you can access the TUI by running:

```bash
pasarguard tui
```

## 📖 TUI Documentation

For more information, you can read [PasarGuard TUI's documentation](./tui/README.md).

# 🌐 Node

<div align="center">

The PasarGuard project introduces the [node](https://github.com/PasarGuard/node), which revolutionizes infrastructure distribution.

</div>

## ✨ Node Benefits

With node, you can distribute your infrastructure across multiple locations, unlocking benefits such as:

- 🔄 **Redundancy**
- ⚡ **High Availability**  
- 📈 **Scalability**
- 🔧 **Flexibility**

## 🎯 User Flexibility

node empowers users to connect to different servers, offering them the flexibility to choose and connect to multiple servers instead of being limited to only one server.

## 📖 Node Documentation

For more detailed information and installation instructions, please refer to the [PasarGuard-node official documentation](https://github.com/PasarGuard/node)

# 🔔 Webhook notifications

<div align="center">

You can set a webhook address and PasarGuard will send the notifications to that address.

</div>

## 📡 How it Works

The requests will be sent as a post request to the address provided by `WEBHOOK_ADDRESS` with `WEBHOOK_SECRET` as `x-webhook-secret` in the headers.

## 📋 Example Request

```http
Headers:
Host: 0.0.0.0:9000
User-Agent: python-requests/2.28.1
Accept-Encoding: gzip, deflate
Accept: */*
Connection: keep-alive
x-webhook-secret: something-very-very-secret
Content-Length: 107
Content-Type: application/json

Body:
{"username": "PasarGuard_test_user", "action": "user_updated", "enqueued_at": 1680506457.636369, "tries": 0}
```

## 🎯 Action Types

Different action types are: `user_created`, `user_updated`, `user_deleted`, `user_limited`, `user_expired`, `user_disabled`, `user_enabled`

# 💝 Donation

<div align="center">

If you found PasarGuard useful and would like to support its development, you can make a donation.

</div>

## 🎯 Support the Project

[Make a Donation](https://donate.gozargah.pro)

Thank you for your support!

# 📄 License

<div align="center">

Made in [Unknown!] and Published under [AGPL-3.0](./LICENSE).

</div>

# 👥 Contributors

<div align="center">

We ❤️‍🔥 contributors! If you'd like to contribute, please check out our [Contributing Guidelines](CONTRIBUTING.md) and feel free to submit a pull request or open an issue.

</div>

## 🤝 Join the Community

We also welcome you to join our [Telegram](https://t.me/Pasar_Guard) group for either support or contributing guidance.

## 🐛 Help Project Progress

Check [open issues](https://github.com/PasarGuard/panel/issues) to help the progress of this project.

<div align="center">

## 🙏 Thanks to Contributors

Thanks to the all contributors who have helped improve PasarGuard:

</div>

<div align="center">

<a href="https://github.com/PasarGuard/panel/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=PasarGuard/panel" />
</a>

</div>

<div align="center">

Made with <a rel="noopener noreferrer" target="_blank" href="https://contrib.rocks">contrib.rocks</a>

</div>
