import asyncio
from datetime import datetime, timedelta

import bot


def test_persian_digit_normalization():
    assert bot.convert_persian_digits("۳۰ دقیقه") == "30 دقیقه"
    assert bot.convert_persian_digits("٢٠٢٦") == "2026"


def test_relative_reminder_parsing():
    parsed = bot.parse_reminder_command("30m تست یادآوری")
    assert parsed is not None
    due, text = parsed
    assert text == "تست یادآوری"
    assert due.tzinfo is not None
    assert 29 * 60 <= (due - datetime.now(bot.TZ)).total_seconds() <= 31 * 60


def test_persian_relative_reminder_parsing():
    parsed = bot.parse_reminder_input("۳۰ دقیقه دیگر تماس")
    assert parsed is not None
    due, text, recurrence = parsed
    assert text == "تماس" and recurrence == ""
    assert 29 * 60 <= (due - datetime.now(bot.TZ)).total_seconds() <= 31 * 60


def test_tomorrow_morning_is_parsed_for_confirmation():
    parsed = bot.parse_reminder_input("فردا صبح تماس با علی")
    assert parsed is not None
    due, text, recurrence = parsed
    assert due.date() == (datetime.now(bot.TZ).date() + timedelta(days=1))
    assert due.hour == 9 and due.minute == 0
    assert text == "تماس با علی" and recurrence == ""


def test_daily_and_weekly_reminder_recurrence():
    daily = bot.parse_reminder_input("هر روز ساعت ۸:۳۰ دارو")
    weekly = bot.parse_reminder_input("هر هفته شنبه ساعت ۹:۰۰ خرید")
    assert daily and daily[2] == "daily" and daily[1] == "دارو"
    assert weekly and weekly[2] == "weekly" and weekly[1] == "خرید"
    assert daily[0].tzinfo is not None and weekly[0].tzinfo is not None


def test_absolute_reminder_parsing_uses_tehran_timezone():
    parsed = bot.parse_reminder_command("2999-05-04 09:25 آزمایش")
    assert parsed is not None
    due, text = parsed
    assert text == "آزمایش"
    assert due.year == 2999 and due.month == 5 and due.day == 4
    assert due.hour == 9 and due.minute == 25
    assert str(due.tzinfo) == "Asia/Tehran"


def test_invalid_or_past_reminder_is_rejected():
    assert bot.parse_reminder_command("/remind 2999-99-99 09:25 bad") is None
    assert bot.parse_reminder_command("/remind 2000-01-01 00:01 old") is None
    assert bot.parse_reminder_command("/remind after lunch") is None
    assert bot.parse_reminder_input("هر روز ساعت 99 دارو") is None
    assert bot.parse_reminder_input("0m همین الان") is None


def test_reminder_persistence_and_daily_recurrence(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DB_PATH", tmp_path / "test.sqlite3")
    bot.init_db()
    due = datetime.now(bot.TZ) - timedelta(minutes=1)
    reminder_id = bot.add_reminder(1234, due, "persistent", "daily")
    rows = bot.take_due_reminders()
    assert any(row[0] == reminder_id and row[1] == 1234 and row[2] == "persistent" for row in rows)
    bot.mark_reminder_sent(reminder_id)
    assert bot.take_due_reminders() == []
    item = bot.get_reminder(1234, reminder_id)
    assert item is not None and item[3] == "daily" and item[4] == 0
    assert datetime.fromisoformat(item[1]) > datetime.now(bot.TZ)


def test_snooze_creates_a_one_off_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DB_PATH", tmp_path / "snooze.sqlite3")
    bot.init_db()
    reminder_id = bot.add_reminder(123, datetime.now(bot.TZ) - timedelta(minutes=1), "call", "weekly")
    assert bot.snooze_reminder(123, reminder_id, 10)
    reminders = bot.list_reminders(123, limit=10)
    assert len(reminders) == 2
    snoozed = [bot.get_reminder(123, row[0]) for row in reminders if row[0] != reminder_id][0]
    assert snoozed[2] == "call" and snoozed[3] == ""


def test_unauthorized_user_is_not_processed(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DB_PATH", tmp_path / "private.sqlite3")
    monkeypatch.setattr(bot, "ALLOWED_USER_ID", "987654321")
    calls = []

    async def fake_telegram_call(client, method, payload):
        calls.append((method, payload))
        return True

    monkeypatch.setattr(bot, "telegram_call", fake_telegram_call)
    message = {"from": {"id": 123}, "chat": {"id": 123, "type": "private"}, "text": "secret text"}
    asyncio.run(bot.process_message(object(), message))
    assert len(calls) == 1
    assert calls[0][0] == "sendMessage"
    assert "secret text" not in str(calls[0][1])


def test_apmix_chat_uses_openai_compatible_endpoint_and_bearer_key(monkeypatch):
    monkeypatch.setattr(bot, "APMIX_API_KEY", "test-key")
    monkeypatch.setattr(bot, "MODEL", "claude-sonnet-4-6-free")

    class FakeResponse:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "hello"}}]}

    class FakeClient:
        def __init__(self):
            self.call = None

        async def post(self, url, **kwargs):
            self.call = (url, kwargs)
            return FakeResponse()

    client = FakeClient()
    result = asyncio.run(bot.apmix_chat(client, [{"role": "user", "content": "hi"}]))
    assert result["choices"][0]["message"]["content"] == "hello"
    url, kwargs = client.call
    assert url == "https://api.apmix.ai/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert kwargs["json"]["model"] == "claude-sonnet-4-6-free"


