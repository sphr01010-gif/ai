# دستیار هوش مصنوعی شخصی تلگرام

بات خصوصی مبتنی بر Python برای گفت‌وگوی فارسی/چندزبانه، جست‌وجوی وب با پیوند منبع، تحلیل تصویر، خلاصه‌سازی سند و یادآوری زمان‌دار. **برای پاسخ‌های هوش مصنوعی فقط از Monica API استفاده می‌کند**؛ polling را برای اتصال به Telegram به کار می‌برد و به دامنه یا webhook نیاز ندارد. دسترسی بات در سطح برنامه به شناسهٔ عددی یک کاربر محدود است.

## امکانات

- گفت‌وگوی متنی با Monica API و نگه‌داری تاریخچهٔ کوتاه در SQLite؛ `/clear` تاریخچه را پاک می‌کند.
- تحلیل عکس با مدلی که بینایی را پشتیبانی کند؛ مدل پیش‌فرض Monica در این پروژه `gemini-3-flash-preview` است.
- جست‌وجوی وب از طریق Tavily و پاسخ‌گویی با Monica؛ پاسخ شامل پیوند منابع است. جست‌وجوی صریح با `/search عبارت` و عبارت‌هایی مانند «جست‌وجو کن: ...» انجام می‌شود. درخواست‌های دارای نشانه‌های اطلاعات روز نیز با چند قاعدهٔ متنی به جست‌وجو هدایت می‌شوند.
- استخراج متن از PDF، DOCX، TXT، MD، CSV، JSON و فایل‌های متنی متداول.
- یادآوری پایدار در SQLite؛ منطقهٔ زمانی پیش‌فرض `Asia/Tehran` است.
- **پیام صوتی فعلاً پردازش نمی‌شود.** مستند Monica Chat API که برای این نسخه بررسی شده، ورودی صوتی را تأیید نمی‌کند؛ بات به‌جای استفاده از ارائه‌دهندهٔ دیگری از کاربر می‌خواهد متن بفرستد.

> Monica API برای فراخوانی API به موجودی مثبت نیاز دارد. هزینهٔ مدل‌ها بر اساس توکن ورودی/خروجی است؛ تعرفهٔ روز و محدودیت اعتبار را در حساب Monica بررسی کنید. برای جست‌وجوی وب، Tavily جداگانه استفاده می‌شود و کلید خودش را لازم دارد. Telegram Bot API نیز طبیعتاً برای دریافت/ارسال پیام استفاده می‌شود.

## فرمان‌ها

- `/start` یا `/help` — راهنما
- `/clear` — پاک‌کردن حافظهٔ گفت‌وگو
- `/search عبارت` — اجرای جست‌وجوی وب و خلاصه‌سازی نتیجه‌ها با Monica
- `/remind 30m تماس با ...` — یادآوری پس از مدت مشخص؛ واحدها `s`، `m`، `h` و `d` هستند.
- `/remind 2026-10-11 14:30 تماس با ...` — یادآوری در زمان محلی ایران با قالب ۲۴ساعته.

## آماده‌سازی حساب‌ها و کلیدها

