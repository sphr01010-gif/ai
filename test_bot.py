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
    assert button_labels == {"گفت‌وگو", "جست‌وجوی وب"}
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
    assert bot.MENU_BUTTON_ACTIONS == {"گفت‌وگو": "chat", "جست‌وجوی وب": "search"}
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


def test_tooken_chat_uses_configured_openai_compatible_endpoint(monkeypatch):
    monkeypatch.setattr(bot, "TOOKEN_API_KEY", "tooken-test-key")
    monkeypatch.setattr(bot, "TOOKEN_API_BASE_URL", "https://api.example.test/v1")
    monkeypatch.setattr(bot, "TOOKEN_MODEL", "test-model")

    class FakeResponse:
        status_code = 200
        text = ""

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "hello from Tooken"}}]}

    class FakeClient:
        async def post(self, url, **kwargs):
            self.call = (url, kwargs)
            return FakeResponse()

    client = FakeClient()
    result = asyncio.run(bot.tooken_chat(client, [{"role": "user", "content": "hi"}]))
    assert result["choices"][0]["message"]["content"] == "hello from Tooken"
    url, kwargs = client.call
    assert url == "https://api.example.test/v1/chat/completions"
    assert kwargs["headers"]["Authorization"] == "Bearer tooken-test-key"
    assert kwargs["json"]["model"] == "test-model"


def test_model_chat_falls_back_from_apmix_to_tooken(monkeypatch):
    monkeypatch.setattr(bot, "AI_PROVIDER_ORDER", ["apmix", "tooken"])
    monkeypatch.setattr(bot, "APMIX_API_KEY", "apmix-test-key")
    monkeypatch.setattr(bot, "TOOKEN_API_KEY", "tooken-test-key")
    monkeypatch.setattr(bot, "TOOKEN_API_BASE_URL", "https://api.example.test/v1")
    monkeypatch.setattr(bot, "TOOKEN_MODEL", "test-model")
    calls = []

    async def fail_apmix(*args, **kwargs):
        calls.append("apmix")
        raise RuntimeError("temporary provider failure")

    async def succeed_tooken(*args, **kwargs):
        calls.append("tooken")
        return {"choices": [{"message": {"content": "fallback worked"}}]}

    monkeypatch.setattr(bot, "apmix_chat", fail_apmix)
    monkeypatch.setattr(bot, "tooken_chat", succeed_tooken)
    result = asyncio.run(bot.model_chat(object(), [{"role": "user", "content": "hi"}]))
    assert result["choices"][0]["message"]["content"] == "fallback worked"
    assert calls == ["apmix", "tooken"]
