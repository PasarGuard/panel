# نصب Railway با حداقل تنظیم دستی

این پروفایل برای **پنل وب، یک replica، یک worker، SQLite روی volume** است؛ node و عبور ترافیک Trojan/VLESS/VMess را روی Railway ایجاد نمی‌کند. اجرای رایگان دائمی، صفرشدن هزینه، uptime نامحدود یا ظرفیت تضمین‌شده وعده داده نمی‌شود.

## مرز واقعی اتوماسیون

واردکردن URL یک Git repository به Railway فقط سورس را در اختیار سرویس قرار می‌دهد. `railway.toml` مجوز ساخت volume، انتخاب پلن، ثبت دامنه یا تغییر حساب کاربری را ندارد. این پروژه هیچ API token مخفی، دسترسی به حساب شما یا قالب با شناسهٔ جعلی ندارد.

پس از اتصال volume، کارهای زیر خودکار است:

- ساخت frontend و محیط Python 3.14 از سورس با lockfile؛ بدون نیاز به artifact خارجی CI؛
- تشخیص محیط Railway، تنظیم HOST/PORT، نقش all-in-one و یک worker؛
- DEBUG و TESTING خاموش، NATS خاموش، HTTP داخلی پشت HTTPS پلتفرم؛
- انتخاب `sqlite+aiosqlite:////data/db.sqlite3` و جلوگیری از fallback به دیسک موقت؛
- CORS بر اساس دامنهٔ Railway؛ بدون دامنه، فقط same-origin و بدون wildcard؛
- قفل تک‌نمونه‌ای روی volume، قبل از migration و تا پایان عمر پردازه؛
- اجرای migration و توقف راه‌اندازی در صورت شکست؛
- ساخت Owner اولیه با رمز تصادفی قوی، بدون چاپ رمز در لاگ استقرار؛
- حفظ حساب و رمز موجود در restart/redeploy؛
- healthcheck و مهلت shutdown پنجاه‌ثانیه‌ای در تنظیمات استقرار.

این پروفایل offsite backup، auto-upgrade، صدور گواهی node، اتصال node خارجی یا ارتقای پلن را خودکار نمی‌کند. پشتیبانی چند replica، HA و PostgreSQL جزو این preset نیست.

## مسیر پیشنهادی: ساخت خودکار زیرساخت با IaC رسمی

