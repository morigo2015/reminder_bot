# pillsbot/tests/test_adapter_flow.py
import pytest
from unittest.mock import AsyncMock, Mock
from pillsbot.adapters.telegram_adapter import TelegramAdapter


@pytest.mark.asyncio
async def test_on_group_text_forwards_to_engine(monkeypatch):
    # Patch aiogram.Bot to avoid network/token validation
    class DummyBot:
        def __init__(self, *a, **k):
            pass

    # Fake Dispatcher with non-async register methods to avoid warnings
    class DummyDispatcher:
        def __init__(self):
            self.message = Mock()
            self.callback_query = Mock()

        def start_polling(self, bot):
            pass

    monkeypatch.setattr("pillsbot.adapters.telegram_adapter.Bot", DummyBot)
    monkeypatch.setattr(
        "pillsbot.adapters.telegram_adapter.Dispatcher", DummyDispatcher
    )

    mock_engine = AsyncMock()
    adapter = TelegramAdapter(
        "123456:ABCDEF-test", engine=mock_engine, patient_groups=[-100]
    )

    msg = type("M", (), {})()
    msg.chat = type("C", (), {"id": -100})()
    msg.text = "hi"
    msg.from_user = type("U", (), {"id": 1})()

    await adapter.on_group_text(msg)
    assert mock_engine.on_patient_message.await_count == 1
