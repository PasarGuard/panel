# تنظیم Trojan، VLESS و VMess

هر سه پروتکل از قبل در مدل کاربر، ویرایشگر inbound/outbound و خروجی subscription پروژه پشتیبانی می‌شوند. این تغییرات، هستهٔ جدید یا تونلِ اجراشده روی حساب شما ایجاد نمی‌کنند. برای فعال‌شدن واقعی، node سازگار با Xray لازم است.

## ساخت تنظیمات یکپارچه

حالت پیشنهادی برای node و پراکسی TLS روی **یک میزبان و یک فضای شبکه**:

```sh
python scripts/generate_xray_config.py --behind-tls-proxy > /tmp/pasarguard-core.json
```

خروجی شامل سه inbound مستقل است:

| پروتکل | آدرس داخلی | مسیر WebSocket |
|---|---|---|
| VLESS | 127.0.0.1:10001 | /pasarguard/vless |
| VMess | 127.0.0.1:10002 | /pasarguard/vmess |
| Trojan | 127.0.0.1:10003 | /pasarguard/trojan |

برای انتخاب زیرمجموعه: `--protocol vless --protocol trojan`. برای تغییر اولین پورت: `--base-port 12001`.

حالت TLS مستقیم، با گواهی معتبر و مسیرهای مطلق:

```sh
python scripts/generate_xray_config.py \
  --listen 0.0.0.0 \
  --cert /etc/pasarguard/certs/fullchain.pem \
  --key /etc/pasarguard/certs/privkey.pem > /tmp/pasarguard-core-tls.json
```

مسیرها باید هنگام اعتبارسنجی/اجرای هسته قابل‌دسترسی باشند. پنل در زمان پردازش تنظیم Xray ممکن است فایل‌های گواهی را بخواند و به certificate داخلی تبدیل کند؛ تنها وجود فایل روی node دوردست کافی نیست. فایل کلید را محرمانه نگه دارید. این مولد گواهی صادر یا تمدید نمی‌کند.

## اتصال تنظیمات به پنل

1. در بخش Cores، هستهٔ Xray ایجاد کنید و JSON تولیدشده را وارد کنید.
2. یک node واقعیِ سازگار اضافه کنید و آن را به این core متصل کنید. خطای اتصال node را بررسی کنید.
3. گروهی با tagهای inbound موردنظر بسازید و کاربر را به آن گروه اختصاص دهید.
4. برای هر inbound، Host با دامنه و پورت **عمومی** تعریف کنید.
5. پشت TLS proxy، مقدار امنیت Host را `tls`، پورت عمومی را 443 و SNI را دامنهٔ گواهی بگذارید؛ امنیت داخلی inbound در این حالت عمداً `none` است. `allowinsecure` را فعال نکنید.
6. آدرس loopback و پورت داخلی 10001..10003 را به‌عنوان آدرس عمومی subscription منتشر نکنید.
7. لینک‌های کاربر را در کلاینت سازگار تست کنید؛ وجود لینک یا HTTP 200، موفقیت عبور ترافیک را ثابت نمی‌کند.

لیست `clients` عمداً خالی است؛ پنل باید UUID/رمز مستقل کاربران را مدیریت کند. UUID یا رمز عمومی مشترک در template قرار داده نشده است. قواعد خروجی literal، شبکه‌های محلی و link-local را محدود می‌کنند؛ این جای firewall، DNS policy و کنترل دسترسی میزبان را نمی‌گیرد.

## نمونهٔ reverse proxy برای node

نمونهٔ زیر در `server` دارای TLS معتبر Nginx قرار می‌گیرد؛ خودش فایل کامل Nginx یا تنظیم پراکسی پنل نیست:

```nginx
location /pasarguard/vless {
    proxy_pass http://127.0.0.1:10001;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 300s;
}
location /pasarguard/vmess {
    proxy_pass http://127.0.0.1:10002;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 300s;
}
location /pasarguard/trojan {
    proxy_pass http://127.0.0.1:10003;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_read_timeout 300s;
}
```

پراکسی managed Railway خودبه‌خود این سه مسیر را به سه پورت داخل برنامه هدایت نمی‌کند. پنل FastAPI تونل WebSocket Xray نیست. قرار دادن پنل روی Railway و node روی میزبان مستقلِ مجاز، معماری قابل‌بررسی است؛ عبور ترافیک روی حساب رایگان هر ارائه‌دهنده باید جداگانه مجاز و قابل‌پشتیبانی باشد.

## شواهد اعتبارسنجی

تست‌ها، حضور هر سه پروتکل، tag/پورت/مسیر مستقل، محدودیت TLS، حفظ credential و مسیر WebSocket در لینک، IPv6، جلوگیری از render تکراری و parser داخلی پنل را بررسی می‌کنند. آزمون native با باینری Xray و اتصال شبکهٔ خارجی هنوز انجام نشده است.


## preset از داخل رابط تنظیمات

در فرم **افزودن/ویرایش Core → نوع Xray** روی **Trojan / VLESS / VMess — WS + TLS proxy** بزنید. هشدار جایگزینی JSON و شرط TLS proxy را بخوانید و تنها پس از تنظیم پراکسی در همان فضای شبکه تأیید کنید. preset شامل هر سه پروتکل است و تنظیمات پیشین را فقط در فرم، پس از تأیید، جایگزین می‌کند؛ ذخیرهٔ Core همچنان با دکمهٔ ذخیرهٔ فرم است.

برای حالت TLS مستقیم از CLI همین سند با certificate/key واقعی استفاده کنید. preset رابط عمداً plaintext را فقط روی loopback باز می‌کند و دامنه یا گواهی جعلی قرار نمی‌دهد. پس از ذخیره، تنظیم node، group، user و Host عمومی TLS طبق مراحل بالا الزامی است. این preset با خروجی CLI در تست Bun مقایسه می‌شود؛ اما اتصال کلاینت خارجی و عبور ترافیک Trojan/VLESS/VMess هنوز در این محیط تأیید نشده است.
