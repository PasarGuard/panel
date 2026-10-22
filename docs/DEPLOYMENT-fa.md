# استقرار و محدودیت‌های عملی

این راهنما برای نسخهٔ موجود در همین مخزن است؛ تضمین اجرای رایگان، امنیت مطلق یا خودترمیمی داده‌ها نیست.

## Railway

فایل `railway.toml` ساخت Docker، مسیر سلامت و حداکثر پنج تلاش restart پس از خروج ناموفق را مشخص می‌کند. Dockerfile داشبورد را از سورس می‌سازد و به artifact جداگانهٔ CI وابسته نیست. ساخت frontend می‌تواند حافظهٔ قابل‌توجهی بخواهد؛ محدودیت حساب را بررسی کنید.

متغیرهای سرویس:

```dotenv
ROLE=all-in-one
DEBUG=false
UVICORN_HOST=0.0.0.0
UVICORN_ALLOW_INSECURE_HTTP=true
UVICORN_WORKERS=1
SUDO_USERNAME=choose-a-private-admin-name
SUDO_PASSWORD=replace-with-a-long-random-password
SQLALCHEMY_DATABASE_URL=sqlite+aiosqlite:////data/db.sqlite3
```

- یک volume پایدار روی `/data` متصل کنید. بدون volume، SQLite با تعویض container از دست می‌رود. یک replica استفاده کنید و backup خارج از سرویس نگه دارید؛ بازیابی backup را نیز آزمایش کنید.
- پورت `PORT` پلتفرم خودکار خوانده می‌شود؛ `UVICORN_PORT` اگر تعیین شود مقدم است. معمولاً آن را تعیین نکنید.
- گزینهٔ HTTP فقط پشت پراکسی با TLS معتبر مجاز است. TLS عمومی را پلتفرم فراهم می‌کند؛ این گزینه نباید برای انتشار HTTP بدون رمزنگاری استفاده شود.
- اعتماد به هدرهای پراکسی پیش‌فرض فعال نشده است. اگر به آن نیاز دارید، `UVICORN_PROXY_HEADERS=true` و `UVICORN_FORWARDED_ALLOW_IPS` را مطابق شبکهٔ پراکسی تنظیم کنید. مقدار `*` تنها وقتی قابل‌قبول است که هیچ مسیر دسترسی مستقیم یا غیرقابل‌اعتماد به سرویس وجود نداشته باشد.
- محدودیت CORS را با `ALLOWED_ORIGINS=https://your-domain.example` مشخص کنید.
- برای PostgreSQL، URL مناسب درایور async را در `SQLALCHEMY_DATABASE_URL` بگذارید: `postgresql+asyncpg://USER:PASSWORD@HOST:PORT/DB`. اتصال محرمانه را در مخزن ثبت نکنید. URL عادی پلتفرم لزوماً مستقیم قابل‌استفاده نیست.
- migration قبل از اجرای پنل انجام می‌شود و شکست آن مانع اجرا می‌شود. قبل از ارتقا backup بگیرید. برای چند replica، migration باید جداگانه و سریالی مدیریت شود؛ این راهنما تک‌replica است.

## آزمون پس از استقرار

1. لاگ ساخت frontend و نصب وابستگی‌های Python باید موفق باشد.
2. لاگ migration باید بدون خطا تمام شود.
3. `https://YOUR-DOMAIN/health` باید وضعیت ۲۰۰ بدهد.
4. صفحهٔ `/dashboard/` را باز کنید؛ ورود، ایجاد کاربر و subscription را امتحان کنید.
5. سرویس را restart کنید و باقی‌ماندن داده‌ها را بررسی کنید.
6. اتصال واقعی به node خارجی و عبور ترافیک را جداگانه آزمایش کنید.

`/health` فقط زنده‌بودن پاسخ‌گویی HTTP را نشان می‌دهد؛ سلامت دیتابیس، node، شبکه یا صحت ترافیک را تضمین نمی‌کند. Docker HEALTHCHECK به‌تنهایی container ناسالم را restart نمی‌کند؛ restart زمان اجرا به تنظیمات میزبان بستگی دارد. healthcheck Railway برای آماده‌شدن deployment است و جای پایش مداوم مستقل را نمی‌گیرد.

## ارزیابی میزبان‌های درخواستی — ۲۲ اکتبر ۲۰۲۶

منابع زیر صفحات رسمی مشاهده‌شده در این بررسی هستند؛ شرایط حساب و سیاست استفاده می‌تواند تغییر کند. این جدول گزارش استقرار واقعی نیست.

