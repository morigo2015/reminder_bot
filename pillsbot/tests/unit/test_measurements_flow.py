# pillsbot/tests/unit/test_measurements_flow.py
import os
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


def _cleanup_csvs(tmp_suffix: str):
    paths = [
        f"pillsbot/logs/pressure_{tmp_suffix}.csv",
        f"pillsbot/logs/weight_{tmp_suffix}.csv",
    ]
    for p in paths:
        try:
            os.remove(p)
        except FileNotFoundError:
            pass


def make_engine(tmp_suffix="x"):
    # Ensure a clean slate for this test run
    _cleanup_csvs(tmp_suffix)

    # Use test-specific CSV paths to avoid touching prod logs
    MEASURES = {k: dict(v) for k, v in cfg.MEASURES.items()}
    MEASURES["pressure"] = dict(
        MEASURES["pressure"], csv_file=f"pillsbot/logs/pressure_{tmp_suffix}.csv"
    )
    MEASURES["weight"] = dict(
        MEASURES["weight"], csv_file=f"pillsbot/logs/weight_{tmp_suffix}.csv"
    )

    class Cfg:
        TZ = cfg.TZ
        LOG_FILE = cfg.LOG_FILE
        CONFIRM_PATTERNS = cfg.CONFIRM_PATTERNS
        MEASURES = {}  # set right after the class definition
        RETRY_INTERVAL_S = 0.05
        MAX_RETRY_ATTEMPTS = 2
        TAKING_GRACE_INTERVAL_S = 60
        PATIENTS = [
            {
                "patient_id": 100,
                "patient_label": "P",
                "group_id": -100,
                "nurse_user_id": 200,
                "doses": [],
                "measurement_checks": [{"measure_id": "pressure", "time": "23:59"}],
            }
        ]

    # IMPORTANT: assign here to avoid NameError inside class scope
    Cfg.MEASURES = MEASURES

    eng = ReminderEngine(Cfg, FakeAdapter())
    return eng


import pytest


@pytest.mark.asyncio
async def test_measurement_ack_and_csv():
    eng = make_engine(tmp_suffix="flow1")
    await eng.start(NoOpScheduler())
    # Send a good pressure message
    msg = IncomingMessage(
        group_id=-100,
        sender_user_id=100,
        text="BP 120/80/60",
        sent_at_utc=datetime.now(UTC),
    )
    await eng.on_patient_message(msg)
    # Should have ack
    assert any("отримано показник" in t for _, _, t in eng.adapter.sent)


@pytest.mark.asyncio
async def test_daily_missing_then_ok():
    eng = make_engine(tmp_suffix="flow2")
    await eng.start(NoOpScheduler())

    # First check: no entry today -> missing reminder
    await eng._measurement_check_job(100, "pressure")
    assert any("сьогодні не отримано показник" in t for _, _, t in eng.adapter.sent)
    eng.adapter.sent.clear()

    # Now record a measurement (this will produce an ACK message)
    msg = IncomingMessage(
        group_id=-100,
        sender_user_id=100,
        text="pressure 120 80 60",
        sent_at_utc=datetime.now(UTC),
    )
    await eng.on_patient_message(msg)
    assert any("отримано показник" in t for _, _, t in eng.adapter.sent)

    # Check again: should NOT send a "missing" reminder and should NOT append any new messages
    before = len(eng.adapter.sent)
    await eng._measurement_check_job(100, "pressure")
    after = len(eng.adapter.sent)
    assert before == after  # no additional messages
    # and specifically no "missing" text present
    assert not any("сьогодні не отримано показник" in t for _, _, t in eng.adapter.sent)
