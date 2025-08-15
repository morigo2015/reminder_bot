# pillsbot/tests/unit/test_adapter_callback_ack.py
import pytest
from unittest.mock import AsyncMock, Mock
from pillsbot.adapters.telegram_adapter import TelegramAdapter


@pytest.mark.asyncio
async def test_on_callback_answers_spinner_and_routes(monkeypatch):
    class DummyBot:
        def __init__(self, *a, **k): ...
        async def send_message(self, *a, **k): return type("M", (), {"message_id": 1})()
        async def delete_message(self, *a, **k): ...

    class DummyDispatcher:
        def __init__(self):
            self.message = Mock()
            self.callback_query = Mock()
        async def start_polling(self, bot): ...

    monkeypatch.setattr("pillsbot.adapters.telegram_adapter.Bot", DummyBot)
    monkeypatch.setattr("pillsbot.adapters.telegram_adapter.Dispatcher", DummyDispatcher)

    engine = AsyncMock()
    adapter = TelegramAdapter("dummy", engine=engine, patient_groups=[-1])

    class _User: id = 1
    class _Chat: id = -1
    class _Msg: chat = _Chat()
    class _CB:
        data = "ui:PRESSURE"
        from_user = _User()
        message = _Msg()
        answered = False
        async def answer(self): self.answered = True

    cb = _CB()
    await adapter.on_callback(cb)

    assert cb.answered is True
    engine.show_hint_menu.assert_awaited_once()
