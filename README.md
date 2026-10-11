# دستیار هوش مصنوعی شخصی تلگرام

بات خصوصی مبتنی بر Python برای گفت‌وگوی فارسی/چندزبانه و جست‌وجوی وب. اتصال APMIX و Tooken Club (اختیاری) همراه با fallback خودکار پشتیبانی می‌شود؛ Tavily برای جست‌وجوی وب و Telegram Bot API برای انتقال پیام‌ها استفاده می‌شود.

بات با polling اجرا می‌شود و به دامنه یا webhook نیاز ندارد. پردازش پیام‌ها به شناسهٔ عددی یک کاربر و گفت‌وگوی خصوصی محدود است.

## منوی فعلی تلگرام

کیبورد پایین صفحه این گزینه‌ها را دارد:

- **گفت‌وگو:** متن دلخواهت را بفرست.
- **جست‌وجوی وب:** پرسشت را بفرست تا پاسخ همراه منبع بگیری.
- **انتخاب API:** برای چت APMIX، Tooken یا «خودکار» را انتخاب کن. انتخاب برای حساب تلگرامی تو ذخیره می‌شود؛ در حالت انتخاب دستی، بات فقط از همان ارائه‌دهنده استفاده می‌کند و در صورت خطا خودکار به دیگری نمی‌رود.

گزینه‌های قبلی از منوی فعال حذف شده‌اند و حالت‌های نیمه‌تمام آن‌ها پس از دریافت پیام پاک می‌شوند. ارسال‌های زمان‌بندی‌شدهٔ یادآوری و خلاصه غیرفعال‌اند. داده‌های قدیمی داخل SQLite عمداً پاک نشده‌اند.

## ساخت کلید APMIX

1. به [apmix.ai](https://apmix.ai/) برو و از داشبورد **API keys** یک کلید بساز.
2. کلید واقعی را در چت یا مخزن GitHub قرار نده؛ آن را فقط در Railway Variables یا فایل محلی محافظت‌شدهٔ `.env` وارد کن.
3. مدل پیش‌فرض `claude-sonnet-4-6-free` است؛ دسترسی مدل‌ها و موجودی/سهمیه را در داشبورد APMIX بررسی کن. شناسهٔ دقیق مدل را می‌توانی از API فهرست مدل‌ها ببینی:

   ```bash
   curl https://api.apmix.ai/v1/models \
     -H "Authorization: Bearer apx_live_YOUR_KEY"
   ```

4. اگر مدل پیش‌فرض برای کلیدت فعال نیست، متغیر `APMIX_MODEL` را در Railway به شناسهٔ مجاز تغییر بده. ورودی تصویر نیز به پشتیبانی مدل انتخاب‌شده نیاز دارد.

اتصال Chat Completions از `https://api.apmix.ai/v1/chat/completions` استفاده می‌کند؛ مستندات را در [APMIX API Docs](https://apmix.ai/docs) ببین.

## متغیرهای محیطی

در Railway → Service → **Variables** این مقادیر را تنظیم کن:

- `TELEGRAM_BOT_TOKEN` — توکن ساخته‌شده با `@BotFather`.
- `TELEGRAM_ALLOWED_USER_ID` — شناسهٔ عددی حساب تلگرامی مجاز.
- `APMIX_API_KEY` — کلید داشبورد APMIX.
- `APMIX_MODEL` — شناسهٔ مدل مجاز APMIX؛ پیش‌فرض `claude-sonnet-4-6-free`.
- `TOOKEN_API_KEY` — کلید API حساب Tooken؛ فقط در Railway Variables وارد شود.
- `TOOKEN_API_BASE_URL` — آدرس پایهٔ سازگار با OpenAI از داشبورد/مستندات Tooken؛ آن را حدس نزن.
- `TOOKEN_MODEL` — شناسهٔ دقیق مدل مجاز در Tooken.
- `AI_PROVIDER_ORDER` — ترتیب تلاش و fallback؛ پیش‌فرض `apmix,tooken`، برای اولویت Tooken مقدار `tooken,apmix` بگذار.
- `TAVILY_API_KEY` — کلید Tavily برای جست‌وجوی وب و منابع. بدون آن گفت‌وگوی عادی فعال می‌ماند، اما جست‌وجوی وب غیرفعال است.
- `TIMEZONE` — منطقهٔ زمانی؛ پیش‌فرض `Asia/Tehran`.
- `BOT_DATA_DIR` — در Railway مقدار `/data`.

`.env.example` فقط قالب متغیرهاست و هیچ کلید واقعی ندارد. فایل `.env` در Git نادیده گرفته می‌شود.

## استقرار روی Railway از GitHub

1. در Railway یک Project بساز و **Deploy from GitHub Repo** را انتخاب کن؛ مخزن و شاخهٔ `main` را وصل کن.
2. این برنامه یک **worker** است؛ فرمان اجرا `python bot.py` است و در `Procfile` هم تعریف شده. پورت عمومی لازم نیست.
3. متغیرهای محیطی بالا را وارد کن.
4. یک Railway Volume به مسیر `/data` وصل کن و `BOT_DATA_DIR=/data` قرار بده. **بدون Volume ممکن است سابقهٔ گفت‌وگو و داده‌های قدیمی SQLite با بازاستقرار از دست بروند.**
5. سرویس را Deploy کن. در Logs باید پیامی شبیه `Telegram bot connected as @...` دیده شود.
6. در تلگرام Start را بزن و گفت‌وگو و جست‌وجوی وب را آزمایش کن.

## اجرای محلی

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# مقدارهای محرمانه را فقط در .env محلی وارد کنید؛ این فایل در .gitignore است.
python bot.py
```

## حریم خصوصی و امنیت

- پیش از پردازش محتوا، شناسهٔ تلگرامی با `TELEGRAM_ALLOWED_USER_ID` مقایسه می‌شود؛ پیام‌های گروهی نادیده گرفته می‌شوند.
- تاریخچهٔ گفت‌وگو در SQLite نگه داشته می‌شود. داده‌های قدیمیِ قابلیت‌های حذف‌شده پاک نشده‌اند؛ برای حذف کامل آن‌ها باید دادهٔ SQLite مربوط به سرویس را جداگانه مدیریت کنی.
- درخواست‌های مدل، متن‌ها و تصاویر انتخاب‌شده به ارائه‌دهنده‌ای فرستاده می‌شوند که در `AI_PROVIDER_ORDER` موفق شود؛ فقط عبارت‌های جست‌وجو و درخواست‌های موضوعی برای بازیابی وب به Tavily می‌روند. سیاست‌های نگه‌داری دادهٔ این سرویس‌ها را بررسی کن.
- کلیدهای واقعی را commit نکن. اگر کلیدی افشا شد، آن را در سرویس مربوط لغو و دوباره صادر کن.

## منابع رسمی

- [Tooken Club](https://tooken.club/)
- [APMIX API Docs](https://apmix.ai/docs)
- [APMIX Models](https://apmix.ai/models)
- [APMIX Pricing](https://apmix.ai/pricing)
- [Telegram Bot API: `getUpdates`](https://core.telegram.org/bots/api#getupdates)
- [Railway services](https://docs.railway.com/services)
- [Railway Volumes](https://docs.railway.com/volumes)