| میزبان | اطلاعات رسمی مرتبط | نتیجهٔ عملی برای این پروژه |
|---|---|---|
| [Railway](https://railway.com/pricing) | trial سی‌روزه با ۵ دلار اعتبار؛ سپس اعتبار ماهانهٔ محدود. صفحهٔ Free سقف ۰٫۵ گیگابایت RAM و ۰٫۵ گیگابایت volume پس از trial را ذکر می‌کند. | پیکربندی Docker پنل اضافه شده است؛ مصرف، هزینه و ظرفیت باید اندازه‌گیری شود. اعتبار محدود، اجرای رایگان نامحدود نیست. |
| [Katabump](https://katabump.com/en/) | پلن Free با ۳۰۸ مگابایت RAM، ۷۱۶ مگابایت فضای NVMe، ۲۵٪ CPU و تمدید رایگان هر چهار روز. | ظرفیت پایین و نیاز به تمدید با ادعای اجرای تمام‌اتوماتیک دائمی سازگار نیست. وجود Python 3.14، وابستگی‌های باینری، پورت وب و TLS باید در حساب تأیید شود. نصب این پروژه روی آن هنوز تأیید نشده است. |
| [Deepnote](https://deepnote.com/pricing) | ماشین Basic رایگان با ۵ گیگابایت RAM و دو vCPU؛ جدول پلن رایگان دورهٔ عدم فعالیت ۱۵ دقیقه را ذکر می‌کند. | برای تحلیل و آزمایش قابل‌بررسی است؛ از این مشخصات نمی‌توان مناسب‌بودن برای پنل production یا تونل دائمی را نتیجه گرفت. |

پنل وب با سرور عبور ترافیک VPN یکسان نیست. پورت TCP/UDP دلخواه، WebSocket پایدار، volume پایدار، runtime مناسب و مجازبودن proxy/VPN را فرض نکنید. شرایط استفاده را پیش از انتقال ترافیک واقعی بررسی کنید. هیچ ابزار دورزدن محدودیت خواب، تمدید حساب یا محدودیت پلن رایگان اضافه نشده است.

روش کم‌ریسک‌تر، پنل وب روی میزبان پشتیبانی‌شده و node روی سرور مستقلِ مجاز است. راهنمای پروتکل‌ها در [PROTOCOLS-fa.md](PROTOCOLS-fa.md) آمده است.

## تست‌های محلی مستقل

```sh
python -m unittest discover -s tests/deployment -v
bash -n start.sh healthcheck.sh
```

برای مجموعهٔ اصلی، Python 3.14 و وابستگی‌های قفل‌شده لازم است:

```sh
uv sync --frozen --group dev
uv run pytest
```

مجموعهٔ اصلی اکنون با Python 3.14 ساخته‌شده از سورس و وابستگی‌های قفل‌شده اجرا شده است؛ جزئیات نتیجه در AUDIT-fa.md آمده است. برای جلوگیری از اختلاف دیتابیس تست و JWT، هنگام تغییر مسیر تست، `DATABASE_URL` و `SQLALCHEMY_DATABASE_URL` را به یک دیتابیس تست مستقل تنظیم کنید. هرگز آن‌ها را به دیتابیس production وصل نکنید.

داشبورد اکنون پیش از build، بررسی سخت‌گیرانهٔ TypeScript انجام می‌دهد:

```sh
cd dashboard
bun install --frozen-lockfile
bun test
bun run build
```

HEALTHCHECK تصویر برای نقش‌های node/scheduler فقط command پردازهٔ PID 1 را بررسی می‌کند، نه آمادگی NATS یا سلامت node. برای این نقش‌ها پایش اختصاصی لازم است.

## رفتار شروع سرویس و تنظیمات TLS

اسکریپت start از مسیر پروژه اجرا می‌شود. ROLE نامعتبر قبل از migration رد می‌شود و شکست migration با همان exit code گزارش می‌شود. برای .env از parser تنظیمات استفاده می‌شود؛ فایل هرگز به‌عنوان اسکریپت shell اجرا نمی‌شود. healthcheck نیز در صورت وجود .env پورت و تنظیمات TLS/UDS را از همان parser می‌خواند.

تعیین فقط یکی از `UVICORN_SSL_CERTFILE` یا `UVICORN_SSL_KEYFILE` اکنون خطای اعتبارسنجی است؛ دیگر به‌صورت ضمنی به HTTP برنمی‌گردد. در حالت TLS termination میزبان، هر دو را خالی بگذارید و HTTP را صریحاً فعال کنید.


## محدودیت lifecycle و jobهای عقب‌افتاده

ROLE را پیش از شروع پردازه تعیین و در همان پردازه تغییر ندهید. scheduler، صف‌ها و registryهای lifecycle process-global هستند؛ فقط یک lifespan هم‌زمان مجاز است. برای restart کامل، پردازه را با supervisor/container جایگزین کنید؛ بستن و بازکردن مکرر lifespan در همان پردازه، بازیابی کامل jobها را تضمین نمی‌کند.

پیش‌فرض jobها یک اجرای هم‌زمان و coalescing است؛ تنظیم صریح هر job بر این پیش‌فرض مقدم است. `JOB_MISFIRE_GRACE_TIME=60` پنجرهٔ مجاز تأخیر را به ثانیه تعیین می‌کند. مقدار باید مثبت باشد، مانند همهٔ `JOB_*_INTERVAL`ها. اجرای عقب‌افتاده‌تر از این پنجره missed می‌شود؛ افزایش این عدد به‌معنای catch-up همهٔ کارها یا بازیابی دادهٔ ازدست‌رفته نیست. وقفهٔ طولانی میزبان را با پایش jobها، backup و آزمون بازیابی مدیریت کنید، نه با وعدهٔ خودترمیم نامحدود.


## تحویل اعلان‌ها و محدودیت صف

هر اجرای عادی webhook حداکثر ۱۰۰ پیام برداشت و در batchهای حداکثر ۵۰تایی ارسال می‌کند. drain نهایی از سقف تعداد پیام مستثناست، اما اکنون تحت بودجهٔ زمانی lifecycle قرار دارد. با اتمام مهلت، hook لغو، برای finally مهلت کوتاه رزرو و cleanupهای بعدی اجرا می‌شوند. پیام NATS ناتمام ack نمی‌شود و می‌تواند redeliver شود؛ صف حافظه پس از مرگ پردازه بازیابی نمی‌شود.

صف حافظه برای هر یک از دو کانال، پیش‌فرض ۲۵۶ پیام و حداکثر ۶۵۵۳۶ بایت JSON برای هر پیام دارد. پیام claimشده نیز ظرفیت اشغال می‌کند؛ retry از همان جای رزروشده استفاده می‌کند، نه ظرفیت تازه. بنابراین پرشدن صف با producer جدید، retry مصرف‌کننده را پشت صف قفل نمی‌کند. ورودی snapshot می‌شود تا تغییر بعدی شیء توسط caller محدودیت را دور نزند. این سقف، اندازهٔ payload نگهداری‌شده را محدود می‌کند، نه RSS دقیق Python یا حافظهٔ مصرفی caller پیش از enqueue.

producer در حالت پر پس از پیش‌فرض یک ثانیه `QueueOverloadedError` می‌گیرد؛ پیام بی‌صدا حذف نمی‌شود. caller باید retry/reject را مدیریت کند. enqueue پیام بزرگ/غیرقابل‌سریال‌سازی نیز خطا دارد. پس از فاز SEAL، producer جدید رد می‌شود ولی retry/release رزروشده قابل‌اجراست.

```dotenv
MEMORY_NOTIFICATION_QUEUE_CAPACITY=256
MEMORY_NOTIFICATION_QUEUE_ENQUEUE_TIMEOUT=1
MEMORY_NOTIFICATION_QUEUE_MAX_ITEM_BYTES=65536
SHUTDOWN_REQUEST_DRAIN_TIMEOUT=10
SHUTDOWN_TIMEOUT=30
SHUTDOWN_HOOK_TIMEOUT=5
```

این مقادیر باید مثبت و timeoutها finite باشند. مهلت درخواست Uvicorn قبل از بودجهٔ cleanup اجرا می‌شود؛ supervisor/container را بالاتر از مجموع آن‌ها تنظیم کنید. compose نمونه `stop_grace_period: 50s` دارد؛ برای Docker مستقیم از `docker stop --timeout 50 ...` استفاده کنید. اگر بودجه‌ها را افزایش می‌دهید، این grace را نیز افزایش دهید.

ترتیب shutdown: **QUIESCE → PRODUCERS → SEAL_QUEUES → DRAIN → TRANSPORTS**. توقف scheduler/dispatcher/maintenance قبل از coreهای node، سپس drain و در پایان بستن HTTP/NATS/bridge انجام می‌شود. ترتیب درون هر فاز ثابت است. hookهای node پیش از startup ثبت می‌شوند تا شکست نیمه‌کارهٔ startup cleanup را حذف نکند.

بودجهٔ واقعی هر hook حداقلِ سقف hook و سهم باقی‌مانده از بودجهٔ کل است؛ بخش آخر این سهم برای cancellation/finally رزرو می‌شود. hookای که cancellation را نادیده می‌گیرد دیگر lifespan را بی‌نهایت نگه نمی‌دارد، اما ممکن است task آن هنوز زنده باشد؛ بازکردن lifespan جدید تا پایان آن رد می‌شود. Python نمی‌تواند کد sync مسدودکننده یا syscall گیرکرده را با این روش قطع کند؛ hard deadline را supervisor با SIGKILL اعمال می‌کند. timeout، خطای shutdown است، نه موفقیت drain کامل.

پیام‌های webhook ناتمام در خطا/cancellation معمول مجدداً به صف برگردانده می‌شوند، اما این کار تحویل exactly-once نیست: درخواست لغوشده ممکن است در مقصد اجرا شده باشد. مصرف‌کننده‌های production اکنون از claim استفاده می‌کنند: ack پس از پردازش، یا بعد از publish موفق پیام retry انجام می‌شود. heartbeat هر ۱۰ ثانیه است و consumerهای موجود با ack_wait کوتاه‌تر نیاز به بازبینی دارند. crash پیش از settlement، پیام اصلی را برای redelivery باقی می‌گذارد؛ ولی ارسال HTTP نامطمئن می‌تواند تکراری شود. برای اعلان‌های حیاتی هنوز outbox، idempotency مقصد و dead-letter لازم است؛ راهکار فعلی را تضمین تحویل همهٔ پیام‌ها تلقی نکنید. موفقیت فعلی batch نیز به‌معنای پذیرش حداقل یک webhook است، نه تمام مقصدها.


راه‌اندازی صف NATS اکنون در خطای setup اتصال تازه را می‌بندد و خطای عمومی broker را معادل «صف خالی» نمی‌گیرد. اگر ساخت stream با APIError مواجه شود، دسترسی stream موجود بررسی می‌شود؛ این بررسی جای اعتبارسنجی همهٔ سیاست‌های retention/subject را نمی‌گیرد. دادهٔ خام JSON/UTF-8 نامعتبر یا غیر-object با term از retry خارج می‌شود و dead-letter ذخیره نمی‌شود. برای نگهداری و بازیابی دادهٔ خراب، راهکار quarantine جداگانه لازم است. قرارداد claim جایگزین مصرف مخرب در هر سه مسیر production شده است. dequeue قدیمی API سازگاری و مخرب است؛ کد جدید نباید آن را مصرف کند.


### آزمون broker و شبکه

برای اجرای تست‌ها با broker محلی واقعی:

```sh
NATS_SERVER_BINARY=/absolute/path/to/nats-server uv run pytest -q tests/test_nats_sync_integration.py tests/test_notification_delivery.py
```

workflow CI نسخهٔ ۲٫۱۴٫۰ را از release رسمی با checksum archive نصب می‌کند. دو probe خارجی فقط با input دستی `network_probes` اجرا می‌شوند؛ شبکهٔ محدود این sandbox اتصال TLS به مقصدهای آن‌ها را قطع می‌کند. موفقیت TLS محلی به‌معنای موفقیت probe خارجی یا تونل WAN نیست.


### شواهد اجرا در GitHub Actions

نسخهٔ runtime در commit `440459e95ea4e097d30b9a9f09006f09dfec6f32` روی همین شاخه آزموده شد:

- [Deployment checks](https://github.com/devv1112/panel/actions/runs/39709463046): ساخت image از سورس، migration/startup، health و dashboard، healthcheck داخل کانتینر و `docker stop --timeout 50` موفق؛ خروج صفر و لاگ `Application shutdown complete` بررسی شدند.
- job native-node-shutdown در همان run باینری رسمی Node **v0.5.4** و Xray **v26.3.27** را با SHA256 پین‌شده اجرا کرد. core واقعاً شروع و سپس با مسیر shutdown پنل متوقف شد؛ پاسخ API و خروج پردازهٔ فرزند Xray پیش از drain/close آزموده شدند. این node موقت و محلیِ runner بود، نه node production کاربر.
- NATS واقعی و تست deadline/redelivery نیز در همان CI موفق بودند.

این شواهد به سناریوی آزموده‌شده محدود است، نه اثبات failover چند node یا عبور ترافیک WAN. دو probe خارجی قبلی در این run opt-in و skipped بودند؛ اتصال فعلی اجازهٔ workflow_dispatch ندارد، بنابراین اجرای خارجی دستی آن‌ها در این دور ادعا نمی‌شود.


ماتریس دیتابیس هم برای همان commit در [run 39709463062](https://github.com/devv1112/panel/actions/runs/39709463062) با نتیجهٔ موفق کامل شد: SQLite، PostgreSQL، MySQL، MariaDB و TimescaleDB، شامل migration/check/tests. این شواهد جای backup/restore واقعی یا آزمون بار و failover production را نمی‌گیرد.
