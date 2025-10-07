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

## ✨ What is PasarGuard?

PasarGuard is a powerful proxy management tool that provides a simple, user-friendly interface for managing hundreds of proxy accounts. Built with Python and React, it's powered by [Xray-core](https://github.com/XTLS/Xray-core) for maximum performance and reliability.

### 🚀 Key Features

- 🌐 **Built-in Web UI** - Intuitive dashboard for easy management
- 🔌 **REST API** - Full programmatic access
- 🌍 **Multi-Node Support** - Distribute infrastructure across locations
- 🔐 **Multiple Protocols** - VMess, VLESS, Trojan, Shadowsocks
- 📊 **Traffic Management** - Limits, expiry dates, periodic restrictions
- 🔗 **Subscription Links** - Compatible with V2Ray, Clash, ClashMeta
- 📱 **QR Code Generation** - Instant sharing capabilities
- 📈 **Real-time Statistics** - Monitor usage and performance
- 🔒 **TLS & REALITY** - Advanced security features
- 🤖 **Telegram Bot** - Manage via Telegram
- 💻 **CLI & TUI** - Command-line interfaces
- 🌐 **Multi-language** - Support for multiple languages

## 🚀 Quick Start

### One-Command Installation

Choose your preferred database:

```bash
# SQLite (Default)
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --pre-release

# MySQL
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --database mysql --pre-release

# MariaDB
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --database mariadb --pre-release

# PostgreSQL
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --database postgresql --pre-release
```

### 🎯 Post-Installation Steps

1. **Access Dashboard**: Navigate to `https://YOUR_DOMAIN:8000/dashboard/`
2. **Create Admin**: Run `pasarguard cli admin create --sudo`
3. **Login**: Use your credentials to access the dashboard

> 💡 **Tip**: For testing without a domain, use SSH port forwarding:
> ```bash
> ssh -L 8000:localhost:8000 user@serverip
> ```
> Then access: `http://localhost:8000/dashboard/`

## ⚙️ Configuration

Key environment variables (set in `.env` file):

| Variable | Description | Default |
|----------|-------------|---------|
| `SUDO_USERNAME` | Superuser username | - |
| `SUDO_PASSWORD` | Superuser password | - |
| `SQLALCHEMY_DATABASE_URL` | Database connection URL | - |
| `UVICORN_HOST` | Application host | `0.0.0.0` |
| `UVICORN_PORT` | Application port | `8000` |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | Token expiry (minutes) | `1440` |
| `DOCS` | Enable API documentation | `False` |

> 📖 **Full Configuration**: See the [Configuration Section](#configuration) for complete details

## 📚 Documentation & Resources

- 📖 **[Official Documentation](https://PasarGuard.github.io/PasarGuard)** - Complete guides in Farsi, English, and Russian
- 🔧 **[API Documentation](./docs)** - REST API reference (enable with `DOCS=True`)
- 💬 **[Telegram Support](https://t.me/Pasar_Guard)** - Community help and updates

## 🛠️ Advanced Features

### 🤖 Telegram Bot
Enable server management via Telegram:
```bash
# Set in .env file
TELEGRAM_API_TOKEN=your_bot_token
TELEGRAM_ADMIN_ID=your_telegram_id
```

### 💻 Command Line Interface
```bash
pasarguard cli [OPTIONS] COMMAND [ARGS]...
```

### 🖥️ Terminal User Interface
```bash
pasarguard tui
```

### 🌐 Multi-Node Support
Distribute your infrastructure across multiple locations for:
- ✅ High availability
- ✅ Load balancing
- ✅ Geographic distribution
- ✅ Redundancy

[Learn more about PasarGuard Node](https://github.com/PasarGuard/node)

### 🔔 Webhook Notifications
Set `WEBHOOK_ADDRESS` and `WEBHOOK_SECRET` in your `.env` file to receive real-time notifications.

## 💾 Backup & Recovery

### Automated Backup Service
```bash
# Install backup service
pasarguard backup-service

# Create immediate backup
pasarguard backup
```

### Manual Backup
Backup these directories:
- `/var/lib/pasarguard` (data files)
- `/opt/pasarguard/.env` (configuration)

## 🏗️ Manual Installation (Advanced)

<details>
<summary>Click to expand manual installation steps</summary>

```bash
# Install Xray
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install

# Clone and setup
git clone https://github.com/PasarGuard/panel.git
cd PasarGuard
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync

# Database migration
uv run alembic upgrade head

# Configuration
cp .env.example .env
nano .env

# Run application
uv run main.py
```

</details>

## 🤝 Contributing

We ❤️ contributors! Help us improve PasarGuard:

- 🐛 [Report Issues](https://github.com/PasarGuard/panel/issues)
- 📝 [Contribute Code](CONTRIBUTING.md)
- 💬 [Join Telegram](https://t.me/Pasar_Guard)

## 💖 Support PasarGuard

If PasarGuard helps you, consider supporting its development:

[![Donate](https://img.shields.io/badge/Donate-Support%20Us-green?style=for-the-badge)](http://donate.pasarguard.org)

## 📄 License

Made with ❤️ and published under [AGPL-3.0](./LICENSE).

---

<div align="center">

### 🌟 Contributors

Thanks to all contributors who help improve PasarGuard:

<a href="https://github.com/PasarGuard/panel/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=PasarGuard/panel" />
</a>

Made with [contrib.rocks](https://contrib.rocks)

</div>
