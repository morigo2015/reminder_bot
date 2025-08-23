# tests/test_policies_unit.py
import asyncio
import pytest
from datetime import datetime
from app import config
from app.policies import (
    handle_timer_fired,
    handle_user_message,
    MED_STATE, MEASURE_STATE,
    _nag_med_if_unconfirmed,
)
KYIV = config.TZ

@pytest.mark.asyncio
async def test_med_text_confirmation_flow(fake_bot, fake_scheduler):
    due_at = datetime.now(KYIV)
    await handle_timer_fired(fake_bot, fake_scheduler,
        kind="med_due", patient_id=1, med_id=42, med_name="A", dose="5", scheduled_due_at=due_at)
    await handle_user_message(fake_bot, patient_id=1, text="так")
    st = MED_STATE[1][42]
    assert st.last_confirm_at is not None
    assert st.nag_count == 0

@pytest.mark.asyncio
async def test_photo_window_confirmation(fake_bot, fake_scheduler):
    due_at = datetime.now(KYIV)
    await handle_timer_fired(fake_bot, fake_scheduler,
        kind="med_due", patient_id=1, med_id=99, med_name="B", dose="10", scheduled_due_at=due_at)
    await handle_user_message(fake_bot, patient_id=1, photo_file_id="photo:1")
    st = MED_STATE[1][99]
    assert st.last_confirm_at is not None

@pytest.mark.asyncio
async def test_measure_alerts(fake_bot, fake_scheduler):
    due_at = datetime.now(KYIV)
    await handle_timer_fired(fake_bot, fake_scheduler, kind="measure_due", patient_id=1, measure_kind="bp", scheduled_due_at=due_at)
    await handle_user_message(fake_bot, patient_id=1, text="181/111")
    await handle_timer_fired(fake_bot, fake_scheduler, kind="measure_due", patient_id=1, measure_kind="temp", scheduled_due_at=due_at)
    await handle_user_message(fake_bot, patient_id=1, text="38.6")
    cg_msgs = [m for m in fake_bot.sent if m[0] == config.CARE_GIVER_CHAT_ID]
    assert len(cg_msgs) >= 2

@pytest.mark.asyncio
async def test_missed_dose_escalation(fake_bot, fake_scheduler):
    due_at = datetime.now(KYIV)
    await handle_timer_fired(fake_bot, fake_scheduler,
        kind="med_due", patient_id=1, med_id=777, med_name="C", dose="1", scheduled_due_at=due_at)
    from app.policies import _nag_deltas
    last_index = len(_nag_deltas())
    await _nag_med_if_unconfirmed(fake_bot, patient_id=1, med_id=777, med_name="C",
                                  scheduled_due_at=due_at, nag_index=last_index)
    cg_msgs = [m for m in fake_bot.sent if m[0] == config.CARE_GIVER_CHAT_ID]
    assert any("Пропуск дози" in text for (_, text) in cg_msgs)
