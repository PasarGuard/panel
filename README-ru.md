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
    <strong>Унифицированное решение для управления прокси, устойчивое к цензуре</strong>
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
    <img src="https://github.com/PasarGuard/PasarGuard.github.io/raw/main/public/logos/screenshot.png" alt="PasarGuard скриншоты" width="600" height="auto">
  </a>
</p>

## 📋 Содержание

> **Быстрая навигация** - Перейдите к любому разделу ниже

-   [📖 Обзор](#-обзор)
    -   [🤔 Зачем использовать PasarGuard?](#-зачем-использовать-pasarguard)
        -   [✨ Функции](#-функции)
-   [🚀 Руководство по установке](#-руководство-по-установке)
-   [📚 Документация](#-документация)
-   [💖 Пожертвования](#-пожертвования)

---

# 📖 Обзор

> **Что такое PasarGuard?**

PasarGuard — это мощный инструмент управления прокси-серверами, который предлагает интуитивно понятный и эффективный интерфейс для работы с сотнями прокси-аккаунтов. Построенный на Python и React.js, он сочетает производительность, масштабируемость и простоту использования для упрощения управления прокси в больших масштабах. Он поддерживает и [Xray-core](https://github.com/XTLS/Xray-core), и [WireGuard](https://www.wireguard.com/) для максимальной производительности.

---

## 🤔 Зачем использовать PasarGuard?

> **Простой, Мощный, Надежный**

PasarGuard — это удобный, многофункциональный и надежный инструмент управления прокси-серверами. Он позволяет создавать и управлять несколькими прокси для ваших пользователей без необходимости сложной настройки. С помощью встроенного веб-интерфейса вы можете легко отслеживать активность, изменять настройки и контролировать ограничения доступа пользователей — все из одного удобного панели управления.

---

### ✨ Функции

<div align="left">

**🌐 Веб-интерфейс и API**
- Встроенная панель управления **Web UI**
- Полностью функциональный бэкенд **REST API**
- Поддержка **Multi-Node** для распределения инфраструктуры

**🔐 Протоколы и безопасность**
- Поддержка **Vmess**, **VLESS**, **Trojan**, **Shadowsocks**, **WireGuard** и **Hysteria2**
- Поддержка **TLS** и **REALITY**
- **Мультипротокол** для одного пользователя

**👥 Управление пользователями**
- **Мультипользователь** на одном inbound
- **Мультиinbound** на **одном порту** (поддержка fallbacks)
- Ограничения по **трафику** и **сроку действия**
- **Периодические** ограничения трафика (ежедневно, еженедельно и т.д.)

**🔗 Подписки и обмен**
- **Ссылка подписки** совместимая с **V2ray**, **Clash** и **ClashMeta**
- Автоматический генератор **ссылок для обмена** и **QR-кодов**
- Мониторинг системы и **статистика трафика**

**🛠️ Инструменты и настройка**
- Настраиваемая конфигурация xray
- Встроенный **Telegram Bot**
- **Интерфейс командной строки (CLI)**
- Поддержка **многоязычности**
- Поддержка **множественных администраторов** (в разработке)

</div>

---

# 🚀 Руководство по установке

> **Быстрый старт** - Запустите PasarGuard за несколько минут

### Для быстрой настройки используйте следующие команды в зависимости от предпочитаемой базы данных.

---

**TimescaleDB (Рекомендуется):**
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
  && sudo bash /tmp/pg.sh install --database postgresql --pre-release
```

### 📋 После установки:

<div align="left">

**📋 Следите за логами** (нажмите `Ctrl+C` для остановки)

**📁 Файлы находятся в** `/opt/pasarguard`

**⚙️ Файл конфигурации:** `/opt/pasarguard/.env` (см. [Конфигурация](#-конфигурация) для деталей)

**💾 Файлы данных:** `/var/lib/pasarguard`

**🔒 Важно:** Панель управления требует SSL-сертификат для безопасности
- Получить SSL-сертификат: [Руководство](https://PasarGuard.github.io/PasarGuard/ru/examples/issue-ssl-certificate)
- Доступ: `https://YOUR_DOMAIN:8000/dashboard/`

**🔗 Для тестирования без домена:** Используйте SSH port forwarding (см. ниже)

</div>

---

```bash
ssh -L 8000:localhost:8000 user@serverip
```

Затем доступ: `http://localhost:8000/dashboard/`

> ⚠️ **Только для тестирования** - Вы потеряете доступ при закрытии SSH-терминала.

### 🔧 Следующие шаги:

```bash
# Создать учетную запись администратора
pasarguard cli admins --create <username>

# Получить справку
pasarguard --help
```

---

# 📚 Документация

<div align="left">

**📖 Официальная документация** - Полные руководства доступны на:

🇺🇸 **[English](https://PasarGuard.github.io/PasarGuard)**

🇮🇷 **[فارسی](https://PasarGuard.github.io/PasarGuard)**

🇷🇺 **[Русский](https://PasarGuard.github.io/PasarGuard)**

</div>

> **Участие:** Помогите улучшить документацию на [GitHub](https://github.com/PasarGuard/PasarGuard.github.io)

---

# 💖 Пожертвования

<div align="left">

> **Поддержка разработки PasarGuard**

Если PasarGuard помогает вам, рассмотрите возможность поддержки его разработки:

[![Donate](https://img.shields.io/badge/Donate-Support%20Us-green?style=for-the-badge)](http://donate.pasarguard.org)

**Спасибо за вашу поддержку!** 💖

</div>

---

<p align="center">
  Made with ❤️ for Internet freedom
</p>
