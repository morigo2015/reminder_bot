# pillsbot/tests/unit/test_measurements_flow.py
import os
from datetime import UTC, datetime

from pillsbot.core.reminder_engine import ReminderEngine, IncomingMessage
from pillsbot import config as cfg


class FakeAdapter:
    def __init__(self):
        self.sent = []  # (kind, id, text, *extra)

    async def send_group_message(self, group_id, text, reply_markup=None):
        self.sent.append(("group", group_id, text))

    async def send_menu_message(self, group_id, text, *, can_confirm: bool):
        self.sent.append(("menu", group_id, text, can_confirm))

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
    _cleanup_csvs(tmp_suffix)

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
        MEASURES = {}
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

    Cfg.MEASURES = MEASURES

    eng = ReminderEngine(Cfg, FakeAdapter())
    return eng


import pytest


@pytest.mark.asyncio
async def test_measurement_ack_and_csv():
    eng = make_engine(tmp_suffix="flow1")
    await eng.start(NoOpScheduler())
    msg = IncomingMessage(
        group_id=-100,
        sender_user_id=100,
        text="BP 120/80",
        sent_at_utc=datetime.now(UTC),
    )
    await eng.on_patient_message(msg)
    assert any("Записав тиск" in t for _, _, t, *rest in eng.adapter.sent)


@pytest.mark.asyncio
async def test_daily_missing_then_ok():
    eng = make_engine(tmp_suffix="flow2")
    await eng.start(NoOpScheduler())

    await eng._job_measure_check(patient_id=100, measure_id="pressure")
    assert any("Не вдалося розпізнати" in t for _, _, t, *rest in eng.adapter.sent)
    eng.adapter.sent.clear()

    msg = IncomingMessage(
        group_id=-100,
        sender_user_id=100,
        text="pressure 120 80",
        sent_at_utc=datetime.now(UTC),
    )
    await eng.on_patient_message(msg)
    assert any("Записав тиск" in t for _, _, t, *rest in eng.adapter.sent)

    before = len(eng.adapter.sent)
    await eng._job_measure_check(patient_id=100, measure_id="pressure")
    after = len(eng.adapter.sent)
    assert before == after
