from datetime import datetime, timedelta

from pillsbot.core.reminder_engine import ReminderEngine, IncomingMessage
from pillsbot import config as cfg


class FakeAdapter:
    def __init__(self):
        self.sent = []  # (chat_id, text)

    async def send_group_message(self, group_id, text):
        self.sent.append(("group", group_id, text))

    async def send_nurse_dm(self, user_id, text):
        self.sent.append(("dm", user_id, text))


def make_engine():
    class Cfg:
        TZ = cfg.TZ
        LOG_FILE = cfg.LOG_FILE
        CONFIRM_PATTERNS = cfg.CONFIRM_PATTERNS
        RETRY_INTERVAL_S = 1
        MAX_RETRY_ATTEMPTS = 2
        TAKING_GRACE_INTERVAL_S = 60
        PATIENTS = [
            {
                "patient_id": 1,
                "patient_label": "Test Patient",
                "group_id": -1,
                "nurse_user_id": 2,
                "doses": [
                    {
                        "time": (datetime.now(cfg.TZ) + timedelta(minutes=1)).strftime(
                            "%H:%M"
                        ),
                        "text": "Vit D",
                    }
                ],
            }
        ]

    adapter = FakeAdapter()
    eng = ReminderEngine(Cfg, adapter)
    return eng, adapter


import pytest  # noqa: E402
from datetime import UTC  # noqa: E402


@pytest.mark.asyncio
async def test_preconfirm_within_grace():
    eng, ad = make_engine()
    await eng.start(
        scheduler=type("S", (), {"add_job": lambda *a, **k: None})()
    )  # no-op scheduler
    # Send a confirmation now; next dose is within 60s
    msg = IncomingMessage(
        group_id=-1,
        sender_user_id=1,
        text="ок",
        sent_at_utc=datetime.now(UTC),
    )
    await eng.on_patient_message(msg)
    # Expect preconfirm ack
    assert any("заздалегідь" in t for _, _, t in ad.sent)
