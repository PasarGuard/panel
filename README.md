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
    Unified GUI Censorship Resistant Solution
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

## 📋 Table of Contents

-   [📖 Overview](#-overview)
    -   [🤔 Why using PasarGuard?](#-why-using-pasarguard)
        -   [✨ Features](#-features)
-   [🚀 Installation guide](#-installation-guide)
-   [⚙️ Configuration](#-configuration)
-   [📚 Documentation](#-documentation)
-   [💖 Donation](#-donation)
-   [📄 License](#-license)
-   [🌟 Contributors](#-contributors)

# 📖 Overview

PasarGuard is a proxy management tool that provides a simple and easy-to-use user interface for managing hundreds of proxy accounts powered by [Xray-core](https://github.com/XTLS/Xray-core) and built using Python and Reactjs.

## 🤔 Why using PasarGuard?

PasarGuard is user-friendly, feature-rich and reliable. It lets you to create different proxies for your users without any complicated configuration. Using its built-in web UI, you are able to monitor, modify and limit users.

### ✨ Features

-   🌐 Built-in **Web UI**
-   🔌 Fully **REST API** backend
-   🌍 [**Multiple Nodes**](#-node) support (for infrastructure distribution & scalability)
-   🔐 Supports protocols **Vmess**, **VLESS**, **Trojan** and **Shadowsocks**
-   🔄 **Multi-protocol** for a single user
-   👥 **Multi-user** on a single inbound
-   🔗 **Multi-inbound** on a **single port** (fallbacks support)
-   📊 **Traffic** and **expiry date** limitations
-   ⏰ **Periodic** traffic limit (e.g. daily, weekly, etc.)
-   🔗 **Subscription link** compatible with **V2ray** _(such as V2RayNG, SingBox, Nekoray, etc.)_, **Clash** and **ClashMeta**
-   🤖 Automated **Share link** and **QRcode** generator
-   📈 System monitoring and **traffic statistics**
-   ⚙️ Customizable xray configuration
-   🔒 **TLS** and **REALITY** support
-   🤖 Integrated **Telegram Bot**
-   💻 Integrated **Command Line Interface (CLI)**
-   🌐 **Multi-language**
-   👨‍💼 **Multi-admin** support (WIP)

# 🚀 Installation guide

### ⚠️ The following commands will install the pre release versions (alpha/beta)

Run the following command to install PasarGuard with SQLite database:

```bash
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --pre-release
```

Run the following command to install PasarGuard with MySQL database:

```bash
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --database mysql --pre-release
```

Run the following command to install PasarGuard with MariaDB database:

```bash
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --database mariadb --pre-release
```

Run the following command to install PasarGuard with PostgreSQL database:

```bash
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --database postgresql --pre-release
```

Once the installation is complete:

-   📋 You will see the logs that you can stop watching them by closing the terminal or pressing `Ctrl+C`
-   📁 The PasarGuard files will be located at `/opt/pasarguard`
-   ⚙️ The configuration file can be found at `/opt/pasarguard/.env` (refer to [configurations](#-configuration) section to see variables)
-   💾 The data files will be placed at `/var/lib/pasarguard`
-   🔒 For security reasons, the PasarGuard dashboard is not accessible via IP address. Therefore, you must [obtain SSL certificate](https://PasarGuard.github.io/PasarGuard/en/examples/issue-ssl-certificate) and access your PasarGuard dashboard by opening a web browser and navigating to `https://YOUR_DOMAIN:8000/dashboard/` (replace YOUR_DOMAIN with your actual domain)
-   🔗 You can also use SSH port forwarding to access the PasarGuard dashboard locally without a domain. Replace `user@serverip` with your actual SSH username and server IP and Run the command below:

```bash
ssh -L 8000:localhost:8000 user@serverip
```

Finally, you can enter the following link in your browser to access your PasarGuard dashboard:

http://localhost:8000/dashboard/

You will lose access to the dashboard as soon as you close the SSH terminal. Therefore, this method is recommended only for testing purposes.

Next, you need to create a sudo admin for logging into the PasarGuard dashboard by the following command

```bash
pasarguard cli admin create --sudo
```

That's it! You can login to your dashboard using these credentials

To see the help message of the PasarGuard script, run the following command

```bash
pasarguard --help
```

If you are eager to run the project using the source code, check the section below

<details markdown="1">
<summary><h3>🏗️ Manual install (advanced)</h3></summary>

Install xray on your machine

You can install it using [Xray-install](https://github.com/XTLS/Xray-install)

```bash
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
```

Clone this project and install the dependencies (you need Python >= 3.12.7)

```bash
git clone https://github.com/PasarGuard/panel.git
cd PasarGuard
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
```

Alternatively, to have an isolated environment you can use [Python Virtualenv](https://pypi.org/project/virtualenv/)

Then run the following command to run the database migration scripts

```bash
uv run alembic upgrade head
```

If you want to use `PasarGuard-cli`, you should link it to a file in your `$PATH`, make it executable, and install the auto-completion:

```bash
sudo ln -s $(pwd)/pasarguard-cli.py /usr/bin/pasarguard-cli
sudo chmod +x /usr/bin/pasarguard-cli
pasarguard-cli completion install
```

Now it's time to configuration

Make a copy of `.env.example` file, take a look and edit it using a text editor like `nano`.

You probably like to modify the admin credentials.

```bash
cp .env.example .env
nano .env
```

> 📖 Check [configurations](#-configuration) section for more information

Eventually, launch the application using command below

```bash
uv run main.py
```

To launch with linux systemctl (copy PasarGuard.service file to `/var/lib/pasarguard/PasarGuard.service`)

```
systemctl enable /var/lib/pasarguard/PasarGuard.service
systemctl start PasarGuard
```

To use with nginx

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

By default the app will be run on `http://localhost:8000/dashboard`. You can configure it using changing the `UVICORN_HOST` and `UVICORN_PORT` environment variables.

</details>

# ⚙️ Configuration

> You can set settings below using environment variables or placing them in `.env` file.



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

The [PasarGuard Documentation](https://PasarGuard.github.io/PasarGuard) provides all the essential guides to get you started, available in three languages: Farsi, English, and Russian. This documentation requires significant effort to cover all aspects of the project comprehensively. We welcome and appreciate your contributions to help us improve it. You can contribute on this [GitHub repository](https://github.com/PasarGuard/PasarGuard.github.io).

# 💖 Donation

If you found PasarGuard useful and would like to support its development, you can make a donation, [Click Here](http://donate.pasarguard.org)

Thank you for your support!

# 📄 License

Made in [Unknown!] and Published under [AGPL-3.0](./LICENSE).

# 🌟 Contributors

We ❤️‍🔥 contributors! If you'd like to contribute, please check out our [Contributing Guidelines](CONTRIBUTING.md) and feel free to submit a pull request or open an issue. We also welcome you to join our [Telegram](https://t.me/Pasar_Guard) group for either support or contributing guidance.

Check [open issues](https://github.com/PasarGuard/panel/issues) to help the progress of this project.

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
