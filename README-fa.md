<p align="center">
  <a href="https://github.com/PasarGuard/panel" target="_blank" rel="noopener noreferrer">
    <picture>
      <source media="(prefers-color-scheme: dark)" srcset="https://github.com/PasarGuard/docs/raw/main/logos/PasarGuard-white-logo.png">
      <img width="160" height="160" src="https://github.com/PasarGuard/docs/raw/main/logos/PasarGuard-black-logo.png">
    </picture>
  </a>
</p>

<h1 align="center"/>پاسارگارد</h1>

<p align="center">
     راه حل یکپارچه برای مدیریت پروتکل های مختلف
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
    <img src="https://github.com/PasarGuard/docs/raw/master/screenshots/preview.png" alt="Elk screenshots" width="600" height="auto">
  </a>
</p>

## فهرست مطالب

- [بررسی اجمالی](#بررسی-اجمالی)
  - [چرا پاسارگارد؟](#چرا-پاسارگارد)
    - [امکانات](#امکانات)
- [راهنمای نصب](#راهنمای-نصب)
- [تنظیمات](#تنظیمات)
- [داکیومنت](#داکیومنت)
- [استفاده از API](#استفاده-از-api)
- [پشتیبان گیری از پاسارگارد](#پشتیبان-گیری-از-پاسارگارد)
- [ربات تلگرام](#ربات-تلگرام)
- [رابط خط فرمان (CLI) پاسارگارد](#رابط-خط-فرمان-cli-پاسارگارد)
- [نود](#نود)
- [ارسال اعلان‌ها به آدرس وبهوک](#ارسال-اعلانها-به-آدرس-وبهوک)
- [کمک مالی](#کمک-مالی)
- [لایسنس](#لایسنس)
- [مشارکت در توسعه](#مشارکت-در-توسعه)

# بررسی اجمالی

پاسارگارد یک نرم افزار (وب اپلیکیشن) مدیریت پروکسی است که امکان مدیریت چند صد حساب پروکسی را با قدرت و دسترسی بالا فراهم میکند. پاسارگارد از [Xray-core](https://github.com/XTLS/Xray-core) قدرت گرفته و با Python و React پیاده سازی شده است.

## چرا پاسارگارد؟

پاسارگارد دارای یک رابط کاربری ساده است که قابلیت های زیادی دارد. پاسارگارد امکان ایجاد چند نوع پروکسی برای کاربر ها را فراهم میکند بدون اینکه به تنظیمات پیچیده ای نیاز داشته باشید. به کمک رابط کاربری تحت وب پاسارگارد، شما میتوانید کاربران را مانیتور، ویرایش و در صورت نیاز، محدود کنید.

### امکانات

- **رابط کاربری تحت وب** آماده
- به صورت **REST API** پیاده سازی شده
- پشتیبانی از پروتکل های **Vmess**, **VLESS**, **Trojan** و **Shadowsocks**
- امکان فعالسازی **چندین پروتکل** برای هر یوزر
- امکان ساخت **چندین کاربر** بر روی یک inbound
- پشتیبانی از **چندین inbound** بر روی **یک port** (به کمک fallbacks)
- محدودیت بر اساس مصرف **ترافیک** و **تاریخ انقضا**
- محدودیت **ترافیک دوره ای** (به عنوان مثال روزانه، هفتگی و غیره)
- پشتیبانی از **Subscription link** سازگار با **V2ray** _(مثل نرم افزار های V2RayNG, SingBox, Nekoray و...)_ و **Clash**
- ساخت **لینک اشتراک گذاری** و **QRcode** به صورت خودکار
- مانیتورینگ منابع سرور و **مصرف ترافیک**
- پشتیبانی از تنظیمات xray
- پشتیبانی از **TLS**
- **ربات تلگرام**
- **رابط خط فرمان (CLI)** داخلی
- قابلیت ایجاد **چندین مدیر** (تکمیل نشده است)

# راهنمای نصب

### ⚠️ دستورات زیر نسخه های پیش از انتشار (آلفا/بتا) را نصب می کنند

با دستور زیر پاسارگارد را با دیتابیس SQLite نصب کنید:

```bash
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --pre-release
```

با دستور زیر پاسارگارد را با دیتابیس MySQL نصب کنید:

```bash
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --database mysql --pre-release
```

با دستور زیر پاسارگارد را با دیتابیس MariaDB نصب کنید:

```bash
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --database mariadb --pre-release
```

با دستور زیر پاسارگارد را با دیتابیس PostgreSQL نصب کنید:

```bash
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install --database postgresql --pre-release
```

وقتی نصب تمام شد:

- شما لاگ های پاسارگارد رو مشاهده میکنید که می‌توانید با بستن ترمینال یا فشار دادن `Ctrl+C` از آن خارج شوید
- فایل های پاسارگارد در پوشه `/opt/pasarguard` قرار می‌گیرند
- فایل تنظیمات در مسیر `/opt/pasarguard/.env` قرار می‌گیرد ([تنظیمات](#تنظیمات) را مشاهده کنید)
- فایل های مهم (اطلاعات) پاسارگارد در مسیر `/var/lib/pasarguard` قرار می‌گیرند
  به دلایل امنیتی، داشبورد پاسارگارد از طریق آیپی قابل دسترسی نیست. بنابراین، باید برای دامنه خود [گواهی SSL](https://pasarguard.github.io/PasarGuard/fa/examples/issue-ssl-certificate) بگیرید و از طریق آدرس https://YOUR_DOMAIN:8000/dashboard/ وارد داشبورد پاسارگارد شوید (نام دامنه خود را جایگزین YOUR_DOMAIN کنید)
- همچنین می‌توانید از فوروارد کردن پورت SSH برای دسترسی لوکال به داشبورد پاسارگارد بدون دامنه استفاده کنید. نام کاربری و آیپی سرور خود را جایگزین `user@serverip` کنید و دستور زیر را اجرا کنید:

```bash
ssh -L 8000:localhost:8000 user@serverip
```

در نهایت، می‌توانید لینک زیر را در مرورگر خود وارد کنید تا به داشبورد پاسارگارد دسترسی پیدا کنید:

http://localhost:8000/dashboard/

به محض بستن ترمینال SSH، دسترسی شما به داشبورد قطع خواهد شد. بنابراین، این روش تنها برای تست کردن توصیه می‌شود.

در مرحله بعد, باید یک ادمین سودو بسازید

```bash
pasarguard cli admin create --sudo
```

تمام! حالا با این اطلاعات می‌توانید وارد پاسارگارد شوید

برای مشاهده راهنمای اسکریپت پاسارگارد دستور زیر را اجرا کنید

```bash
pasarguard --help
```

اگر مشتاق هستید که پاسارگارد رو با پایتون و به صورت دستی اجرا کنید، مراحل زیر را مشاهده کنید

<details markdown="1">
<summary><h3>نصب به صورت دستی (پیچیده)</h3></summary>

لطفا xray را نصب کنید.
شما میتواند به کمک [Xray-install](https://github.com/XTLS/Xray-install) این کار را انجام دهید.

```bash
bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install
```

پروژه را clone کنید و dependency ها را نصب کنید. دقت کنید که نسخه پایتون شما Python>=3.12.7 باشد.

```bash
git clone https://github.com/PasarGuard/panel.git
cd PasarGuard
curl -LsSf https://astral.sh/uv/install.sh | sh
uv sync
```

همچنین میتواند از [Python Virtualenv](https://pypi.org/project/virtualenv/) هم استفاده کنید.

سپس کامند زیر را اجرا کنید تا دیتابیس تنظیم شود.

```bash
uv run alembic upgrade head
```

اگر می خواهید از `PasarGuard-cli` استفاده کنید، باید آن را به یک فایل در `$PATH` خود لینک و قابل اجرا (executable) کنید. سپس تکمیل خودکار (auto-completion) آن را نصب کنید:

```bash
sudo ln -s $(pwd)/PasarGuard-cli.py /usr/bin/pasarguard-cli
sudo chmod +x /usr/bin/pasarguard-cli
pasarguard-cli completion install
```

حالا یک کپی از `.env.example` با نام `.env` بسازید و با یک ادیتور آن را باز کنید و تنظیمات دلخواه خود را انجام دهید. یه عنوان مثال نام کاربری و رمز عبور را می توانید در این فایل تغییر دهید.

```bash
cp .env.example .env
nano .env
```

> برای اطلاعات بیشتر بخش [تنظیمات](#تنظیمات) را مطالعه کنید.

در انتها, پاسارگارد را به کمک دستور زیر اجرا کنید.

```bash
uv run main.py
```

اجرا با استفاده از systemctl در لینوکس

```
systemctl enable /var/lib/pasarguard/PasarGuard.service
systemctl start PasarGuard
```

اجرا با nginx

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

به صورت پیشفرض پاسارگارد در آدرس `http://localhost:8000/dashboard` اجرا میشود. شما میتوانید با تغییر `UVICORN_HOST` و `UVICORN_PORT`، هاست و پورت را تغییر دهید.

</details>

# تنظیمات

> متغیر های زیر در فایل ‍`env` یا `.env` استفاده میشوند. شما می توانید با تعریف و تغییر آن ها، تنظیمات پاسارگارد را تغییر دهید.

|                                                                                                                                                  توضیحات |                  متغیر                   |
| -------------------------------------------------------------------------------------------------------------------------------------------------------: | :--------------------------------------: |
|                                                                                                                                       نام کاربری مدیر کل |              SUDO_USERNAME               |
|                                                                                                                                         رمز عبور مدیر کل |              SUDO_PASSWORD               |
|                                           آدرس دیتابیس ([بر اساس مستندات SQLAlchemy](https://docs.sqlalchemy.org/en/20/core/engines.html#database-urls)) |         SQLALCHEMY_DATABASE_URL          |
|                                                                                                                                       (پیشفرض: `10`) |           SQLALCHEMY_POOL_SIZE           |
|                                                                                                                                      (پیشفرض: `30`) |         SQLALCHEMY_MAX_OVERFLOW          |
|                                                                                               آدرس هاستی که پاسارگارد روی آن اجرا میشود (پیشفرض: `0.0.0.0`) |               UVICORN_HOST               |
|                                                                                                       پورتی که پاسارگارد روی آن اجرا میشود (پیشفرض: `8000`) |               UVICORN_PORT               |
|                                                                                                                اجرای پاسارگارد بر روی یک Unix domain socket |               UVICORN_UDS                |
|                                                                                                               آدرس گواهی SSL به جهت ایمن کردن پنل پاسارگارد |           UVICORN_SSL_CERTFILE           |
|                                                                                                                                      آدرس کلید گواهی SSL |           UVICORN_SSL_KEYFILE            |
|                                                          نوع گواهینامه مرجع SSL. از «خصوصی» برای آزمایش CA با امضای خود استفاده کنید (پیش‌فرض: `public`) |           UVICORN_SSL_CA_TYPE            |
|                                                                                                 مسیر فایل json تنظیمات xray (پیشفرض: `xray_config.json`) |                XRAY_JSON                 |
|                                                                                                         مسیر باینری xray (پیشفرض: `/usr/local/bin/xray`) |           XRAY_EXECUTABLE_PATH           |
|                                                                                                    مسیر asset های xray (پیشفرض: `/usr/local/share/xray`) |             XRAY_ASSETS_PATH             |
|                                  پیشوند (یا هاست) آدرس های اشتراکی (زمانی کاربرد دارد که نیاز دارید دامنه subscription link ها با دامنه پنل متفاوت باشد) |       XRAY_SUBSCRIPTION_URL_PREFIX       |
|                                                                                                         تگ inboundای که به عنوان fallback استفاده میشود. |        XRAY_FALLBACKS_INBOUND_TAG        |
|                                                                                 تگ های inbound ای که لازم نیست در کانفیگ های ساخته شده وجود داشته باشند. |        XRAY_EXCLUDE_INBOUND_TAGS         |
|                                                                                                                آدرس محل template های شخصی سازی شده کاربر |        CUSTOM_TEMPLATES_DIRECTORY        |
|                                                                            تمپلیت مورد استفاده برای تولید کانفیگ های Clash (پیشفرض: `clash/default.yml`) |       CLASH_SUBSCRIPTION_TEMPLATE        |
|                                                                                      تمپلیت صفحه اطلاعات اشتراک کاربر (پیشفرض `subscription/index.html`) |        SUBSCRIPTION_PAGE_TEMPLATE        |
|                                                                             تمپلیت مورد استفاده برای تولید کانفیگ های xray (پیشفرض: `xray/default.yml`) |       XRAY_SUBSCRIPTION_TEMPLATE         |
|                                                                          تمپلیت مورد استفاده برای تولید کانفیگ های singbox (پیشفرض: `singbox/default.yml`) |      SINGBOX_SUBSCRIPTION_TEMPLATE       |
|                                                                                                              تمپلیت صفحه اول (پیشفرض: `home/index.html`) |            HOME_PAGE_TEMPLATE            |
|                                                                                        توکن ربات تلگرام (دریافت از [@botfather](https://t.me/botfather)) |            TELEGRAM_API_TOKEN            |
|                                                                           آیدی عددی ادمین در تلگرام (دریافت از [@userinfobot](https://t.me/userinfobot)) |            TELEGRAM_ADMIN_ID             |
|                                                                                                                                اجرای ربات از طریق پروکسی |            TELEGRAM_PROXY_URL            |
|                                                             مدت زمان انقضا توکن دسترسی به پنل پاسارگارد, `0` به معنای بدون تاریخ انقضا است (پیشفرض: `1440`) |     JWT_ACCESS_TOKEN_EXPIRE_MINUTES      |
|                                                                                        فعال سازی داکیومنتیشن به آدرس `/docs` و `/redoc`(پیشفرض: `False`) |                   DOCS                   |
|                                                                                                      فعالسازی حالت توسعه (development) (پیشفرض: `False`) |                  DEBUG                   |
|                                  آدرس webhook که تغییرات حالت یک کاربر به آن ارسال می‌شوند. اگر این متغیر مقدار داشته باشد، ارسال پیام‌ها انجام می‌شوند. |             WEBHOOK_ADDRESS              |
|                                                                           متغیری که به عنوان `x-webhook-secret` در header ارسال می‌شود. (پیشفرض: `None`) |              WEBHOOK_SECRET              |
|                                                              تعداد دفعاتی که برای ارسال یک پیام، در صورت تشخیص خطا در ارسال تلاش دوباره شود (پیشفرض `3`) |    NUMBER_OF_RECURRENT_NOTIFICATIONS     |
|                                                                    مدت زمان بین هر ارسال دوباره پیام در صورت تشخیص خطا در ارسال به ثانیه (پیشفرض: `180`) |     RECURRENT_NOTIFICATIONS_TIMEOUT      |
|                                                                     هنگام رسیدن مصرف کاربر به چه درصدی پیام اخطار به آدرس وبهوک ارسال شود (پیشفرض: `80`) |       NOTIFY_REACHED_USAGE_PERCENT       |
|                                                                           چند روز مانده به انتهای سرویس پیام اخطار به آدرس وبهوک ارسال شود (پیشفرض: `3`) |             NOTIFY_DAYS_LEFT             |
| حذف خودکار کاربران منقضی شده (و بطور اختیاری محدود شده) پس از گذشت این تعداد روز (مقادیر منفی این قابلیت را به طور پیشفرض غیرفعال می کنند. پیشفرض: `-1`) |          USERS_AUTODELETE_DAYS           |
|                                                                                                 تعیین اینکه کاربران محدودشده شامل حذف خودکار بشوند یا نه | USER_AUTODELETE_INCLUDE_LIMITED_ACCOUNTS |
|                                                                                                     شما می توانید مسیر api خود را برای اشتراک تغییر دهید |           XRAY_SUBSCRIPTION_PATH           |
|                                                                        با توجه به حجم بالای داده، این کار فقط برای postgresql و timescaledb در دسترس است |       ENABLE_RECORDING_NODES_STATS       |
|                                                           فعال کردن کانفیگ سفارشی JSON برای همه برنامه‌هایی که از آن پشتیبانی می‌کنند (پیش‌فرض: `False`) |         USE_CUSTOM_JSON_DEFAULT          |
|                                                                                فعال کردن کانفیگ سفارشی JSON فقط برای برنامه‌ی V2rayNG (پیش‌فرض: `False`) |       USE_CUSTOM_JSON_FOR_V2RAYNG        |
|                                                                              فعال کردن کانفیگ سفارشی JSON فقط برای برنامه‌ی Streisand (پیش‌فرض: `False`) |      USE_CUSTOM_JSON_FOR_STREISAND       |
|                                                                                 فعال کردن کانفیگ سفارشی JSON فقط برای برنامه‌ی V2rayN (پیش‌فرض: `False`) |        USE_CUSTOM_JSON_FOR_V2RAYN        |

# داکیومنت

[داکیومنت پاسارگارد](https://pasarguard.github.io/PasarGuard) تمامی آموزش‌های ضروری برای شروع را فراهم می‌کند و در سه زبان فارسی، انگلیسی و روسی در دسترس است. این داکیومنت نیاز به تلاش زیادی دارد تا تمامی جنبه‌های پروژه را به طور کامل پوشش دهد. ما از کمک و همکاری شما برای بهبود آن استقبال و قدردانی می‌کنیم. می‌توانید در این صفحه [گیت‌هاب](https://github.com/Gozargah/pasarguard.github.io) مشارکت کنید.

# استفاده از API

پاسارگارد به توسعه دهندگانAPI REST ارائه می دهد. برای مشاهده اسناد API در قالب Swagger UI یا ReDoc، متغیر `DOCS=True` را در تنظیمات خود ست کنید و در مرورگر به مسیر `/docs` و `/redoc` بروید.

# پشتیبان گیری از پاسارگارد

بهتر است همیشه از فایل های پاسارگارد خود نسخه پشتیبان تهیه کنید تا در صورت خرابی سیستم یا حذف تصادفی اطلاعات از دست نروند. مراحل تهیه نسخه پشتیبان از پاسارگارد به شرح زیر است:

1. به طور پیش فرض، تمام فایل های مهم پاسارگارد در `/var/lib/pasarguard` ذخیره می شوند (در نسخه داکر). کل پوشه `/var/lib/pasarguard` را در یک مکان پشتیبان مورد نظر خود، مانند هارد دیسک خارجی یا فضای ذخیره سازی ابری کپی کنید.
2. علاوه بر این، مطمئن شوید که از فایل env خود که حاوی متغیرهای تنظیمات شما است و همچنین فایل پیکربندی Xray خود نسخه پشتیبان تهیه کنید.

خدمات پشتیبان‌گیری پاسارگارد به طور کارآمد تمام فایل‌های ضروری را فشرده کرده و آن‌ها را به ربات تلگرام مشخص شده شما ارسال می‌کند. این خدمات از پایگاه‌های داده SQLite، MySQL و MariaDB پشتیبانی می‌کند. یکی از ویژگی‌های اصلی آن، خودکار بودن است که به شما اجازه می‌دهد تا پشتیبان‌گیری‌ها را هر ساعت برنامه‌ریزی کنید. محدودیتی در مورد محدودیت‌های آپلود تلگرام برای ربات‌ها وجود ندارد؛ اگر فایل شما بزرگتر از میزان محدودیت تلگرام باشد، به دو یا چند بخش تقسیم شده و ارسال می‌شود. علاوه بر این، شما می‌توانید در هر زمان پشتیبان‌گیری فوری انجام دهید.

نصب آخرین ورژن پاسارگارد کامند:

```bash
sudo bash -c "$(curl -sL https://github.com/PasarGuard/scripts/raw/main/pasarguard.sh)" @ install-script
```

راه‌اندازی سرویس پشتیبان گیری:

```bash
pasarguard backup-service
```

پشتیبان گیری فوری:

```bash
pasarguard backup
```

با انجام این مراحل، می توانید اطمینان حاصل کنید که از تمام فایل ها و داده های پاسارگارد خود یک نسخه پشتیبان تهیه کرده اید. به خاطر داشته باشید که نسخه های پشتیبان خود را به طور مرتب به روز کنید تا آنها را به روز نگه دارید.

# ربات تلگرام

پاسارگارد دارای یک ربات تلگرام داخلی است که می تواند مدیریت سرور، ایجاد و حذف کاربر و ارسال نوتیفیکیشن را انجام دهد. این ربات را می توان با انجام چند مرحله ساده به راحتی فعال کرد

برای فعال کردن ربات تلگرام:

1. در تنظیمات، متغیر`TELEGRAM_API_TOKEN` را به API TOKEN ربات تلگرام خود تنظیم کنید.
2. همینطور، متغیر`TELEGRAM_ADMIN_ID` را به شناسه عددی حساب تلگرام خود تنظیم کنید. شما می‌توانید شناسه خود را از [@userinfobot](https://t.me/userinfobot) دریافت کنید.

# رابط خط فرمان (CLI) پاسارگارد

پاسارگارد دارای یک رابط خط فرمان (CLI) داخلی به نام `PasarGuard-cli` است که به مدیران اجازه می دهد با آن ارتباط مستقیم داشته باشند.

اگر پاسارگارد را با استفاده از اسکریپت نصب آسان نصب کرده اید، می توانید با اجرای دستور زیر به دستورات cli دسترسی پیدا کنید

```bash
pasarguard cli [OPTIONS] COMMAND [ARGS]...
```

برای اطلاعات بیشتر، می توانید [مستندات CLI پاسارگارد](./cli/README.md) را مطالعه کنید.

# رابط کاربری متنی (TUI) پاسارگارد

پاسارگارد همچنین یک رابط کاربری متنی (TUI) برای مدیریت تعاملی مستقیم در ترمینال شما فراهم می کند.

اگر پاسارگارد را با استفاده از اسکریپت نصب آسان نصب کرده اید، می توانید با اجرای دستور زیر به TUI دسترسی پیدا کنید:

```bash
pasarguard tui
```

برای اطلاعات بیشتر، می توانید [مستندات TUI پاسارگارد](./tui/README.md) را مطالعه کنید.

# نود

پروژه پاسارگارد [نود](https://github.com/PasarGuard/node) را معرفی می کند که توزیع زیرساخت را متحول می کند. با نود، می توانید زیرساخت خود را در چندین مکان توزیع کنید و از مزایایی مانند افزونگی، در دسترس بودن بالا، مقیاس پذیری و انعطاف پذیری بهره مند شوید. نود به کاربران این امکان را می دهد که به سرورهای مختلف متصل شوند و به آنها انعطاف پذیری انتخاب و اتصال به چندین سرور را به جای محدود شدن به تنها یک سرور ارائه می دهد.
برای اطلاعات دقیق تر و دستورالعمل های نصب، لطفاً به [مستندات رسمی PasarGuard-node](https://github.com/PasarGuard/node) مراجعه کنید.

# ارسال اعلان‌ها به آدرس وبهوک

شما می‌توانید آدرسی را برای پاسارگارد فراهم کنید تا تغییرات کاربران را به صورت اعلان برای شما ارسال کند.

اعلان‌ها به صورت یک درخواست POST به آدرسی که در `WEBHOOK_ADDRESS` فراهم شده به همراه مقدار تعیین شده در `WEBHOOK_SECRET` به عنوان `x-webhook-secret` در header درخواست ارسال می‌شوند.

نمونه‌ای از درخواست ارسال شده توسط پاسارگارد:

```
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

انواع مختلف actionهایی که پاسارگارد ارسال می‌کند: `user_created`, `user_updated`, `user_deleted`, `user_limited`, `user_expired`, `user_disabled`, `user_enabled`

# کمک مالی

اگر پاسارگارد را برای شما مفید بوده و می‌خواهید از توسعه آن حمایت کنید، می‌توانید کمک مالی کنید، [اینجا کلیک کنید](https://donate.gozargah.pro)

از حمایت شما متشکرم!

# لایسنس

توسعه یافته شده در [ناشناس!] و منتشر شده تحت لایسنس [AGPL-3.0](./LICENSE).

# مشارکت در توسعه

این ❤️‍🔥 تقدیم به همه‌ی کسایی که در توسعه پاسارگارد مشارکت می‌کنند! اگر می‌خواهید مشارکت داشته باشید، لطفاً [دستورالعمل‌های مشارکت](CONTRIBUTING.md) ما را بررسی کنید و در صورت تمایل Pull Request ارسال کنید یا یک Issue باز کنید. همچنین از شما برای پیوستن به گروه [تلگرام](https://t.me/Pasar_Guard) ما برای حمایت یا کمک به راهنمایی استقبال می کنیم.

لطفا اگر امکانش رو دارید، با بررسی [لیست کار ها](https://github.com/PasarGuard/panel/issues) به ما در بهبود پاسارگارد کمک کنید. کمک های شما با آغوش باز پذیرفته میشه.

<p align="center">
با تشکر از همه همکارانی که به بهبود پاسارگارد کمک کردند:
</p>
<p align="center">
<a href="https://github.com/PasarGuard/panel/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=PasarGuard/panel" />
</a>
</p>
<p align="center">
  ساخته شده با <a rel="noopener noreferrer" target="_blank" href="https://contrib.rocks">contrib.rocks</a>
</p>
