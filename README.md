<div align="center">

# 🛡️ PasarGuard

[![PasarGuard Logo](https://github.com/PasarGuard/docs/blob/main/logos/PasarGuard-black-logo.png)](https://github.com/PasarGuard/panel)

### راه‌حل یکپارچه مقاوم در برابر سانسور با رابط گرافیکی

**Unified GUI Censorship Resistant Solution**

</div>

<div align="center">

## 📊 وضعیت پروژه | Project Status

[![Build Status](https://img.shields.io/github/actions/workflow/status/PasarGuard/panel/build.yml?style=for-the-badge&label=Build&logo=github)](https://github.com/PasarGuard/panel/actions)
[![Docker Pulls](https://img.shields.io/docker/pulls/PasarGuard/panel?style=for-the-badge&label=Docker%20Pulls&logo=docker)](https://hub.docker.com/r/PasarGuard/panel)
[![License](https://img.shields.io/github/license/PasarGuard/panel?style=for-the-badge&label=License&logo=opensourceinitiative)](https://github.com/PasarGuard/panel/blob/main/LICENSE)
[![Telegram](https://img.shields.io/badge/Telegram-Group-2CA5E0?style=for-the-badge&logo=telegram&logoColor=white)](https://t.me/Pasar_Guard)
[![GitHub Stars](https://img.shields.io/github/stars/PasarGuard/panel?style=for-the-badge&label=Stars&logo=github)](https://github.com/PasarGuard/panel)

</div>

<div align="center">

## 🌍 زبان‌ها | Languages

[![English](https://img.shields.io/badge/English-🇺🇸-blue?style=for-the-badge)](./README.md)
[![فارسی](https://img.shields.io/badge/فارسی-🇮🇷-green?style=for-the-badge)](./README-fa.md)
[![简体中文](https://img.shields.io/badge/简体中文-🇨🇳-red?style=for-the-badge)](./README-zh-cn.md)
[![Русский](https://img.shields.io/badge/Русский-🇷🇺-orange?style=for-the-badge)](./README-ru.md)

</div>

<div align="center">

## 🖼️ پیش‌نمایش | Preview

[![PasarGuard Dashboard Preview](https://github.com/PasarGuard/docs/raw/master/screenshots/preview.png)](https://github.com/PasarGuard/panel)

*کلیک کنید تا تصویر بزرگ‌تر را ببینید | Click to view larger image*

</div>

## 📋 فهرست مطالب | Table of Contents

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

**PasarGuard** ابزاری قدرتمند برای مدیریت پروکسی است که رابط کاربری ساده و آسانی برای مدیریت صدها حساب پروکسی فراهم می‌کند. این ابزار بر پایه [Xray-core](https://github.com/XTLS/Xray-core) ساخته شده و با استفاده از Python و Reactjs توسعه یافته است.

**PasarGuard** is a powerful proxy management tool that provides a simple and easy-to-use user interface for managing hundreds of proxy accounts. Built on [Xray-core](https://github.com/XTLS/Xray-core) and developed using Python and Reactjs.

</div>

## ❓ Why using PasarGuard?

<div align="center">

PasarGuard کاربرپسند، غنی از ویژگی و قابل اعتماد است. این ابزار به شما امکان ایجاد پروکسی‌های مختلف برای کاربرانتان بدون هیچ پیکربندی پیچیده‌ای را می‌دهد. با استفاده از رابط وب داخلی آن، می‌توانید کاربران را نظارت، تغییر و محدود کنید.

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

- ✅ **Built-in Web UI** - رابط کاربری وب داخلی
- ✅ **Fully REST API** backend - بک‌اند API کامل
- ✅ **[Multiple Nodes](#node)** support - پشتیبانی از چندین نود
- ✅ **Multi-protocol** for a single user - چندین پروتکل برای یک کاربر
- ✅ **Multi-user** on a single inbound - چندین کاربر روی یک inbound
- ✅ **Multi-inbound** on a **single port** - چندین inbound روی یک پورت
- ✅ **Traffic** and **expiry date** limitations - محدودیت ترافیک و تاریخ انقضا
- ✅ **Periodic** traffic limit (daily, weekly, etc.) - محدودیت ترافیک دوره‌ای
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

## ⚠️ هشدار | Warning

دستورات زیر نسخه‌های پیش‌انتشار (آلفا/بتا) را نصب می‌کنند

The following commands will install the pre-release versions (alpha/beta)

</div>

## 📦 نصب با پایگاه داده SQLite | Install with SQLite Database

```bash
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --pre-release
```

## 🗄️ نصب با پایگاه داده MySQL | Install with MySQL Database

```bash
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --database mysql --pre-release
```

## 🗃️ نصب با پایگاه داده MariaDB | Install with MariaDB Database

```bash
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --database mariadb --pre-release
```

## 🐘 نصب با پایگاه داده PostgreSQL | Install with PostgreSQL Database

```bash
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --database postgresql --pre-release
```

## ✅ پس از تکمیل نصب | After Installation Complete

<div align="center">

### 📋 مراحل بعدی | Next Steps

</div>

- ✅ **Logs**: شما لاگ‌ها را خواهید دید که می‌توانید با بستن ترمینال یا فشردن `Ctrl+C` آن‌ها را متوقف کنید
- 📁 **Files Location**: فایل‌های PasarGuard در `/opt/pasarguard` قرار خواهند گرفت
- ⚙️ **Configuration**: فایل پیکربندی در `/opt/pasarguard/.env` یافت می‌شود
- 💾 **Data Files**: فایل‌های داده در `/var/lib/pasarguard` قرار خواهند گرفت
- 🔒 **Security**: داشبورد PasarGuard به دلایل امنیتی از طریق آدرس IP قابل دسترسی نیست
- 🌐 **SSL Required**: باید [گواهی SSL دریافت کنید](https://PasarGuard.github.io/PasarGuard/en/examples/issue-ssl-certificate) و به `https://YOUR_DOMAIN:8000/dashboard/` دسترسی پیدا کنید

### 🔗 دسترسی محلی با SSH | Local Access via SSH

```bash
ssh -L 8000:localhost:8000 user@serverip
```

سپس در مرورگر خود به آدرس زیر بروید:

Then navigate to the following link in your browser:

```
http://localhost:8000/dashboard/
```

⚠️ **توجه**: دسترسی به داشبورد با بستن ترمینال SSH از بین می‌رود. این روش فقط برای تست توصیه می‌شود.

### 👨‍💼 ایجاد ادمین | Create Admin

```bash
pasarguard cli admin create --sudo
```

### ❓ راهنمایی | Help

```bash
pasarguard --help
```

## 🔧 نصب دستی (پیشرفته) | Manual Install (Advanced)

<div align="center">

اگر می‌خواهید پروژه را با کد منبع اجرا کنید، بخش زیر را بررسی کنید

If you are eager to run the project using the source code, check the section below

</div>

<details markdown="1">
<summary><h3>🔧 Manual install (advanced) | نصب دستی (پیشرفته)</h3></summary>

### 🚀 مرحله 1: نصب Xray | Step 1: Install Xray

```bash
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
```

### 📥 مرحله 2: کلون پروژه | Step 2: Clone Project

```bash
git clone https://github.com/PasarGuard/panel.git
cd PasarGuard
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
```

> **نکته**: شما به Python >= 3.12.7 نیاز دارید | You need Python >= 3.12.7

### 🗄️ مرحله 3: مهاجرت پایگاه داده | Step 3: Database Migration

```bash
uv run alembic upgrade head
```

### 💻 مرحله 4: نصب CLI | Step 4: Install CLI

```bash
sudo ln -s $(pwd)/PasarGuard-cli.py /usr/bin/pasarguard-cli
sudo chmod +x /usr/bin/pasarguard-cli
pasarguard-cli completion install
```

### ⚙️ مرحله 5: پیکربندی | Step 5: Configuration

```bash
cp .env.example .env
nano .env
```

> 📖 برای اطلاعات بیشتر بخش [پیکربندی](#configuration) را بررسی کنید | Check [configurations](#configuration) section for more information

### 🚀 مرحله 6: اجرای برنامه | Step 6: Run Application

```bash
uv run main.py
```

### 🔧 اجرا با systemctl | Run with systemctl

```bash
systemctl enable /var/lib/pasarguard/PasarGuard.service
systemctl start PasarGuard
```

### 🌐 پیکربندی Nginx | Nginx Configuration

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

### 🌐 پیکربندی ساده Nginx | Simple Nginx Configuration

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

### 🌐 دسترسی به داشبورد | Dashboard Access

به طور پیش‌فرض برنامه روی `http://localhost:8000/dashboard` اجرا می‌شود. می‌توانید با تغییر متغیرهای محیطی `UVICORN_HOST` و `UVICORN_PORT` آن را پیکربندی کنید.

By default the app will be run on `http://localhost:8000/dashboard`. You can configure it using changing the `UVICORN_HOST` and `UVICORN_PORT` environment variables.

</details>

# ⚙️ Configuration

<div align="center">

می‌توانید تنظیمات زیر را با استفاده از متغیرهای محیطی یا قرار دادن آن‌ها در فایل `.env` تنظیم کنید.

You can set settings below using environment variables or placing them in `.env` file.

</div>

## 📋 جدول متغیرهای پیکربندی | Configuration Variables Table

| متغیر | Variable | توضیحات | Description |
|:---:|:---:|:---:|:---:|
| `SUDO_USERNAME` | SUDO_USERNAME | نام کاربری سوپرکاربر | Superuser's username |
| `SUDO_PASSWORD` | SUDO_PASSWORD | رمز عبور سوپرکاربر | Superuser's password |
| `SQLALCHEMY_DATABASE_URL` | SQLALCHEMY_DATABASE_URL | آدرس پایگاه داده | Database URL |
| `SQLALCHEMY_POOL_SIZE` | SQLALCHEMY_POOL_SIZE | اندازه پول اتصال (پیش‌فرض: 10) | Pool size (default: 10) |
| `SQLALCHEMY_MAX_OVERFLOW` | SQLALCHEMY_MAX_OVERFLOW | حداکثر سرریز (پیش‌فرض: 30) | Max overflow (default: 30) |
| `UVICORN_HOST` | UVICORN_HOST | میزبان اتصال (پیش‌فرض: 0.0.0.0) | Bind host (default: 0.0.0.0) |
| `UVICORN_PORT` | UVICORN_PORT | پورت اتصال (پیش‌فرض: 8000) | Bind port (default: 8000) |
| `UVICORN_UDS` | UVICORN_UDS | اتصال به سوکت دامنه UNIX | UNIX domain socket |
| `UVICORN_SSL_CERTFILE` | UVICORN_SSL_CERTFILE | فایل گواهی SSL | SSL certificate file |
| `UVICORN_SSL_KEYFILE` | UVICORN_SSL_KEYFILE | فایل کلید SSL | SSL key file |
| `UVICORN_SSL_CA_TYPE` | UVICORN_SSL_CA_TYPE | نوع گواهی CA (پیش‌فرض: public) | CA type (default: public) |
| `XRAY_JSON` | XRAY_JSON | مسیر فایل پیکربندی Xray | Xray config file path |
| `CUSTOM_TEMPLATES_DIRECTORY` | CUSTOM_TEMPLATES_DIRECTORY | مسیر قالب‌های سفارشی | Custom templates directory |
| `CLASH_SUBSCRIPTION_TEMPLATE` | CLASH_SUBSCRIPTION_TEMPLATE | قالب اشتراک Clash | Clash subscription template |
| `SUBSCRIPTION_PAGE_TEMPLATE` | SUBSCRIPTION_PAGE_TEMPLATE | قالب صفحه اشتراک | Subscription page template |
| `XRAY_SUBSCRIPTION_TEMPLATE` | XRAY_SUBSCRIPTION_TEMPLATE | قالب اشتراک Xray | Xray subscription template |
| `SINGBOX_SUBSCRIPTION_TEMPLATE` | SINGBOX_SUBSCRIPTION_TEMPLATE | قالب اشتراک SingBox | SingBox subscription template |
| `HOME_PAGE_TEMPLATE` | HOME_PAGE_TEMPLATE | قالب صفحه اصلی | Home page template |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | JWT_ACCESS_TOKEN_EXPIRE_MINUTES | زمان انقضای توکن (دقیقه) | Token expire time (minutes) |
| `DOCS` | DOCS | نمایش مستندات API | Show API docs |
| `DEBUG` | DEBUG | حالت دیباگ | Debug mode |
| `USERS_AUTODELETE_DAYS` | USERS_AUTODELETE_DAYS | حذف خودکار کاربران منقضی | Auto-delete expired users |
| `USER_AUTODELETE_INCLUDE_LIMITED_ACCOUNTS` | USER_AUTODELETE_INCLUDE_LIMITED_ACCOUNTS | شامل حساب‌های محدود | Include limited accounts |
| `XRAY_SUBSCRIPTION_PATH` | XRAY_SUBSCRIPTION_PATH | مسیر API اشتراک | Subscription API path |
| `ENABLE_RECORDING_NODES_STATS` | ENABLE_RECORDING_NODES_STATS | ثبت آمار نودها | Record node statistics |

# 📚 Documentation

<div align="center">

[مستندات PasarGuard](https://PasarGuard.github.io/PasarGuard) تمام راهنمای‌های ضروری برای شروع کار را فراهم می‌کند و به سه زبان فارسی، انگلیسی و روسی در دسترس است.

The [PasarGuard Documentation](https://PasarGuard.github.io/PasarGuard) provides all the essential guides to get you started, available in three languages: Farsi, English, and Russian.

</div>

## 🤝 مشارکت در مستندات | Contributing to Documentation

این مستندات نیاز به تلاش قابل توجهی برای پوشش جامع تمام جنبه‌های پروژه دارد. ما از مشارکت شما برای بهبود آن استقبال می‌کنیم.

This documentation requires significant effort to cover all aspects of the project comprehensively. We welcome and appreciate your contributions to help us improve it.

[مخزن GitHub مستندات](https://github.com/PasarGuard/PasarGuard.github.io) | [Documentation GitHub Repository](https://github.com/PasarGuard/PasarGuard.github.io)

# 🔌 API

<div align="center">

PasarGuard یک REST API فراهم می‌کند که به توسعه‌دهندگان امکان تعامل برنامه‌نویسی با سرویس‌های PasarGuard را می‌دهد.

PasarGuard provides a REST API that enables developers to interact with PasarGuard services programmatically.

</div>

## 📖 مشاهده مستندات API | View API Documentation

برای مشاهده مستندات API در Swagger UI یا ReDoc، متغیر پیکربندی `DOCS=True` را تنظیم کنید و به `/docs` و `/redoc` بروید.

To view the API documentation in Swagger UI or ReDoc, set the configuration variable `DOCS=True` and navigate to the `/docs` and `/redoc`.

# 💾 Backup

<div align="center">

## 🔄 سرویس پشتیبان‌گیری خودکار | Automated Backup Service

همیشه ایده خوبی است که فایل‌های PasarGuard خود را به طور منظم پشتیبان‌گیری کنید تا از از دست رفتن داده در صورت خرابی سیستم یا حذف تصادفی جلوگیری کنید.

It's always a good idea to backup your PasarGuard files regularly to prevent data loss in case of system failures or accidental deletion.

</div>

## 📋 مراحل پشتیبان‌گیری | Backup Steps

1. **📁 فایل‌های مهم**: به طور پیش‌فرض، تمام فایل‌های مهم PasarGuard در `/var/lib/pasarguard` ذخیره می‌شوند
2. **⚙️ فایل پیکربندی**: فایل env و فایل پیکربندی Xray را نیز پشتیبان‌گیری کنید
3. **📂 مسیر پیکربندی**: اگر با اسکریپت PasarGuard نصب کرده‌اید، پیکربندی‌ها در `/opt/pasarguard/` قرار دارند

## 🤖 سرویس پشتیبان‌گیری تلگرام | Telegram Backup Service

سرویس پشتیبان‌گیری PasarGuard به طور کارآمد تمام فایل‌های ضروری را فشرده می‌کند و آن‌ها را به ربات تلگرام مشخص شده شما ارسال می‌کند.

### ✨ ویژگی‌ها | Features

- ✅ پشتیبانی از SQLite، MySQL و MariaDB
- ✅ خودکارسازی با امکان زمان‌بندی پشتیبان‌گیری هر ساعت
- ✅ بدون محدودیت آپلود تلگرام (فایل‌های بزرگ تقسیم می‌شوند)
- ✅ امکان پشتیبان‌گیری فوری در هر زمان

### 🚀 نصب و راه‌اندازی | Installation & Setup

```bash
# نصب آخرین نسخه اسکریپت PasarGuard
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install-script

# راه‌اندازی سرویس پشتیبان‌گیری
pasarguard backup-service

# پشتیبان‌گیری فوری
pasarguard backup
```

## 💡 نکات مهم | Important Notes

- 🔄 پشتیبان‌گیری‌ها را به طور منظم به‌روزرسانی کنید
- 📁 تمام فایل‌های داده و پیکربندی را پشتیبان‌گیری کنید
- 🔐 فایل‌های env و پیکربندی Xray را فراموش نکنید

# 🤖 Telegram Bot

<div align="center">

PasarGuard با یک ربات تلگرام یکپارچه همراه است که می‌تواند مدیریت سرور، ایجاد و حذف کاربران و ارسال اعلان‌ها را انجام دهد.

PasarGuard comes with an integrated Telegram bot that can handle server management, user creation and removal, and send notifications.

</div>

## ⚙️ راه‌اندازی ربات تلگرام | Enable Telegram Bot

این ربات را می‌توان با دنبال کردن چند مرحله ساده به راحتی فعال کرد و راهی راحت برای تعامل با PasarGuard بدون نیاز به ورود به سرور در هر بار فراهم می‌کند.

This bot can be easily enabled by following a few simple steps, and it provides a convenient way to interact with PasarGuard without having to log in to the server every time.

### 🔧 مراحل راه‌اندازی | Setup Steps

1. **🔑 تنظیم توکن API**: `TELEGRAM_API_TOKEN` را به توکن API ربات خود تنظیم کنید
2. **👤 تنظیم شناسه ادمین**: `TELEGRAM_ADMIN_ID` را به شناسه عددی حساب تلگرام خود تنظیم کنید

### 📱 دریافت شناسه تلگرام | Get Telegram ID

می‌توانید شناسه خود را از [@userinfobot](https://t.me/userinfobot) دریافت کنید.

You can get your ID from [@userinfobot](https://t.me/userinfobot).

# 💻 PasarGuard CLI

<div align="center">

PasarGuard با یک CLI یکپارچه به نام `PasarGuard-cli` همراه است که به مدیران امکان تعامل مستقیم با آن را می‌دهد.

PasarGuard comes with an integrated CLI named `PasarGuard-cli` which allows administrators to have direct interaction with it.

</div>

## 🚀 استفاده از CLI | Using CLI

اگر PasarGuard را با اسکریپت نصب آسان نصب کرده‌اید، می‌توانید با اجرای دستور زیر به دستورات CLI دسترسی پیدا کنید:

If you've installed PasarGuard using easy install script, you can access the cli commands by running:

```bash
pasarguard cli [OPTIONS] COMMAND [ARGS]...
```

## 📖 مستندات CLI | CLI Documentation

برای اطلاعات بیشتر، می‌توانید [مستندات PasarGuard CLI](./cli/README.md) را مطالعه کنید.

For more information, You can read [PasarGuard CLI's documentation](./cli/README.md).

# 🖥️ PasarGuard TUI

<div align="center">

PasarGuard همچنین یک رابط کاربری ترمینال (TUI) برای مدیریت تعاملی مستقیماً در ترمینال شما فراهم می‌کند.

PasarGuard also provides a Terminal User Interface (TUI) for interactive management directly within your terminal.

</div>

## 🚀 استفاده از TUI | Using TUI

اگر PasarGuard را با اسکریپت نصب آسان نصب کرده‌اید، می‌توانید با اجرای دستور زیر به TUI دسترسی پیدا کنید:

If you've installed PasarGuard using the easy install script, you can access the TUI by running:

```bash
pasarguard tui
```

## 📖 مستندات TUI | TUI Documentation

برای اطلاعات بیشتر، می‌توانید [مستندات PasarGuard TUI](./tui/README.md) را مطالعه کنید.

For more information, you can read [PasarGuard TUI's documentation](./tui/README.md).

# 🌐 Node

<div align="center">

پروژه PasarGuard [node](https://github.com/PasarGuard/node) را معرفی می‌کند که توزیع زیرساخت را متحول می‌کند.

The PasarGuard project introduces the [node](https://github.com/PasarGuard/node), which revolutionizes infrastructure distribution.

</div>

## ✨ مزایای Node | Node Benefits

با node، می‌توانید زیرساخت خود را در چندین مکان توزیع کنید و از مزایایی مانند:

With node, you can distribute your infrastructure across multiple locations, unlocking benefits such as:

- 🔄 **Redundancy** - افزونگی
- ⚡ **High Availability** - در دسترس بودن بالا  
- 📈 **Scalability** - مقیاس‌پذیری
- 🔧 **Flexibility** - انعطاف‌پذیری

## 🎯 انعطاف کاربران | User Flexibility

node به کاربران امکان اتصال به سرورهای مختلف را می‌دهد و انعطاف انتخاب و اتصال به چندین سرور به جای محدودیت به یک سرور را فراهم می‌کند.

node empowers users to connect to different servers, offering them the flexibility to choose and connect to multiple servers instead of being limited to only one server.

## 📖 مستندات Node | Node Documentation

برای اطلاعات تفصیلی و دستورالعمل‌های نصب، لطفاً به [مستندات رسمی PasarGuard-node](https://github.com/PasarGuard/node) مراجعه کنید.

For more detailed information and installation instructions, please refer to the [PasarGuard-node official documentation](https://github.com/PasarGuard/node)

# 🔔 Webhook notifications

<div align="center">

می‌توانید یک آدرس webhook تنظیم کنید و PasarGuard اعلان‌ها را به آن آدرس ارسال کند.

You can set a webhook address and PasarGuard will send the notifications to that address.

</div>

## 📡 نحوه کارکرد | How it Works

درخواست‌ها به عنوان درخواست POST به آدرس ارائه شده توسط `WEBHOOK_ADDRESS` با `WEBHOOK_SECRET` به عنوان `x-webhook-secret` در هدرها ارسال می‌شوند.

The requests will be sent as a post request to the address provided by `WEBHOOK_ADDRESS` with `WEBHOOK_SECRET` as `x-webhook-secret` in the headers.

## 📋 مثال درخواست | Example Request

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

## 🎯 انواع عملیات | Action Types

انواع مختلف عملیات عبارتند از: `user_created`, `user_updated`, `user_deleted`, `user_limited`, `user_expired`, `user_disabled`, `user_enabled`

Different action types are: `user_created`, `user_updated`, `user_deleted`, `user_limited`, `user_expired`, `user_disabled`, `user_enabled`

# 💝 Donation

<div align="center">

اگر PasarGuard را مفید یافتید و می‌خواهید از توسعه آن پشتیبانی کنید، می‌توانید کمک مالی کنید.

If you found PasarGuard useful and would like to support its development, you can make a donation.

</div>

## 🎯 حمایت از پروژه | Support the Project

[کمک مالی کنید](https://donate.gozargah.pro) | [Make a Donation](https://donate.gozargah.pro)

از حمایت شما متشکریم! | Thank you for your support!

# 📄 License

<div align="center">

ساخته شده در [نامشخص!] و منتشر شده تحت [AGPL-3.0](./LICENSE).

Made in [Unknown!] and Published under [AGPL-3.0](./LICENSE).

</div>

# 👥 Contributors

<div align="center">

ما ❤️‍🔥 مشارکت‌کنندگان را دوست داریم! اگر می‌خواهید مشارکت کنید، لطفاً [راهنمای مشارکت](CONTRIBUTING.md) ما را بررسی کنید و آزادانه یک pull request ارسال کنید یا issue باز کنید.

We ❤️‍🔥 contributors! If you'd like to contribute, please check out our [Contributing Guidelines](CONTRIBUTING.md) and feel free to submit a pull request or open an issue.

</div>

## 🤝 پیوستن به جامعه | Join the Community

همچنین از شما دعوت می‌کنیم به گروه [تلگرام](https://t.me/Pasar_Guard) ما برای پشتیبانی یا راهنمایی مشارکت بپیوندید.

We also welcome you to join our [Telegram](https://t.me/Pasar_Guard) group for either support or contributing guidance.

## 🐛 کمک به پیشرفت پروژه | Help Project Progress

[مسائل باز](https://github.com/PasarGuard/panel/issues) را بررسی کنید تا به پیشرفت این پروژه کمک کنید.

Check [open issues](https://github.com/PasarGuard/panel/issues) to help the progress of this project.

<div align="center">

## 🙏 تشکر از مشارکت‌کنندگان | Thanks to Contributors

از تمام مشارکت‌کنندگانی که به بهبود PasarGuard کمک کرده‌اند متشکریم:

Thanks to the all contributors who have helped improve PasarGuard:

</div>

<div align="center">

<a href="https://github.com/PasarGuard/panel/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=PasarGuard/panel" />
</a>

</div>

<div align="center">

ساخته شده با <a rel="noopener noreferrer" target="_blank" href="https://contrib.rocks">contrib.rocks</a>

Made with <a rel="noopener noreferrer" target="_blank" href="https://contrib.rocks">contrib.rocks</a>

</div>
