# pillsbot/tests/unit/test_hint_expectation.py
import pytest
from datetime import UTC, datetime
from pillsbot.core.reminder_engine import ReminderEngine, IncomingMessage, DoseKey, Status
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


def _mk_msg(group_id, user_id, text):
    return IncomingMessage(
        group_id=group_id,
        sender_user_id=user_id,
        text=text,
        sent_at_utc=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_hint_then_next_message_is_parsed():
    eng = ReminderEngine(cfg, adapter=FakeAdapter())
    await eng.start(None)

    patient = list(eng.patient_index.values())[0]
    gid = patient["group_id"]
    uid = patient["patient_id"]

    await eng.show_hint_menu(gid, kind="pressure")

    await eng.on_patient_message(_mk_msg(gid, uid, "120 80 72"))
    assert any("пульс 72" in t for _, _, t, *rest in eng.adapter.sent)


@pytest.mark.asyncio
async def test_confirmation_takes_precedence_over_hint_expectation():
    eng = ReminderEngine(cfg, adapter=FakeAdapter())
    await eng.start(None)

    patient = list(eng.patient_index.values())[0]
    gid = patient["group_id"]
    uid = patient["patient_id"]

    key = DoseKey(uid, eng.clock.today_str(), patient["doses"][0]["time"])
    inst = eng.state_mgr.get(key)
    eng.state_mgr.set_status(inst, Status.AWAITING)

    await eng.show_hint_menu(gid, kind="pressure")

    await eng.on_patient_message(_mk_msg(gid, uid, "так"))

    assert eng.state_mgr.status(inst) == Status.CONFIRMED
    assert any("Готово! Прийом зафіксовано" in t for _, _, t, *rest in eng.adapter.sent)


@pytest.mark.asyncio
async def test_help_takes_precedence_over_hint_expectation():
    eng = ReminderEngine(cfg, adapter=FakeAdapter())
    await eng.start(None)

    patient = list(eng.patient_index.values())[0]
    gid = patient["group_id"]
    uid = patient["patient_id"]

    await eng.show_hint_menu(gid, kind="weight")
    await eng.on_patient_message(_mk_msg(gid, uid, "help"))

    assert any("Доступні вимірювання: тиск, вага" in t for _, _, t, *rest in eng.adapter.sent)
