# tests/test_preconfirm.py
import pytest
from datetime import timedelta
from pillsbot.core.reminder_engine import ReminderEngine, DoseKey, Status
import pillsbot.config as cfg


@pytest.mark.asyncio
async def test_preconfirm_within_grace():
    eng = ReminderEngine(cfg, adapter=None)
    await eng.start(None)

    patient = list(eng.patient_index.values())[0]
    key = DoseKey(patient["patient_id"], eng._today_str(), patient["doses"][0]["time"])
    inst = eng.state_mgr.get(key)
    inst.scheduled_dt_local = eng.clock.now() + timedelta(
        seconds=eng.cfg.TAKING_GRACE_INTERVAL_S - 1
    )

    await eng._handle_confirmation_text(patient)

    assert eng.state_mgr.status(inst) == Status.CONFIRMED
    assert inst.preconfirmed