def test_apmix_chat_requires_apmix_key(monkeypatch):
    monkeypatch.setattr(bot, "APMIX_API_KEY", "")

    class FakeClient:
        async def post(self, *args, **kwargs):
            raise AssertionError("API must not be called without a key")

    try:
        asyncio.run(bot.apmix_chat(FakeClient(), []))
        assert False, "expected missing-key error"
    except RuntimeError as exc:
        assert "APMIX_API_KEY" in str(exc)


def test_web_search_trigger_detection():
    assert bot.should_search_web("What is the latest weather today?")
    assert bot.should_search_web("آخرین قیمت دلار چقدر است؟")
    assert not bot.should_search_web("سلام، حالت چطوره؟")


def test_voice_input_is_not_sent_to_another_ai_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DB_PATH", tmp_path / "voice.sqlite3")
    bot.init_db()
    monkeypatch.setattr(bot, "ALLOWED_USER_ID", "123")
    calls = []

    async def fake_telegram_call(client, method, payload):
        calls.append((method, payload))
        return True

    async def forbidden_apmix_call(*args, **kwargs):
        raise AssertionError("unsupported voice must not be forwarded to an unverified endpoint")

    monkeypatch.setattr(bot, "telegram_call", fake_telegram_call)
    monkeypatch.setattr(bot, "apmix_chat", forbidden_apmix_call)
    message = {"from": {"id": 123}, "chat": {"id": 123, "type": "private"}, "voice": {"file_id": "voice-file"}}
    asyncio.run(bot.process_message(object(), message))
    assert any(method == "sendMessage" and "ورودی صوتی" in payload["text"] for method, payload in calls)