**به‌روزرسانی مهم ۲۲ اکتبر ۲۰۲۶:** اسناد فعلی Railway، Config as Code قدیمی (`railway.toml`/`railway.json`) را deprecated اعلام می‌کنند؛ برای سرویس‌های جدید باید از Infrastructure as Code یا تنظیمات حساب استفاده کرد. IaC با CLI و پس از تأیید مدیر حساب اعمال می‌شود، نه صرفاً با import URL مخزن. فایل `.railway/railway.ts` این پروژه سرویس، volume، mount و تنظیمات استقرار را تعریف می‌کند. [1](https://docs.railway.com/infrastructure-as-code)

پیش‌نیاز محلی: Git، Node.js 22+، npm، Bash (Linux/macOS/WSL) و دسترسی به حساب خودتان. ابتدا اجازهٔ دسترسی Railway به مخزن GitHub را در مرورگر تأیید کنید؛ هیچ رمز یا token را در چت یا کد نگذارید.

```sh
git clone --depth 1 --branch arena/263b0995-panel https://github.com/devv1112/panel.git
cd panel
npm install -g @railway/cli@5.71.0
railway login
railway init
bash scripts/railway-provision.sh
```

در `railway init` یک **پروژهٔ جدید و خالی** در workspace/پلن موردنظر خود بسازید. اسکریپت وابستگی‌های SDK رسمی را از lockfile نصب و اعتبارسنجی می‌کند، plan را نشان می‌دهد و برای apply تأیید می‌خواهد. قبل از تأیید، نام پروژه/محیط، ۱ سرویس panel، ۱ volume به نام panel-data و هزینه/سقف حساب را بررسی کنید. هیچ گزینهٔ `--yes` یا تأیید خودکار تغییر مخرب در اسکریپت نیست.

پس از تأیید، این موارد درخواست می‌شوند:

- اتصال همین مخزن و همین شاخه به سرویس `panel`؛
- ساخت volume به اندازهٔ ۵۰۰ مگابایت و mount در `/data`؛
- Dockerfile builder، PORT=8080، یک replica، healthcheck و drain پنجاه‌ثانیه‌ای؛
- خاموش‌کردن خواب خودکار برای نیازهای پس‌زمینهٔ پنل — این کار مصرف اعتبار را متوقف نمی‌کند؛
- ساخت دامنهٔ عمومی با `railway domain --service panel --port 8080`.

تعریف volume در API رسمی: [1](https://docs.railway.com/infrastructure-as-code/reference). ساخت دامنه با CLI: [1](https://docs.railway.com/cli/domain).

SDK روی Node 22 در این محیط type-check و برای production/staging به‌صورت آفلاین render و با validator رسمی بررسی شده است. **ساخت منابع واقعی در حساب Railway اینجا انجام نشده**؛ اجازهٔ حساب، اتصال GitHub، ظرفیت منطقه و وضعیت پلن تنها هنگام plan/apply واقعی معلوم می‌شوند.

فایل IaC از partial ownership استفاده می‌کند تا منابع نامرتبط را مدیریت نکند. بااین‌حال plan را همیشه بخوانید. برای پروژهٔ قبلیِ تحت مدیریت legacy، ابتدا طبق راهنمای رسمی مهاجرت کنید؛ صرفاً این اسکریپت را روی production قبلی اجرا نکنید. تغییر mount، حذف volume یا تغییر اندازهٔ رو به پایین ممکن است مخرب باشد.

اسکریپت برای نصب اولیه و ساخت دامنه است. در دفعات بعد برای تغییرات زیرساخت، `railway config plan` و `railway config apply` را پس از بازبینی اجرا کنید؛ اگر دامنه از قبل وجود دارد، دوباره آن را نسازید.

پس از استقرار، به مرحلهٔ «دریافت امن رمز اولیه» در همین راهنما بروید؛ دیگر لازم نیست volume یا متغیرهای برنامه را دستی بسازید.

## نصب گام‌به‌گام از رابط وب، بدون IaC

این مسیر چند تنظیم دستی دارد؛ واردکردن تنها URL کافی نیست.

### ۱. مخزن و شاخه

در Railway: **New Project → Deploy from GitHub Repo**.

```text
Repository: devv1112/panel
Branch: arena/263b0995-panel
Root directory: /
```

اگر Railway ابتدا main را انتخاب کرد، در **Settings → Source** شاخه را اصلاح کنید. تغییرات این جلسه تا زمان merge در main نیستند. اگر Fork می‌گیرید، وجود همین شاخه را در Fork بررسی کنید.

### ۲. volume — تنها منبع لازم برای این preset

یک volume به **سرویس پنل** متصل کنید؛ mount path دقیقاً:

```text
/data
```

مستندات رسمی اتصال volume: [1](https://docs.railway.com/volumes).

شروع خودکار Build پیش از اتصال volume طبیعی است؛ برنامه تا فراهم‌شدن mount واقعی، با پیام روشن متوقف می‌شود. پس از اتصال، Redeploy کنید. پوشهٔ خالی `/data` جای volume را نمی‌گیرد. volume داده را بین تعویض کانتینر نگه می‌دارد، نه در برابر حذف پروژه/volume یا پایان شرایط نگهداری حساب.

### ۳. تنظیمات سرویس

برای سرویس جدید این گزینه‌ها را در UI تنظیم کنید؛ به `railway.toml` legacy تکیه نکنید. در مسیر IaC بالا، همین گزینه‌ها از `.railway/railway.ts` اعمال می‌شوند:

```text
Builder: Dockerfile
Dockerfile path: Dockerfile
Custom build command: خالی
Custom start command: خالی
Replicas: 1
Healthcheck: /health
Healthcheck timeout: 120 seconds
Draining time: 50 seconds
```

مستندات جایگزین فعلی: [1](https://docs.railway.com/infrastructure-as-code).

برای نصب معمولی این preset **هیچ فایل .env، رمز ثابت، متغیر SUDO، سرویس NATS یا دیتابیس جداگانه لازم نیست**. اگر قبلاً متغیرهای دستی ناسازگار گذاشته‌اید، آن‌ها را حذف کنید؛ برنامه به‌جای نادیده‌گرفتن بی‌صدای تعارض، متوقف می‌شود.

PORT را Railway تعیین می‌کند؛ در نبود آن مقدار پیش‌فرض 8080 است. UVICORN_PORT جداگانه نگذارید. DATABASE_URL به‌تنهایی تنظیم دیتابیس این برنامه نیست.

### ۴. دامنه

در **Settings → Networking → Public Networking → Generate Domain** دامنه بسازید. Target port باید همان PORT برنامه در لاگ باشد، معمولاً 8080. دسترسی مرورگر باید HTTPS باشد. پس از تغییر/افزودن دامنه، Redeploy کنید تا متغیر دامنه در پردازهٔ جدید اعمال شود.

```text
https://YOUR-PANEL.up.railway.app/health
https://YOUR-PANEL.up.railway.app/dashboard/
```

تولید دامنه و TLS عمومی وظیفهٔ Railway است، نه برنامه: [1](https://docs.railway.com/networking/public-networking).

### ۵. دریافت امن رمز اولیه

Owner خودکار ساخته می‌شود. برای جلوگیری از افشای رمز در لاگ، رمز فقط در این فایل خصوصی قرار می‌گیرد:

```text
/data/.pasarguard/initial-owner.json
```

پوشه mode 0700 و فایل mode 0600 دارد؛ هیچ endpoint وب برای دریافت آن وجود ندارد. فایل به‌صورت کامل و اتمیک پیش از commit حساب منتشر می‌شود تا restart بین این دو مرحله، رمز متفاوت نسازد.

روی کامپیوتر مورد اعتماد دارای Node/npm و SSH:

```sh
npm install -g @railway/cli
railway login
railway link
railway ssh -- cat /data/.pasarguard/initial-owner.json
```

پروژه، سرویس و محیط درست را انتخاب کنید. CLI در صورت نیاز ثبت کلید SSH را راهنمایی می‌کند. این دستور را فقط در ترمینال خصوصی اجرا کنید؛ خروجی را در چت، issue یا screenshot عمومی نگذارید. این **دریافت آگاهانهٔ رمز توسط مدیر حساب** است، نه چاپ خودکار در deployment logs. [2](https://docs.railway.com/cli/ssh)

با username/password همان JSON در داشبورد وارد شوید؛ در این preset دیگر ساخت Owner با کلید موقت لازم نیست. نام کاربری اولیه `owner` است. رمز حدود ۵۰ کاراکتر و شامل ۳۲ بایت تصادفی رمزنگارانه است؛ رمز مشترک یا hardcoded نداریم.

**بلافاصله رمز را تغییر دهید و در password manager نگه دارید. سپس فایل plaintext اولیه را پاک کنید:**

```sh
railway ssh -- rm /data/.pasarguard/initial-owner.json
```

بعد از وجود Owner، فایل پاک‌شده دوباره ساخته نمی‌شود و restart رمز را reset نمی‌کند. حذف فایل به‌تنهایی باعث تغییر رمز نمی‌شود؛ ابتدا رمز را تغییر دهید.

در دیتابیس قبلیِ دارای Owner، حساب موجود حفظ می‌شود و ممکن است این فایل اصلاً وجود نداشته باشد؛ همان حساب قبلی را استفاده کنید. اگر یک حساب غیرOwner با نام owner از قبل وجود داشته باشد، bootstrap به‌جای تصاحب آن شکست می‌خورد؛ با CLI مدیریت موجود، وضعیت حساب را صریحاً اصلاح کنید.

## بازیابی رمز فراموش‌شده

به‌جای حذف دیتابیس یا DEBUG=true، در shell همان سرویس اجرا کنید:

```sh
railway ssh
cd /code
python pasarguard-cli.py generate-temp-key
```

سپس در `/dashboard/` به **Owner access → Reset** بروید و کلید پنج‌دقیقه‌ای را استفاده کنید. تنظیمات خودکار در پردازه‌های CLI/SSH نیز اعمال می‌شوند تا CLI اشتباهاً دیتابیس محلی دیگری نسازد.

## بکاپ خارج از سرویس

volume بکاپ نیست. در shell کانتینر:

```sh
python - <<'PY'
import sqlite3
from contextlib import closing
with closing(sqlite3.connect('/data/db.sqlite3')) as source:
    with closing(sqlite3.connect('/data/db.backup.sqlite3')) as target:
        source.backup(target)
print('Snapshot created; download it privately')
PY
```

از shell خارج شوید و روی کامپیوتر خودتان دانلود کنید:

```sh
scp YOUR-PANEL.up.railway.app@ssh.railway.com:/data/db.backup.sqlite3 ./panel-backup.sqlite3
```

پشتیبانی SCP/SFTP: [2](https://docs.railway.com/cli/ssh). فایل را محرمانه نگه دارید؛ بکاپ دارای اطلاعات حساس است. برای بکاپ خودکار خارج از سرویس، یک مقصد و سیاست نگهداری مستقل باید فراهم شود؛ این preset بدون مجوز، اطلاعات شما را به سرویس دیگری نمی‌فرستد. restore باید در سرویس متوقف، پس از نگهداری نسخهٔ قبلی و قبل از migration انجام شود؛ صحت restore را در محیط جداگانه امتحان کنید.

## محدودیت Free و منابع

طبق اسناد رسمی فعلی، trial اعتبار ۵ دلار/تا ۳۰ روز و Free اعتبار ۱ دلار ماهانه دارد. Free سقف ۰٫۵ گیگابایت RAM و ۰٫۵ گیگابایت volume دارد. هیچ تضمینی نیست که بار شما تمام ماه در این اعتبار یا حافظه جا شود. مصرف CPU/RAM/egress/storage را در حساب خود بررسی کنید. [1](https://docs.railway.com/pricing/free-trial) [6](https://docs.railway.com/pricing/plans)

قفل برنامه مانع دو پردازهٔ هم‌زمان روی همین volume می‌شود، اما جای سیاست استقرار تک‌replica را نمی‌گیرد. برای این نصب ادعای zero-downtime نداریم؛ Railway نیز برای سرویس‌های دارای volume، downtime کوتاه هنگام redeploy را اعلام کرده است. [1](https://docs.railway.com/volumes/reference) `/health` فقط پاسخ‌گویی HTTP است، نه تأیید عبور ترافیک، سلامت node یا همهٔ وابستگی‌ها.

## تنظیمات پیشرفته و خروج صریح از preset

برای معماری سفارشی، PostgreSQL، NATS، نقش جدا یا تنظیمات دیگر ابتدا این متغیر را **دقیقاً** تنظیم کنید:

```dotenv
PASARGUARD_RAILWAY_AUTO_CONFIG=false
```

در این حالت این preset و bootstrap خودکار غیرفعال می‌شوند؛ تأمین همهٔ تنظیمات، ساخت Owner و ماندگاری دیتابیس بر عهدهٔ شماست. راهنمای دستی در [DEPLOYMENT-fa.md](DEPLOYMENT-fa.md) است. متغیر داخلی `PASARGUARD_RAILWAY_READY` را خودتان تنظیم نکنید.

## آزمون‌ها و حدود شواهد

```sh
python -m unittest discover -s tests/deployment -v
uv run pytest tests/test_railway_bootstrap.py -q
```

CI در `.github/workflows/deployment-checks.yml` ساخت Docker واقعی، boot با volume واقعی، ورود HTTP با Owner ساخته‌شده در production، حفظ credential پس از تعویض کانتینر، منع نمونهٔ دوم روی همان volume و توقف بدون volume را بررسی می‌کند. وضعیت اجرای موفق/ناموفق را از Actions همان commit بخوانید؛ وجود یک workflow به‌تنهایی به معنی موفق‌بودن آن نیست.

این آزمون‌ها شبیه‌سازی محیط Railway روی Docker هستند، نه دسترسی یا استقرار انجام‌شده در حساب Railway شما. plan/apply مربوط به IaC و mountهای واقعی میزبان همچنان باید در اولین deployment حساب خودتان بررسی شوند. فایل railway.toml صرفاً سازگاری legacy است.

## node و پروتکل‌ها

این preset فقط پنل است. برای استفادهٔ واقعی از Trojan/VLESS/VMess، node مستقل روی میزبان مجاز، Core، Group، User و Host عمومی واقعی را تنظیم کنید. دامنهٔ پنل را بدون وجود node به‌عنوان آدرس ترافیک منتشر نکنید. راهنما: [PROTOCOLS-fa.md](PROTOCOLS-fa.md).
