import asyncio
from datetime import datetime

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


def test_reminder_persistence(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DB_PATH", tmp_path / "test.sqlite3")
    bot.init_db()
    due = datetime(2000, 5, 4, 9, 25, tzinfo=bot.TZ)
    bot.add_reminder(1234, due, "persistent")
    rows = bot.take_due_reminders()
    assert any(row[1] == 1234 and row[2] == "persistent" for row in rows)
    bot.mark_reminder_sent(rows[0][0])
    assert bot.take_due_reminders() == []


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
        raise AssertionError("voice should not be forwarded to an undocumented API")

    monkeypatch.setattr(bot, "telegram_call", fake_telegram_call)
    monkeypatch.setattr(bot, "apmix_chat", forbidden_apmix_call)
    message = {
        "from": {"id": 123},
        "chat": {"id": 123, "type": "private"},
        "voice": {"file_id": "voice-file"},
    }
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
    message = {
        "from": {"id": 123},
        "chat": {"id": 123, "type": "private"},
        "message_id": 10,
        "text": "/start",
    }
    asyncio.run(bot.process_message(object(), message))
    assert len(calls) == 1
    method, payload = calls[0]
    assert method == "sendMessage"
    assert payload["reply_markup"] == bot.MAIN_MENU_MARKUP
    button_labels = {
        button["text"]
        for row in payload["reply_markup"]["keyboard"]
        for button in row
    }
    assert button_labels == {"گفت‌وگو", "جست‌وجوی وب", "ثبت یادآوری", "یادآوری‌های من", "بررسی عکس/سند", "پاک‌کردن حافظه", "راهنما"}
    assert payload["reply_markup"]["is_persistent"] is True
    assert payload["reply_markup"]["resize_keyboard"] is True


def test_unauthorized_callback_is_answered_but_not_processed(monkeypatch):
    monkeypatch.setattr(bot, "ALLOWED_USER_ID", "123")
    calls = []

    async def fake_telegram_call(client, method, payload):
        calls.append((method, payload))
        return True

    monkeypatch.setattr(bot, "telegram_call", fake_telegram_call)
    callback = {
        "id": "callback-1",
        "from": {"id": 999},
        "message": {"chat": {"id": 999, "type": "private"}},
        "data": "menu:help",
    }
    asyncio.run(bot.process_callback_query(object(), callback))
    assert len(calls) == 1
    method, payload = calls[0]
    assert method == "answerCallbackQuery"
    assert payload["show_alert"] is True
    assert "خصوصی" in payload["text"]


def test_reminder_callback_returns_instructions_and_menu(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DB_PATH", tmp_path / "reminder-callback.sqlite3")
    bot.init_db()
    monkeypatch.setattr(bot, "ALLOWED_USER_ID", "123")
    calls = []

    async def fake_telegram_call(client, method, payload):
        calls.append((method, payload))
        return True

    monkeypatch.setattr(bot, "telegram_call", fake_telegram_call)
    callback = {
        "id": "callback-2",
        "from": {"id": 123},
        "message": {"chat": {"id": 123, "type": "private"}},
        "data": "menu:remind",
    }
    asyncio.run(bot.process_callback_query(object(), callback))
    assert [method for method, _ in calls] == ["answerCallbackQuery", "sendMessage"]
    payload = calls[1][1]
    assert "30m تماس با علی" in payload["text"]
    assert "/remind" not in payload["text"]
    assert payload["reply_markup"] == bot.MAIN_MENU_MARKUP
    assert bot.get_user_state(123) == "await_reminder"


def test_search_button_routes_next_plain_text_to_web_search(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DB_PATH", tmp_path / "search-flow.sqlite3")
    monkeypatch.setattr(bot, "ALLOWED_USER_ID", "123")
    bot.init_db()
    queries = []
    calls = []

    async def fake_search(client, query):
        queries.append(query)
        return "search result"

    async def fake_telegram_call(client, method, payload):
        calls.append((method, payload))
        return True

    monkeypatch.setattr(bot, "explicit_search_reply", fake_search)
    monkeypatch.setattr(bot, "telegram_call", fake_telegram_call)
    menu_message = {
        "from": {"id": 123},
        "chat": {"id": 123, "type": "private"},
        "message_id": 10,
        "text": "جست‌وجوی وب",
    }
    asyncio.run(bot.process_message(object(), menu_message))
    assert bot.get_user_state(123) == "await_search"
    assert calls[-1][1]["reply_markup"] == bot.MAIN_MENU_MARKUP
    message = {
        "from": {"id": 123},
        "chat": {"id": 123, "type": "private"},
        "message_id": 11,
        "text": "latest space news",
    }
    asyncio.run(bot.process_message(object(), message))
    assert queries == ["latest space news"]
    assert calls[-1][0] == "sendMessage"
    assert calls[-1][1]["text"] == "search result"
    assert calls[-1][1]["reply_markup"] == bot.MAIN_MENU_MARKUP
    assert bot.get_user_state(123) is None


def test_reminder_button_accepts_plain_text_and_stores_it(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DB_PATH", tmp_path / "reminder-flow.sqlite3")
    monkeypatch.setattr(bot, "ALLOWED_USER_ID", "123")
    bot.init_db()
    calls = []

    async def fake_telegram_call(client, method, payload):
        calls.append((method, payload))
        return True

    monkeypatch.setattr(bot, "telegram_call", fake_telegram_call)
    menu_message = {
        "from": {"id": 123},
        "chat": {"id": 123, "type": "private"},
        "message_id": 11,
        "text": "ثبت یادآوری",
    }
    asyncio.run(bot.process_message(object(), menu_message))
    assert bot.get_user_state(123) == "await_reminder"
    message = {
        "from": {"id": 123},
        "chat": {"id": 123, "type": "private"},
        "message_id": 12,
        "text": "30m تماس با علی",
    }
    asyncio.run(bot.process_message(object(), message))
    reminders = bot.list_reminders(123)
    assert len(reminders) == 1
    assert reminders[0][2] == "تماس با علی"
    assert "/remind" not in calls[-1][1]["text"]
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


def test_clear_history_button_requires_confirmation(tmp_path, monkeypatch):
    monkeypatch.setattr(bot, "DB_PATH", tmp_path / "clear-confirm.sqlite3")
    monkeypatch.setattr(bot, "ALLOWED_USER_ID", "123")
    bot.init_db()
    bot.save_history(123, [{"role": "user", "content": "keep until confirmed"}])
    calls = []

    async def fake_telegram_call(client, method, payload):
        calls.append((method, payload))
        return True

    monkeypatch.setattr(bot, "telegram_call", fake_telegram_call)
    base = {"from": {"id": 123}, "chat": {"id": 123, "type": "private"}}
    asyncio.run(bot.process_message(object(), {**base, "message_id": 1, "text": "پاک‌کردن حافظه"}))
    assert bot.load_history(123)[0]["content"] == "keep until confirmed"
    assert calls[-1][1]["reply_markup"] == bot.CLEAR_CONFIRM_MARKUP
    asyncio.run(bot.process_message(object(), {**base, "message_id": 2, "text": "تأیید پاک‌کردن"}))
    assert bot.load_history(123) == []
    assert calls[-1][1]["reply_markup"] == bot.MAIN_MENU_MARKUP