def test_start_message_includes_persistent_reply_menu(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DB_PATH", tmp_path / "start-menu.sqlite3")
    bot.init_db()
    monkeypatch.setattr(bot, "ALLOWED_USER_ID", "123")
    calls = []

    async def fake_telegram_call(client, method, payload):
        calls.append((method, payload))
        return True

    monkeypatch.setattr(bot, "telegram_call", fake_telegram_call)
    message = {"from": {"id": 123}, "chat": {"id": 123, "type": "private"}, "message_id": 10, "text": "/start"}
    asyncio.run(bot.process_message(object(), message))
    assert len(calls) == 1
    method, payload = calls[0]
    assert method == "sendMessage"
    assert payload["reply_markup"] == bot.MAIN_MENU_MARKUP
    button_labels = {button["text"] for row in payload["reply_markup"]["keyboard"] for button in row}
    assert button_labels == {"گفت‌وگو", "جست‌وجوی وب", "انتخاب API"}
    assert payload["reply_markup"]["is_persistent"] is True
    assert payload["reply_markup"]["resize_keyboard"] is True


def test_removed_menu_options_are_hidden_and_inert(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DB_PATH", tmp_path / "removed-menu.sqlite3")
    monkeypatch.setattr(bot, "ALLOWED_USER_ID", "123")
    bot.init_db()
    calls = []
    removed = {
        "ثبت یادآوری", "بررسی عکس/سند", "تنظیمات", "مقایسهٔ منابع",
        "یادآوری‌های من", "حافظهٔ شخصی", "خلاصه‌ها", "پاک‌کردن حافظه", "راهنما",
    }
    assert bot.MENU_BUTTON_ACTIONS["گفت‌وگو"] == "chat"
    assert bot.MENU_BUTTON_ACTIONS["جست‌وجوی وب"] == "search"
    assert bot.MENU_BUTTON_ACTIONS["انتخاب API"] == "provider_menu"
    assert removed <= bot.REMOVED_MENU_BUTTON_LABELS

    async def fake_telegram_call(client, method, payload):
        calls.append((method, payload))
        return True

    monkeypatch.setattr(bot, "telegram_call", fake_telegram_call)

    async def exercise_removed_labels():
        for label in sorted(removed):
            await bot.process_message(object(), {
                "from": {"id": 123}, "chat": {"id": 123, "type": "private"}, "text": label,
            })

    asyncio.run(exercise_removed_labels())
    assert len(calls) == len(removed)
    assert all(method == "sendMessage" for method, _ in calls)
    assert all("حذف شده" in payload["text"] for _, payload in calls)
    assert all(payload["reply_markup"] == bot.MAIN_MENU_MARKUP for _, payload in calls)
    assert bot.get_user_state(123) is None


def test_unauthorized_callback_is_answered_but_not_processed(monkeypatch):
    monkeypatch.setattr(bot, "ALLOWED_USER_ID", "123")
    calls = []

    async def fake_telegram_call(client, method, payload):
        calls.append((method, payload))
        return True

    monkeypatch.setattr(bot, "telegram_call", fake_telegram_call)
    callback = {"id": "callback-1", "from": {"id": 999}, "message": {"chat": {"id": 999, "type": "private"}}, "data": "menu:help"}
    asyncio.run(bot.process_callback_query(object(), callback))
    assert len(calls) == 1
    method, payload = calls[0]
    assert method == "answerCallbackQuery"
    assert payload["show_alert"] is True
    assert "خصوصی" in payload["text"]




def test_search_button_routes_plain_text_to_web_search(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DB_PATH", tmp_path / "search-flow.sqlite3")
    monkeypatch.setattr(bot, "ALLOWED_USER_ID", "123")
    bot.init_db()
    queries = []
    calls = []

    async def fake_search(client, query, *, compare=False):
        queries.append((query, compare))
        return "search result"

    async def fake_telegram_call(client, method, payload):
        calls.append((method, payload))
        return True

    monkeypatch.setattr(bot, "explicit_search_reply", fake_search)
    monkeypatch.setattr(bot, "telegram_call", fake_telegram_call)
    base = {"from": {"id": 123}, "chat": {"id": 123, "type": "private"}}
    asyncio.run(bot.process_message(object(), {**base, "message_id": 10, "text": "جست‌وجوی وب"}))
    assert bot.get_user_state(123) == "await_search"
    asyncio.run(bot.process_message(object(), {**base, "message_id": 11, "text": "latest space news"}))
    assert queries == [("latest space news", False)]
    assert calls[-1][1]["text"] == "search result"
    assert calls[-1][1]["reply_markup"] == bot.MAIN_MENU_MARKUP
    assert bot.get_user_state(123) is None








def test_reminder_delete_is_scoped_to_owning_user(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DB_PATH", tmp_path / "reminder-delete.sqlite3")
    bot.init_db()
    bot.add_reminder(123, datetime(2999, 5, 4, 9, 25, tzinfo=bot.TZ), "owned")
    reminder_id = bot.list_reminders(123)[0][0]
    assert bot.delete_reminder(999, reminder_id) is False
    assert len(bot.list_reminders(123)) == 1
    assert bot.delete_reminder(123, reminder_id) is True
    assert bot.list_reminders(123) == []




def test_personal_memory_is_explicit_and_user_scoped(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DB_PATH", tmp_path / "memory.sqlite3")
    bot.init_db()
    memory_id = bot.add_memory(123, "ترجیح می‌دهم پاسخ‌ها کوتاه باشند")
    assert bot.list_memories(123)[0] == (memory_id, "ترجیح می‌دهم پاسخ‌ها کوتاه باشند")
    assert bot.list_memories(999) == []
    assert bot.delete_memory(999, memory_id) is False
    assert bot.delete_memory(123, memory_id) is True
    assert bot.list_memories(123) == []






def test_user_settings_persist_across_reads(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DB_PATH", tmp_path / "settings.sqlite3")
    bot.init_db()
    settings = bot.set_user_setting(123, "language", "en")
    assert settings["language"] == "en"
    assert bot.get_user_settings(123)["language"] == "en"
    assert bot.get_user_settings(123)["history_enabled"] is True


def test_history_disabled_does_not_store_chat_turns(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DB_PATH", tmp_path / "history-off.sqlite3")
    monkeypatch.setattr(bot, "APMIX_API_KEY", "test")
    bot.init_db()
    bot.set_user_setting(123, "history_enabled", False)
    bot.add_memory(123, "پاسخ‌ها را به فارسی بده")
    captured = []

    async def fake_apmix(client, messages, **kwargs):
        captured.extend(messages)
        return {"choices": [{"message": {"content": "جواب"}}]}

    monkeypatch.setattr(bot, "apmix_chat", fake_apmix)
    result = asyncio.run(bot.assistant_reply(object(), 123, "سلام"))
    assert result == "جواب"
    assert bot.load_history(123) == []
    assert "پاسخ‌ها را به فارسی بده" in captured[0]["content"]


def test_file_context_roundtrip_and_forget(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DB_PATH", tmp_path / "files.sqlite3")
    bot.init_db()
    images = [b"page-1", b"page-2"]
    stored = bot.encode_saved_images(images)
    bot.save_user_file(123, "scan.pdf", "", stored)
    record = bot.get_user_file(123)
    assert record[0] == "scan.pdf"
    assert bot.decode_saved_images(record[2]) == images
    assert bot.clear_user_file(123) is True
    assert bot.get_user_file(123) is None


def test_follow_topics_are_user_scoped_and_removable(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DB_PATH", tmp_path / "topics.sqlite3")
    bot.init_db()
    topic_id = bot.add_follow_topic(123, "خبرهای هوش مصنوعی")
    assert bot.list_follow_topics(123) == [(topic_id, "خبرهای هوش مصنوعی")]
    assert bot.list_follow_topics(999) == []
    assert bot.delete_follow_topic(123, topic_id)
    assert bot.list_follow_topics(123) == []








def test_reminder_list_button_snooze_labels_include_id():
    markup = bot.reminder_notification_markup(42)
    labels = [button["text"] for row in markup["keyboard"] for button in row]
    assert "تعویق ۱۰ دقیقه (42)" in labels
    assert "تعویق ۱ ساعت (42)" in labels


def test_snooze_button_creates_new_reminder(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DB_PATH", tmp_path / "snooze-button.sqlite3")
    monkeypatch.setattr(bot, "ALLOWED_USER_ID", "123")
    bot.init_db()
    reminder_id = bot.add_reminder(123, datetime.now(bot.TZ) - timedelta(minutes=1), "call")
    bot.mark_reminder_sent(reminder_id)
    calls = []

    async def fake_telegram_call(client, method, payload):
        calls.append((method, payload))
        return True

    monkeypatch.setattr(bot, "telegram_call", fake_telegram_call)
    message = {"from": {"id": 123}, "chat": {"id": 123, "type": "private"}, "text": f"تعویق ۱۰ دقیقه ({reminder_id})"}
    asyncio.run(bot.process_message(object(), message))
    assert len(bot.list_reminders(123)) == 1
    assert bot.list_reminders(123)[0][2] == "call"
    assert "10 دقیقه" in calls[-1][1]["text"]


def test_scanned_pdf_pages_render_for_ocr(tmp_path):
    import fitz
    document = fitz.open()
    page = document.new_page()
    page.insert_text((50, 50), "scan test")
    raw = document.tobytes()
    rendered = bot.render_pdf_pages(raw)
    assert len(rendered) == 1
    assert rendered[0].startswith(b"\x89PNG")


def test_summary_includes_saved_topics_and_sends_result(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DB_PATH", tmp_path / "summary.sqlite3")
    monkeypatch.setattr(bot, "APMIX_API_KEY", "test")
    monkeypatch.setattr(bot, "TAVILY_API_KEY", "")
    bot.init_db()
    due = datetime.now(bot.TZ) + timedelta(hours=3)
    bot.add_reminder(123, due, "گرفتن دارو")
    bot.add_follow_topic(123, "هوش مصنوعی")
    apmix_calls = []
    telegram_calls = []

    async def fake_apmix(client, messages, **kwargs):
        apmix_calls.extend(messages)
        return {"choices": [{"message": {"content": "خلاصه آماده"}}]}

    async def fake_telegram_call(client, method, payload):
        telegram_calls.append((method, payload))
        return True

    monkeypatch.setattr(bot, "apmix_chat", fake_apmix)
    monkeypatch.setattr(bot, "telegram_call", fake_telegram_call)
    asyncio.run(bot.send_personal_summary(object(), 123, weekly=False))
    assert "گرفتن دارو" in apmix_calls[-1]["content"]
    assert "هوش مصنوعی" in apmix_calls[-1]["content"]
    assert telegram_calls[-1][1]["text"] == "خلاصه آماده"


def test_export_reminders_sends_csv_document(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DB_PATH", tmp_path / "export.sqlite3")
    bot.init_db()
    bot.add_reminder(123, datetime(2999, 5, 4, 9, 25, tzinfo=bot.TZ), "task", "weekly")
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            pass

        @staticmethod
        def json():
            return {"ok": True}

    class FakeClient:
        async def post(self, url, **kwargs):
            captured["url"] = url
            captured.update(kwargs)
            return FakeResponse()

    monkeypatch.setattr(bot, "TG_API", "https://api.telegram.org/botTOKEN")
    asyncio.run(bot.send_reminder_export(FakeClient(), 123, 123))
    assert captured["url"].endswith("/sendDocument")
    assert captured["files"]["document"][0] == "reminders.csv"
    assert b"weekly" not in captured["files"]["document"][1]
    assert b"task" in captured["files"]["document"][1]


def test_gemini_chat_uses_google_generate_content_api(monkeypatch):
    monkeypatch.setattr(bot, "GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setattr(bot, "GEMINI_MODEL", "gemini-3.8-flash")

    class FakeResponse:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"candidates": [{"content": {"parts": [{"text": "hello from Gemini"}]}}]}

    class FakeClient:
        async def post(self, url, **kwargs):
            self.call = (url, kwargs)
            return FakeResponse()

    client = FakeClient()
    result = asyncio.run(bot.gemini_chat(client, [
        {"role": "system", "content": "Be helpful"},
        {"role": "user", "content": "hi"},
    ]))
    assert result["choices"][0]["message"]["content"] == "hello from Gemini"
    url, kwargs = client.call
    assert url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.8-flash:generateContent"
    assert kwargs["headers"]["x-goog-api-key"] == "gemini-test-key"
    assert kwargs["json"]["system_instruction"]["parts"][0]["text"] == "Be helpful"
    assert kwargs["json"]["contents"] == [{"role": "user", "parts": [{"text": "hi"}]}]


def test_gemini_chat_converts_inline_image_to_google_part(monkeypatch):
    import base64
    monkeypatch.setattr(bot, "GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setattr(bot, "GEMINI_MODEL", "gemini-3.8-flash")
    image = base64.b64encode(b"fake-image").decode("ascii")

    class FakeResponse:
        status_code = 200
        @staticmethod
        def json():
            return {"candidates": [{"content": {"parts": [{"text": "image seen"}]}}]}

    class FakeClient:
        async def post(self, url, **kwargs):
            self.payload = kwargs["json"]
            return FakeResponse()

    client = FakeClient()
    asyncio.run(bot.gemini_chat(client, [{"role": "user", "content": [
        {"type": "text", "text": "Describe"},
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image}"}},
    ]}]))
    parts = client.payload["contents"][0]["parts"]
    assert parts[0] == {"text": "Describe"}
    assert parts[1] == {"inline_data": {"mime_type": "image/jpeg", "data": image}}


def test_model_chat_falls_back_from_apmix_to_gemini(monkeypatch):
    monkeypatch.setattr(bot, "AI_PROVIDER_ORDER", ["apmix", "gemini"])
    monkeypatch.setattr(bot, "APMIX_API_KEY", "apmix-test-key")
    monkeypatch.setattr(bot, "GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setattr(bot, "GEMINI_MODEL", "test-model")
    calls = []

    async def fail_apmix(*args, **kwargs):
        calls.append("apmix")
        raise RuntimeError("temporary provider failure")

    async def succeed_gemini(*args, **kwargs):
        calls.append("gemini")
        return {"choices": [{"message": {"content": "fallback worked"}}]}

    monkeypatch.setattr(bot, "apmix_chat", fail_apmix)
    monkeypatch.setattr(bot, "gemini_chat", succeed_gemini)
    result = asyncio.run(bot.model_chat(object(), [{"role": "user", "content": "hi"}]))
    assert result["choices"][0]["message"]["content"] == "fallback worked"
    assert calls == ["apmix", "gemini"]



def test_provider_selection_persists_and_requires_configuration(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DB_PATH", tmp_path / "provider-selection.sqlite3")
    monkeypatch.setattr(bot, "ALLOWED_USER_ID", "123")
    monkeypatch.setattr(bot, "APMIX_API_KEY", "apmix-test-key")
    monkeypatch.setattr(bot, "GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setattr(bot, "GEMINI_MODEL", "test-model")
    bot.init_db()
    calls = []

    async def fake_telegram_call(client, method, payload):
        calls.append((method, payload))
        return True

    monkeypatch.setattr(bot, "telegram_call", fake_telegram_call)
    base = {"from": {"id": 123}, "chat": {"id": 123, "type": "private"}}
    asyncio.run(bot.process_message(object(), {**base, "text": "انتخاب API"}))
    assert calls[-1][1]["reply_markup"] == bot.ai_provider_markup(123)
    asyncio.run(bot.process_message(object(), {**base, "text": "Gemini"}))
    assert bot.get_user_settings(123)["ai_provider"] == "gemini"
    assert calls[-1][1]["reply_markup"] == bot.MAIN_MENU_MARKUP

    asyncio.run(bot.process_message(object(), {**base, "text": "APMIX"}))
    assert bot.get_user_settings(123)["ai_provider"] == "apmix"
    asyncio.run(bot.process_message(object(), {**base, "text": "خودکار"}))
    assert bot.get_user_settings(123)["ai_provider"] == "auto"

    monkeypatch.setattr(bot, "GEMINI_API_KEY", "")
    asyncio.run(bot.process_message(object(), {**base, "text": "Gemini"}))
    assert bot.get_user_settings(123)["ai_provider"] == "auto"
    assert "GEMINI_API_KEY" in calls[-1][1]["text"]


def test_assistant_reply_uses_the_user_selected_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DB_PATH", tmp_path / "provider-chat.sqlite3")
    bot.init_db()
    bot.set_user_setting(123, "ai_provider", "gemini")
    observed = []

    async def fake_model_chat(client, messages, *, model=None, provider=None, fallback_on_error=False):
        observed.append((provider, fallback_on_error))
        return {"choices": [{"message": {"content": "Gemini response"}}]}

    monkeypatch.setattr(bot, "model_chat", fake_model_chat)
    result = asyncio.run(bot.assistant_reply(object(), 123, "سلام"))
    assert result == "Gemini response"
    assert observed == [("gemini", False)]


def test_explicit_provider_selection_does_not_fallback(monkeypatch):
    monkeypatch.setattr(bot, "AI_PROVIDER_ORDER", ["apmix", "gemini"])
    monkeypatch.setattr(bot, "APMIX_API_KEY", "apmix-test-key")
    monkeypatch.setattr(bot, "GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setattr(bot, "GEMINI_MODEL", "test-model")
    calls = []

    async def unexpected_apmix(*args, **kwargs):
        calls.append("apmix")
        raise AssertionError("selected Gemini must not call APMIX")

    async def succeed_gemini(*args, **kwargs):
        calls.append("gemini")
        return {"choices": [{"message": {"content": "selected Gemini"}}]}

    monkeypatch.setattr(bot, "apmix_chat", unexpected_apmix)
    monkeypatch.setattr(bot, "gemini_chat", succeed_gemini)
    result = asyncio.run(bot.model_chat(object(), [{"role": "user", "content": "hi"}], provider="gemini"))
    assert result["choices"][0]["message"]["content"] == "selected Gemini"
    assert calls == ["gemini"]


def test_provider_errors_show_actionable_details_without_leaking_keys(monkeypatch):
    monkeypatch.setattr(bot, "AI_PROVIDER_ORDER", ["gemini"])
    monkeypatch.setattr(bot, "APMIX_API_KEY", "")
    monkeypatch.setattr(bot, "GEMINI_API_KEY", "super-secret-gemini-key")
    monkeypatch.setattr(bot, "GEMINI_MODEL", "test-model")

    async def fail_gemini(*args, **kwargs):
        raise RuntimeError("Gemini API HTTP 401: invalid key super-secret-gemini-key")

    monkeypatch.setattr(bot, "gemini_chat", fail_gemini)
    try:
        asyncio.run(bot.model_chat(object(), [{"role": "user", "content": "hi"}], provider="gemini"))
    except RuntimeError as exc:
        assert "HTTP 401" in str(exc)
        assert "invalid key" in str(exc)
        assert "super-secret-gemini-key" not in str(exc)
        assert "[REDACTED]" in str(exc)
    else:
        raise AssertionError("provider failure should be surfaced")


def test_removed_provider_setting_migrates_to_auto(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DB_PATH", tmp_path / "legacy-provider-setting.sqlite3")
    bot.init_db()
    bot.save_user_settings(321, {"ai_provider": "tooken", "language": "fa"})
    settings = bot.get_user_settings(321)
    assert settings["ai_provider"] == "auto"
    assert settings["language"] == "fa"



def test_gemini_retries_transient_503_then_succeeds(monkeypatch):
    monkeypatch.setattr(bot, "GEMINI_API_KEY", "gemini-test-key")
    monkeypatch.setattr(bot, "GEMINI_MODEL", "gemini-3.8-flash")
    sleeps = []

    async def no_sleep(delay):
        sleeps.append(delay)

    monkeypatch.setattr(bot.asyncio, "sleep", no_sleep)

    class FakeResponse:
        def __init__(self, status, body):
            self.status_code = status
            self.text = body
            self.headers = {}

        @staticmethod
        def json():
            return {"candidates": [{"content": {"parts": [{"text": "recovered"}]}}]}

    class FakeClient:
        def __init__(self):
            self.responses = [FakeResponse(503, '{"error":"busy"}'), FakeResponse(200, "")]
            self.calls = 0

        async def post(self, url, **kwargs):
            self.calls += 1
            return self.responses.pop(0)

    client = FakeClient()
    result = asyncio.run(bot.gemini_chat(client, [{"role": "user", "content": "hi"}]))
    assert result["choices"][0]["message"]["content"] == "recovered"
    assert client.calls == 2 and len(sleeps) == 1 and sleeps[0] >= 1


def test_explicit_provider_failover_is_opt_in(monkeypatch):
    monkeypatch.setattr(bot, "AI_PROVIDER_ORDER", ["apmix", "gemini"])
    monkeypatch.setattr(bot, "APMIX_API_KEY", "apmix-test-key")
    monkeypatch.setattr(bot, "GEMINI_API_KEY", "gemini-test-key")
    calls = []

    async def fail_gemini(*args, **kwargs):
        calls.append("gemini")
        raise RuntimeError("temporary outage")

    async def succeed_apmix(*args, **kwargs):
        calls.append("apmix")
        return {"choices": [{"message": {"content": "fallback answer"}}]}

    monkeypatch.setattr(bot, "gemini_chat", fail_gemini)
    monkeypatch.setattr(bot, "apmix_chat", succeed_apmix)
    try:
        asyncio.run(bot.model_chat(object(), [{"role": "user", "content": "hi"}], provider="gemini"))
    except RuntimeError as exc:
        assert "temporary outage" in str(exc)
    else:
        raise AssertionError("manual provider must not fail over by default")
    assert calls == ["gemini"]

    calls.clear()
    result = asyncio.run(bot.model_chat(object(), [{"role": "user", "content": "hi"}], provider="gemini", fallback_on_error=True))
    assert result["choices"][0]["message"]["content"] == "fallback answer"
    assert calls == ["gemini", "apmix"]


def test_provider_fallback_toggle_persists_and_updates_button(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DB_PATH", tmp_path / "fallback-toggle.sqlite3")
    monkeypatch.setattr(bot, "ALLOWED_USER_ID", "123")
    bot.init_db()
    calls = []

    async def fake_telegram_call(client, method, payload):
        calls.append(payload)
        return True

    monkeypatch.setattr(bot, "telegram_call", fake_telegram_call)
    base = {"from": {"id": 123}, "chat": {"id": 123, "type": "private"}}
    asyncio.run(bot.process_message(object(), {**base, "text": "انتخاب API"}))
    assert bot.get_user_settings(123)["fallback_on_error"] is False
    asyncio.run(bot.process_message(object(), {**base, "text": "جایگزینی هنگام خطا: خاموش"}))
    assert bot.get_user_settings(123)["fallback_on_error"] is True
    assert "جایگزینی هنگام خطا: روشن" in str(calls[-1]["reply_markup"])


def test_weather_tool_calls_open_meteo_and_labels_source_and_local_time():
    class FakeResponse:
        def __init__(self, body):
            self.body = body
        def raise_for_status(self):
            pass
        def json(self):
            return self.body

    class FakeClient:
        def __init__(self):
            self.calls = []
        async def get(self, url, **kwargs):
            self.calls.append((url, kwargs))
            if "geocoding" in url:
                return FakeResponse({"results": [{"name": "شیراز", "admin1": "Fars", "country": "Iran", "latitude": 29.59, "longitude": 52.58}]})
            return FakeResponse({"timezone": "Asia/Tehran", "current": {"time": "2026-10-12T12:00", "temperature_2m": 25, "apparent_temperature": 26, "relative_humidity_2m": 30, "precipitation": 0, "weather_code": 0, "wind_speed_10m": 8}, "daily": {"time": ["2026-10-12"], "weather_code": [0], "temperature_2m_min": [15], "temperature_2m_max": [29]}})

    client = FakeClient()
    answer = asyncio.run(bot.dispatch_api_tool(client, "هوای شیراز چطوره؟"))
    assert len(client.calls) == 2
    assert client.calls[0][1]["params"]["name"] == "شیراز"
    assert "Open-Meteo" in answer and "Asia/Tehran" in answer and "29°C" in answer


def test_currency_tool_converts_persian_amount_and_shows_rate_date():
    class FakeResponse:
        def raise_for_status(self):
            pass
        @staticmethod
        def json():
            return {"date": "2026-10-12", "base": "USD", "quote": "EUR", "rate": 0.9}

    class FakeClient:
        def __init__(self):
            self.url = None
        async def get(self, url, **kwargs):
            self.url = url
            return FakeResponse()

    client = FakeClient()
    answer = asyncio.run(bot.dispatch_api_tool(client, "۱۰۰ دلار به یورو چند می‌شود؟"))
    assert client.url.endswith("/v2/rate/usd/eur")
    assert "100 USD ≈ 90 EUR" in answer
    assert "2026-10-12" in answer and "Frankfurter" in answer and "نرخ لحظه‌ای" in answer


def test_currency_intent_asks_for_missing_destination_instead_of_guessing():
    answer = asyncio.run(bot.dispatch_api_tool(object(), "نرخ دلار امروز چنده؟"))
    assert "ارز مقصد" in answer


def test_api_tool_registry_accepts_additional_handlers():
    async def example_tool(client, text, match):
        return "example-result"
    bot.register_api_tool("test-extension", __import__("re").compile("example"), example_tool)
    try:
        assert asyncio.run(bot.dispatch_api_tool(object(), "run example")) == "example-result"
    finally:
        bot.API_TOOL_REGISTRY.pop("test-extension", None)


def test_explicit_search_prompt_separates_sourced_facts_and_analysis(monkeypatch):
    observed = {}
    async def fake_tavily(client, query, *, deep=False):
        return {"results": [{"title": "Example", "url": "https://example.test", "published_date": "2026-10-10", "content": "Verified claim."}]}
    async def fake_model_chat(client, messages, *, model=None, provider=None, fallback_on_error=False):
        observed["prompt"] = messages[-1]["content"]
        return {"choices": [{"message": {"content": "ok"}}]}
    monkeypatch.setattr(bot, "tavily_search", fake_tavily)
    monkeypatch.setattr(bot, "model_chat", fake_model_chat)
    asyncio.run(bot.explicit_search_reply(object(), "What happened?"))
    assert "اطلاعات منبع‌شده" in observed["prompt"] and "تحلیل" in observed["prompt"]
    assert "2026-10-10" in observed["prompt"]


def test_currency_pair_without_conversion_intent_does_not_call_tool():
    answer = asyncio.run(bot.dispatch_api_tool(object(), "I like USD and EUR"))
    assert answer is None