1. در Telegram با `@BotFather` یک bot بساز و token آن را بگیر.
2. شناسهٔ عددی کاربر تلگرامت را از یک ابزار قابل‌اعتماد مانند `@userinfobot` پیدا کن.
3. در [Monica API Platform](https://platform.monica.im/) حساب بساز. طبق [Quickstart رسمی](https://platform.monica.im/docs/en/quickstart)، برای استفاده از API باید روش پرداخت را متصل و حساب را شارژ کنی؛ موجودی مثبت لازم است.
4. در [داشبورد API Keys](https://platform.monica.im/dashboard/api_keys) یک API key بساز. آن را امن نگه دار و در چت، GitHub یا فایل‌های commit‌شده قرار نده.
5. برای جست‌وجوی وب یک کلید Tavily نیز تهیه کن؛ این کلید با Monica API فرق دارد.

## متغیرهای محیطی

این مقادیر را در Railway → Service → Variables وارد کن:

- `TELEGRAM_BOT_TOKEN` — توکن BotFather.
- `TELEGRAM_ALLOWED_USER_ID` — شناسهٔ عددی شخص مجاز؛ فقط همین حساب پردازش می‌شود.
- `MONICA_API_KEY` — کلید Monica API؛ جایگزین `OPENROUTER_API_KEY` در این نسخه.
- `MONICA_MODEL` — شناسهٔ مدل Monica. پیش‌فرض `gemini-3-flash-preview` انتخاب شده چون در [مستند مدل‌های Google Monica](https://platform.monica.im/docs/en/chat/models/google) ورودی تصویر را پشتیبانی می‌کند. شناسه‌های Monica با نام‌های OpenRouter یکی نیستند؛ از فهرست Monica استفاده کن.
- `TAVILY_API_KEY` — کلید Tavily برای جست‌وجوی وب؛ بدون آن پاسخ‌دهی متنی می‌تواند کار کند اما جست‌وجو غیرفعال است.
- `TIMEZONE` — پیش‌فرض `Asia/Tehran`.
- `BOT_DATA_DIR` — مسیر داده؛ در Railway مقدار `/data` بگذار.

فایل `.env.example` نمونه‌ای از نام متغیرها دارد و هیچ‌کدام از کلیدهای واقعی را شامل نمی‌شود. توکن‌ها را فقط در Railway Variables یا در `.env` محلیِ محافظت‌شده وارد کن.

## استقرار روی Railway از GitHub

1. در Railway یک Project بساز و **Deploy from GitHub Repo** را انتخاب کن؛ مخزن را وصل و شاخهٔ `main` را انتخاب کن.
2. بات یک **worker service** است، نه وب‌سایت؛ دستور اجرا `python bot.py` است. فایل `Procfile` همین worker process را تعریف می‌کند. نیازی به Generate Domain یا بازکردن پورت نیست.
3. در بخش Variables، موارد بالا را وارد کن و تغییرات را بررسی و deploy کن.
4. برای نگه‌داری تاریخچه و یادآوری‌ها پس از redeploy، یک Railway Volume به مسیر `/data` متصل کن و `BOT_DATA_DIR=/data` بگذار. بدون Volume فایل SQLite ممکن است هنگام redeploy از بین برود.
5. پس از Deploy در Logs بررسی کن که پیامی مانند `Telegram bot connected as @...` دیده شود.
6. در Telegram به بات `/start` بفرست و گفت‌وگو، `/search` و یک یادآوری کوتاه را آزمایش کن. برای آزمایش تصویر، مدل انتخاب‌شده باید در Monica vision را پشتیبانی کند.

## اجرای محلی برای توسعه

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# مقادیر واقعی را فقط در .env محلی وارد کنید؛ این فایل در .gitignore است.
python bot.py
```

## حریم خصوصی و امنیت

- پیش از پردازش محتوا، شناسهٔ تلگرامی با `TELEGRAM_ALLOWED_USER_ID` مقایسه می‌شود؛ پیام‌های گروهی نادیده گرفته می‌شوند.
- تاریخچهٔ متنی اخیر و یادآوری‌ها در SQLite ذخیره می‌شوند. `/clear` تاریخچهٔ مکالمه را پاک می‌کند؛ یادآوری‌ها جداگانه باقی می‌مانند.
- متن و تصویرهای ارسالی برای پاسخ هوش مصنوعی به Monica API می‌روند. عبارت‌های جست‌وجو برای بازیابی وب به Tavily فرستاده می‌شوند. سیاست‌های نگه‌داری دادهٔ این سرویس‌ها را بررسی کن.
- برای پاک‌کردن همهٔ داده‌ها، سرویس را متوقف و فایل `assistant.sqlite3` را از Volume حذف کن.
- logها مقدار متغیرهای محرمانه را چاپ نمی‌کنند. اگر کلیدی افشا شد، آن را فوراً در سرویس مربوط لغو و دوباره صادر کن.

## منابع فنی

- [Monica API Quickstart](https://platform.monica.im/docs/en/quickstart)
- [Monica Chat Completion](https://platform.monica.im/docs/en/chat/chat)
- [Monica Google models and vision capabilities](https://platform.monica.im/docs/en/chat/models/google)
- [Monica models and pricing](https://platform.monica.im/docs/en/models-and-pricing)
- [Telegram Bot API: `getUpdates`](https://core.telegram.org/bots/api#getupdates)
- [Railway services](https://docs.railway.com/services)
