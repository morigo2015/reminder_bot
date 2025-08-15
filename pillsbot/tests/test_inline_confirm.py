# pillsbot/tests/test_inline_confirm.py
import pytest
from pillsbot.core.reminder_engine import ReminderEngine, DoseKey, Status
import pillsbot.config as cfg


class FakeAdapter:
    def __init__(self):
        self.sent = []  # (kind, id, text, *extra)

    async def send_group_message(self, group_id, text, reply_markup=None):
        self.sent.append(("group", group_id, text))

    async def send_menu_message(self, group_id, text, *, can_confirm: bool):
        self.sent.append(("menu", group_id, text, can_confirm))

    async def send_nurse_dm(self, user_id, text):
        self.sent.append(("dm", user_id, text))


@pytest.mark.asyncio
async def test_text_confirmation_confirms_when_awaiting():
    eng = ReminderEngine(cfg, adapter=FakeAdapter())
    await eng.start(None)

    patient = list(eng.patient_index.values())[0]
    key = DoseKey(patient["patient_id"], eng.clock.today_str(), patient["doses"][0]["time"])
    inst = eng.state_mgr.get(key)
    eng.state_mgr.set_status(inst, Status.AWAITING)

    from datetime import UTC, datetime as dt
    msg = type("Msg", (), dict(
        group_id=patient["group_id"],
        sender_user_id=patient["patient_id"],
        text="ок",
        sent_at_utc=dt.now(UTC),
    ))()
    await eng.on_patient_message(msg)

    assert eng.state_mgr.status(inst) == Status.CONFIRMED
    assert any("Готово! Зафіксовано" in t for _, _, t, *rest in eng.adapter.sent)
