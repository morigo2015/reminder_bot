import asyncio
import pytest
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from pillsbot.core.reminder_engine import ReminderEngine, IncomingMessage
from pillsbot import config as cfg

class FakeAdapter:
    def __init__(self):
        self.sent = []

    async def send_group_message(self, group_id, text):
        self.sent.append(("group", group_id, text))

    async def send_nurse_dm(self, user_id, text):
        self.sent.append(("dm", user_id, text))

class NoOpScheduler:
    def __init__(self): pass
    def add_job(self, *args, **kwargs): pass

def make_engine(interval=0.05, max_attempts=2):
    now = datetime.now(cfg.TZ)
    dose_time = (now + timedelta(seconds=0.1)).strftime("%H:%M")
    class Cfg:
        TZ = cfg.TZ
        LOG_FILE = cfg.LOG_FILE
        CONFIRM_PATTERNS = cfg.CONFIRM_PATTERNS
        RETRY_INTERVAL_S = interval
        MAX_RETRY_ATTEMPTS = max_attempts
        TAKING_GRACE_INTERVAL_S = 0
        PATIENTS = [{
            "patient_id": 10,
            "patient_label": "P",
            "group_id": -10,
            "nurse_user_id": 20,
            "doses": [{"time": dose_time, "text": "X"}],
        }]
    eng = ReminderEngine(Cfg, FakeAdapter())
    return eng

@pytest.mark.asyncio
async def test_retry_and_escalation():
    eng = make_engine(interval=0.05, max_attempts=2)
    await eng.start(NoOpScheduler())
    # Manually trigger the job (simulate scheduler firing)
    await eng._start_dose_job(patient_id=10, time_str=list(eng.state.keys())[0].time_str)
    # Wait enough for retries + escalation
    await asyncio.sleep(0.2)
    # Check an escalation happened
    assert any(kind=="dm" for (kind, _, _) in eng.adapter.sent)
