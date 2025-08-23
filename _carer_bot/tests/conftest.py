# tests/conftest.py
import asyncio
import os
import sys
import types
import shutil
import tempfile
import pytest

# Ensure project root is on sys.path for 'import app...'
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

@pytest.fixture(autouse=True)
def _isolate_logs_tmpdir(monkeypatch):
    """
    Redirect app.config.LOG_DIR to a temporary folder per test.
    Ensures CSV logs are isolated and writable.
    """
    import app.config as cfg
    tmpdir = tempfile.mkdtemp(prefix="logs_")
    monkeypatch.setattr(cfg, "LOG_DIR", tmpdir, raising=False)
    yield
    shutil.rmtree(tmpdir, ignore_errors=True)

@pytest.fixture(autouse=True)
def _safe_config(monkeypatch):
    """
    Set safe defaults for tests: caregiver chat id negative,
    small patients mapping, and DEBUG_MODE on for fast nag steps.
    """
    import app.config as cfg
    # Provide a fake token to pass fail-fast (not used in tests)
    monkeypatch.setattr(cfg, "BOT_TOKEN", "TEST:TOKEN")
    # Negative id typical for supergroups
    monkeypatch.setattr(cfg, "CARE_GIVER_CHAT_ID", -1001234567890)
    # Test patients
    monkeypatch.setattr(cfg, "PATIENTS", {
        1: {"name": "Марія", "tg_user_id": 11},
        2: {"name": "Олег",  "tg_user_id": 22},
    })
    # Debug mode for quick cycles
    monkeypatch.setattr(cfg, "DEBUG_MODE", True, raising=False)
    monkeypatch.setattr(cfg, "DEBUG_NAG_SECONDS", [1, 2, 3], raising=False)
    yield

class FakeBot:
    """
    Minimal async-compatible bot that stores sent messages.
    """
    def __init__(self):
        self.sent = []  # list of (chat_id, text)

    async def send_message(self, chat_id, text):
        self.sent.append((chat_id, text))
        # Return a minimal object with message_id for CSV logging
        return types.SimpleNamespace(message_id=len(self.sent))

class FakeScheduler:
    """
    Mock scheduler that captures add_job calls without executing them.
    """
    def __init__(self):
        self.jobs = []
    
    def add_job(self, func, trigger=None, id=None, replace_existing=True, kwargs=None):
        self.jobs.append({
            'func': func,
            'trigger': trigger,
            'id': id,
            'replace_existing': replace_existing,
            'kwargs': kwargs or {}
        })

@pytest.fixture
def fake_bot():
    return FakeBot()

@pytest.fixture
def fake_scheduler():
    return FakeScheduler()
