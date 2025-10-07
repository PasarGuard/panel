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
    <strong>统一且抗审查的代理管理解决方案</strong>
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
    <img src="https://github.com/PasarGuard/PasarGuard.github.io/raw/main/public/logos/screenshot.png" alt="PasarGuard 截图" width="600" height="auto">
  </a>
</p>

## 📋 目录

> **快速导航** - 跳转到下面的任何部分

-   [📖 概述](#-概述)
    -   [🤔 为什么要使用 PasarGuard？](#-为什么要使用-pasarguard)
        -   [✨ 功能](#-功能)
-   [🚀 安装指南](#-安装指南)
-   [📚 文档](#-文档)
-   [💖 捐赠](#-捐赠)

---

# 📖 概述

> **什么是 PasarGuard？**

PasarGuard 是一个强大的代理管理工具，为处理数百个代理账户提供直观高效的界面。使用 Python 和 React.js 构建，它结合了性能、可扩展性和易用性，简化大规模代理管理。它由 [Xray-core](https://github.com/XTLS/Xray-core) 提供支持，以实现最大性能。

---

## 🤔 为什么要使用 PasarGuard？

> **简单、强大、可靠**

PasarGuard 是一个用户友好、功能丰富且可靠的代理管理工具。它允许您为用户创建和管理多个代理，无需复杂配置。通过其内置的 Web 界面，您可以轻松监控活动、修改设置和控制用户访问限制——所有这些都来自一个便捷的仪表板。

---

### ✨ 功能

<div align="left">

**🌐 Web 界面和 API**
- 内置 **Web UI** 仪表板
- 完全功能的 **REST API** 后端
- **多节点** 支持用于基础设施分发

**🔐 协议和安全**
- 支持 **Vmess**、**VLESS**、**Trojan** 和 **Shadowsocks**
- **TLS** 和 **REALITY** 支持
- 单个用户的 **多协议**

**👥 用户管理**
- 单个 inbound 上的 **多用户**
- **单个端口** 上的 **多 inbound**（支持 fallbacks）
- **流量** 和 **过期日期** 限制
- **周期性** 流量限制（每日、每周等）

**🔗 订阅和分享**
- 与 **V2ray**、**Clash** 和 **ClashMeta** 兼容的 **订阅链接**
- 自动 **分享链接** 和 **二维码** 生成器
- 系统监控和 **流量统计**

**🛠️ 工具和自定义**
- 可自定义的 xray 配置
- 集成的 **Telegram Bot**
- **命令行界面 (CLI)**
- **多语言** 支持
- **多管理员** 支持（开发中）

</div>

---

# 🚀 安装指南

> **快速开始** - 在几分钟内运行 PasarGuard

### 要快速设置，请根据您首选的数据库使用以下命令。

---

**TimescaleDB（推荐）：**
```bash
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --database timescaledb --pre-release
```

**SQLite：**
```bash
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --pre-release
```

**MySQL：**
```bash
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --database mysql --pre-release
```

**MariaDB：**
```bash
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --database mariadb --pre-release
```

**PostgreSQL：**
```bash
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --database postgresql --pre-release
```

### 📋 安装后：

<div align="left">

**📋 查看日志**（按 `Ctrl+C` 停止）

**📁 文件位于** `/opt/pasarguard`

**⚙️ 配置文件：** `/opt/pasarguard/.env`（有关详细信息，请参阅[配置](#-配置)）

**💾 数据文件：** `/var/lib/pasarguard`

**🔒 重要：** 仪表板需要 SSL 证书以确保安全
- 获取 SSL 证书：[指南](https://PasarGuard.github.io/PasarGuard/zh-cn/examples/issue-ssl-certificate)
- 访问：`https://YOUR_DOMAIN:8000/dashboard/`

**🔗 无域名测试：** 使用 SSH 端口转发（见下文）

</div>

---

```bash
ssh -L 8000:localhost:8000 user@serverip
```

然后访问：`http://localhost:8000/dashboard/`

> ⚠️ **仅用于测试** - 关闭 SSH 终端时您将失去访问权限。

### 🔧 下一步：

```bash
# 创建管理员账户
pasarguard cli admin create --sudo

# 获取帮助
pasarguard --help
```

---

# 📚 文档

<div align="left">

**📖 官方文档** - 完整指南可在以下位置获得：

🇺🇸 **[English](https://PasarGuard.github.io/PasarGuard)**

🇮🇷 **[فارسی](https://PasarGuard.github.io/PasarGuard)**

🇷🇺 **[Русский](https://PasarGuard.github.io/PasarGuard)**

</div>

> **贡献：** 在 [GitHub](https://github.com/PasarGuard/PasarGuard.github.io) 上帮助改进文档

---

# 💖 捐赠

<div align="left">

> **支持 PasarGuard 开发**

如果 PasarGuard 对您有帮助，请考虑支持其开发：

[![Donate](https://img.shields.io/badge/Donate-Support%20Us-green?style=for-the-badge)](http://donate.pasarguard.org)

**感谢您的支持！** 💖

</div>

---

<p align="center">
  Made with ❤️ for Internet freedom
</p>
