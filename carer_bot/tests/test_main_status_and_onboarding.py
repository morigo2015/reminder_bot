# tests/test_main_status_and_onboarding.py
import os
import pytest
from types import SimpleNamespace
from app.main import on_status, _handle_unknown_user_message, _tail_csv_events
from app import config

class DummyChat:
    def __init__(self):
        self.replies = []
    async def answer(self, text):
        self.replies.append(text)

@pytest.mark.asyncio
async def test_status_outputs(monkeypatch):
    os.makedirs(config.LOG_DIR, exist_ok=True)
    p = os.path.join(config.LOG_DIR, "events_2099-01-01.csv")
    with open(p, "w", encoding="utf-8") as f:
        f.write("hdr\nrow1\nrow2\nrow3\nrow4\n")
    dummy = DummyChat()
    msg = SimpleNamespace(answer=dummy.answer)
    await on_status(msg)
    assert len(dummy.replies) == 1
    assert "TZ:" in dummy.replies[0]

def test_tail_reads_last_three():
    os.makedirs(config.LOG_DIR, exist_ok=True)
    path = os.path.join(config.LOG_DIR, "events_2099-01-02.csv")
    with open(path, "w", encoding="utf-8") as f:
        f.write("hdr\nr1\nr2\nr3\nr4\n")
    rows = _tail_csv_events(3)
    assert rows == ["r2", "r3", "r4"]

@pytest.mark.asyncio
async def test_onboarding_feedback_once(monkeypatch):
    sent = []
    class TempMsg:
        from_user = SimpleNamespace(id=999)
        async def answer(self, text):
            sent.append(text)
    await _handle_unknown_user_message(TempMsg())
    await _handle_unknown_user_message(TempMsg())
    assert sent.count("Вас не знайдено в списку пацієнтів") == 1
