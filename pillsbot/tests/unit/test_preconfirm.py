# pillsbot/tests/unit/test_preconfirm.py
import pytest
from datetime import UTC, datetime
from pillsbot.core.reminder_engine import ReminderEngine, IncomingMessage
import pillsbot.config as cfg


class FakeAdapter:
    def __init__(self):
        self.sent = []

    async def send_group_message(self, group_id, text, reply_markup=None):
        self.sent.append(("group", group_id, text))

    async def send_menu_message(self, group_id, text, *, can_confirm: bool):
        self.sent.append(("menu", group_id, text, can_confirm))

    async def send_nurse_dm(self, user_id, text):
        self.sent.append(("dm", user_id, text))


@pytest.mark.asyncio
async def test_confirmation_without_awaiting_is_unknown():
    eng = ReminderEngine(cfg, adapter=FakeAdapter())
    await eng.start(None)

    msg = IncomingMessage(
        group_id=cfg.PATIENTS[0]["group_id"],
        sender_user_id=cfg.PATIENTS[0]["patient_id"],
        text="так",
        sent_at_utc=datetime.now(UTC),
    )
    await eng.on_patient_message(msg)

    assert any("Не вдалося розпізнати" in t for _, _, t, *rest in eng.adapter.sent)
