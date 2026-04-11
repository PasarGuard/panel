<p align="center">
  <a href="https://github.com/PasarGuard/panel" target="_blank" rel="noopener noreferrer">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://github.com/PasarGuard/PasarGuard.github.io/raw/main/public/logos/PasarGuard-white-logo.png">
      <img width="160" height="160" src="https://github.com/PasarGuard/PasarGuard.github.io/raw/main/public/logos/PasarGuard-black-logo.png">
    </picture>
  </a>
</p>

<h1 align="center">🛡️ پاسارگارد</h1>

<p align="center">
    <strong>راه‌حل یکپارچه و مقاوم در برابر سانسور برای مدیریت پروکسی</strong>
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
 🇺🇸 English
 </a>
 /
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
    <img src="https://github.com/PasarGuard/PasarGuard.github.io/raw/main/public/logos/screenshot.png" alt="پاسارگارد اسکرین‌شات" width="600" height="auto">
  </a>
</p>

## 📋 فهرست مطالب

> **ناوبری سریع** - به هر بخش زیر پرش کنید

-   [📖 بررسی اجمالی](#-بررسی-اجمالی)
    -   [🤔 چرا از پاسارگارد استفاده کنیم؟](#-چرا-از-پاسارگارد-استفاده-کنیم)
        -   [✨ ویژگی‌ها](#-ویژگیها)
-   [🚀 راهنمای نصب](#-راهنمای-نصب)
-   [📚 مستندات](#-مستندات)
-   [💖 حمایت مالی](#-حمایت-مالی)

---

# 📖 بررسی اجمالی

> **پاسارگارد چیست؟**

پاسارگارد یک ابزار قدرتمند مدیریت پروکسی است که رابط کاربری بصری و کارآمدی برای مدیریت صدها حساب پروکسی ارائه می‌دهد. این ابزار با Python و React.js ساخته شده و عملکرد، مقیاس‌پذیری و سهولت استفاده را برای ساده‌سازی مدیریت پروکسی در مقیاس بزرگ ترکیب می‌کند. این ابزار هم از [Xray-core](https://github.com/XTLS/Xray-core) و هم از [WireGuard](https://www.wireguard.com/) برای حداکثر عملکرد پشتیبانی می‌کند.

---

## 🤔 چرا از پاسارگارد استفاده کنیم؟

> **ساده، قدرتمند، قابل اعتماد**

پاسارگارد یک ابزار مدیریت پروکسی کاربرپسند، غنی از ویژگی و قابل اعتماد است. این ابزار به شما امکان ایجاد و مدیریت چندین پروکسی برای کاربران بدون نیاز به پیکربندی پیچیده را می‌دهد. با رابط کاربری وب داخلی آن، می‌توانید به راحتی فعالیت‌ها را نظارت کنید، تنظیمات را تغییر دهید و محدودیت‌های دسترسی کاربران را کنترل کنید — همه از یک داشبورد مناسب.

---

### ✨ ویژگی‌ها

<div align="right">

**🌐 رابط کاربری وب و API**
- داشبورد **Web UI** داخلی
- بک‌اند کاملاً **REST API**
- پشتیبانی از **Multi-Node** برای توزیع زیرساخت

**🔐 پروتکل‌ها و امنیت**
- پشتیبانی از **Vmess**، **VLESS**، **Trojan**، **Shadowsocks**، **WireGuard** و **Hysteria2**
- پشتیبانی از **TLS** و **REALITY**
- **چند پروتکل** برای یک کاربر

**👥 مدیریت کاربران**
- **چند کاربر** روی یک inbound
- **چند inbound** روی **یک پورت** (پشتیبانی از fallbacks)
- محدودیت‌های **ترافیک** و **تاریخ انقضا**
- محدودیت ترافیک **دوره‌ای** (روزانه، هفتگی و غیره)

**🔗 اشتراک‌ها و اشتراک‌گذاری**
- **لینک اشتراک** سازگار با **V2ray**، **Clash** و **ClashMeta**
- تولیدکننده خودکار **لینک اشتراک** و **QRcode**
- نظارت بر سیستم و **آمار ترافیک**

**🛠️ ابزارها و سفارشی‌سازی**
- پیکربندی قابل تنظیم xray
- **ربات تلگرام** یکپارچه
- **رابط خط فرمان (CLI)**
- پشتیبانی از **چند زبان**
- پشتیبانی از **چند ادمین** (در حال توسعه)

</div>

---

# 🚀 راهنمای نصب

> **شروع سریع** - پاسارگارد را در چند دقیقه راه‌اندازی کنید

### برای راه‌اندازی سریع، از دستورات زیر بر اساس دیتابیس مورد نظرتان استفاده کنید.

---

**TimescaleDB (توصیه شده):**
```bash
curl -fsSL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh -o /tmp/pg.sh \
  && sudo bash /tmp/pg.sh install --database timescaledb
```

**SQLite:**
```bash
curl -fsSL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh -o /tmp/pg.sh \
  && sudo bash /tmp/pg.sh install
```

**MySQL:**
```bash
curl -fsSL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh -o /tmp/pg.sh \
  && sudo bash /tmp/pg.sh install --database mysql
```

**MariaDB:**
```bash
curl -fsSL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh -o /tmp/pg.sh \
  && sudo bash /tmp/pg.sh install --database mariadb
```

**PostgreSQL:**
```bash
curl -fsSL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh -o /tmp/pg.sh \
  && sudo bash /tmp/pg.sh install --database postgresql
```

### 📋 پس از نصب:

<div align="right">

**📋 لاگ‌ها را مشاهده کنید** (برای توقف `Ctrl+C` را فشار دهید)

**📁 فایل‌ها در مسیر** `/opt/pasarguard` قرار دارند

**⚙️ فایل پیکربندی:** `/opt/pasarguard/.env` (برای جزئیات [پیکربندی](#-پیکربندی) را ببینید)

**💾 فایل‌های داده:** `/var/lib/pasarguard`

**🔒 مهم:** داشبورد برای امنیت نیاز به گواهی SSL دارد
- دریافت گواهی SSL: [راهنما](https://PasarGuard.github.io/PasarGuard/fa/examples/issue-ssl-certificate)
- دسترسی: `https://YOUR_DOMAIN:8000/dashboard/`

**🔗 برای تست بدون دامنه:** از SSH port forwarding استفاده کنید (پایین را ببینید)

</div>

---

```bash
ssh -L 8000:localhost:8000 user@serverip
```

سپس دسترسی: `http://localhost:8000/dashboard/`

> ⚠️ **فقط برای تست** - با بستن ترمینال SSH دسترسی خود را از دست خواهید داد.

### 🔧 مراحل بعدی:

```bash
# ایجاد حساب ادمین
pasarguard cli admins --create <username>

# دریافت راهنما
pasarguard --help
```

---

# 📚 مستندات

<div align="right">

**📖 مستندات رسمی** - راهنماهای کامل در دسترس:

🇺🇸 **[English](https://PasarGuard.github.io/PasarGuard)**

🇮🇷 **[فارسی](https://PasarGuard.github.io/PasarGuard)**

🇷🇺 **[Русский](https://PasarGuard.github.io/PasarGuard)**

</div>

> **مشارکت:** در بهبود مستندات در [GitHub](https://github.com/PasarGuard/PasarGuard.github.io) کمک کنید

---

# 💖 حمایت مالی

<div align="right">

> **حمایت از توسعه پاسارگارد**

اگر پاسارگارد به شما کمک می‌کند، از توسعه آن حمایت کنید:

[![Donate](https://img.shields.io/badge/Donate-Support%20Us-green?style=for-the-badge)](http://donate.pasarguard.org)

**از حمایت شما متشکریم!** 💖

</div>

---

<p align="center">
  Made with ❤️ for Internet freedom
</p>
