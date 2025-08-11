# pillsbot/tests/integration/test_measure_unknown_behavior.py
import pytest
from datetime import UTC, datetime
from pillsbot.core.reminder_engine import ReminderEngine, IncomingMessage
from pillsbot import config as cfg


class FakeAdapter:
    def __init__(self):
        self.sent = []  # (kind, id, text)

    async def send_group_message(self, group_id, text):
        self.sent.append(("group", group_id, text))

    async def send_nurse_dm(self, user_id, text):
        self.sent.append(("dm", user_id, text))


class NoOpScheduler:
    def add_job(self, *args, **kwargs):
        pass


def make_engine():
    class Cfg:
        TZ = cfg.TZ
        LOG_FILE = cfg.LOG_FILE
        CONFIRM_PATTERNS = cfg.CONFIRM_PATTERNS
        MEASURES = cfg.MEASURES
        RETRY_INTERVAL_S = 0.05
        MAX_RETRY_ATTEMPTS = 2
        TAKING_GRACE_INTERVAL_S = 60
        PATIENTS = [
            {
                "patient_id": 10,
                "patient_label": "P",
                "group_id": -10,
                "nurse_user_id": 20,
                "doses": [],  # none to avoid confirm effects
            }
        ]

    return ReminderEngine(Cfg, FakeAdapter())


@pytest.mark.asyncio
async def test_unknown_when_not_measure_nor_confirmation():
    eng = make_engine()
    await eng.start(NoOpScheduler())

    msg = IncomingMessage(
        group_id=-10,
        sender_user_id=10,
        text="hello there",
        sent_at_utc=datetime.now(UTC),
    )
    await eng.on_patient_message(msg)

    assert any("невідомий показник" in t for _, _, t in eng.adapter.sent)


@pytest.mark.asyncio
async def test_no_unknown_for_confirmation():
    eng = make_engine()
    await eng.start(NoOpScheduler())

    msg = IncomingMessage(
        group_id=-10, sender_user_id=10, text="ok", sent_at_utc=datetime.now(UTC)
    )
    await eng.on_patient_message(msg)

    # For confirmation with no target doses, engine replies "too_early" instead of measure_unknown
    assert any("ще не на часі" in t for _, _, t in eng.adapter.sent)
    assert all("невідомий показник" not in t for _, _, t in eng.adapter.sent)
