# pillsbot/tests/test_inline_confirm.py
import pytest
from pillsbot.core.reminder_engine import ReminderEngine, DoseKey, Status
import pillsbot.config as cfg
from pillsbot.core.i18n import fmt  # import the i18n formatter


@pytest.mark.asyncio
async def test_inline_confirm_falls_back_to_selection():
    eng = ReminderEngine(cfg, adapter=None)
    await eng.start(None)

    patient = list(eng.patient_index.values())[0]
    key = DoseKey(patient["patient_id"], eng._today_str(), patient["doses"][0]["time"])
    inst = eng.state_mgr.get(key)
    eng.state_mgr.set_status(inst, Status.AWAITING)

    result = await eng.on_inline_confirm(
        group_id=patient["group_id"],
        from_user_id=patient["patient_id"],
        data="confirm:999:2020-01-01:00:00",  # invalid key to force fallback
        message_id=None,
    )

    assert fmt("cb_late_ok") in result["cb_text"]
    assert eng.state_mgr.status(inst) == Status.CONFIRMED
