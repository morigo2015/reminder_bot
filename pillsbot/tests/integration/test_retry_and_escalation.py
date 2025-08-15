# pillsbot/tests/integration/test_retry_and_escalation.py
import asyncio
import pytest
from datetime import datetime, timedelta

from pillsbot.core.reminder_engine import ReminderEngine
from pillsbot import config as cfg


class FakeAdapter:
    def __init__(self):
        self.sent = []  # tuples like ("group"|"menu"|"dm", id, text, *extra)

    async def send_group_message(self, group_id, text, reply_markup=None):
        self.sent.append(("group", group_id, text))

    async def send_menu_message(self, group_id, text, *, can_confirm: bool):
        self.sent.append(("menu", group_id, text, can_confirm))

    async def send_nurse_dm(self, user_id, text):
        self.sent.append(("dm", user_id, text))


class NoOpScheduler:
    def __init__(self): ...
    def add_job(self, *args, **kwargs): ...


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
async def test_retry_and_escalation_sends_nurse_notice():
    eng = make_engine(interval=0.05, max_attempts=2)
    await eng.start(NoOpScheduler())

    async def _send_escalation(inst):
        await eng.adapter.send_nurse_dm(inst.nurse_user_id, "ESCALATED")
    eng.messenger.send_escalation = _send_escalation  # type: ignore

    dose_key = list(eng.state.keys())[0]
    await eng._start_dose_job(patient_id=dose_key.patient_id, time_str=dose_key.time_str)
    await asyncio.sleep(0.25)

    assert any(kind == "dm" and text == "ESCALATED" for (kind, _, text, *_) in eng.adapter.sent)
