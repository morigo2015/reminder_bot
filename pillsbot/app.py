# pillsbot/app.py
from __future__ import annotations

import sys
from pathlib import Path
import asyncio
import logging
from typing import List, Tuple, Dict, Any
from datetime import datetime

# --------------------------------------------------------------------------------------
# Ensure project root is in sys.path so "import pillsbot.*" always works
# --------------------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import config as cfg  # noqa: E402
from config import get_bot_token, PATIENTS  # noqa: E402
from pillsbot.core.reminder_engine import ReminderEngine  # noqa: E402
from pillsbot.adapters.telegram_adapter import TelegramAdapter  # noqa: E402
from apscheduler.schedulers.asyncio import AsyncIOScheduler  # noqa: E402
from pillsbot.core.i18n import MESSAGES  # noqa: E402


def _now_hhmm(tz) -> str:
    """Return current local time in HH:MM for a given tzinfo."""
    return datetime.now(tz).strftime("%H:%M")


async def schedule_jobs(
    engine: ReminderEngine, timezone
) -> Tuple[AsyncIOScheduler, List[Tuple[int, str]]]:
    """
    Schedule daily dose reminders and (optionally) measurement checks from config.

    Returns (scheduler, immediate_doses) where immediate_doses is a list of (patient_id, '*')
    that must be triggered exactly once after startup.

    Note: The scheduler is created and configured here, but NOT started.
    """
    sched = AsyncIOScheduler(timezone=timezone)

    immediate: List[Tuple[int, str]] = []

    # Doses
    for p in PATIENTS:
        pid = p["patient_id"]
        for d in p["doses"]:
            t = d["time"]
            if t == "*":
                immediate.append((pid, t))
                continue
            hh, mm = (int(x) for x in t.split(":"))
            sched.add_job(
                engine._start_dose_job,  # async function
                trigger="cron",
                hour=hh,
                minute=mm,
                kwargs={"patient_id": pid, "time_str": t},
                id=f"dose:{pid}:{t}",
                replace_existing=True,
                coalesce=True,
                misfire_grace_time=300,
                max_instances=1,
            )

    # Measurement checks — robustly resolve the job function
    target = getattr(engine, "_start_measurement_check_job", None)
    if target is None:
        # v4/v5 canonical name
        target = getattr(engine, "_job_measure_check", None)

    if target:
        for p in PATIENTS:
            pid = p["patient_id"]
            for chk in p.get("measurement_checks", []):
                t = chk["time"]
                hh, mm = (int(x) for x in t.split(":"))
                sched.add_job(
                    target,
                    trigger="cron",
                    hour=hh,
                    minute=mm,
                    kwargs={"patient_id": pid, "measure_id": chk["measure_id"]},
                    id=f"measure:{pid}:{chk['measure_id']}:{t}",
                    replace_existing=True,
                    coalesce=True,
                    misfire_grace_time=300,
                    max_instances=1,
                )

    return sched, immediate


def _patients_with_star_replaced(
    patients: List[Dict[str, Any]], hhmm: str
) -> List[Dict[str, Any]]:
    """
    Return a shallow-copied PATIENTS where any dose with time=='*' is replaced by HH:MM.
    This guarantees engine/state initialization pre-creates today's instances.
    """
    result: List[Dict[str, Any]] = []
    for p in patients:
        newp = dict(p)
        new_doses: List[Dict[str, Any]] = []
        for d in p.get("doses", []):
            if d.get("time") == "*":
                d = dict(d)
                d["time"] = hhmm
            new_doses.append(d)
        newp["doses"] = new_doses
        result.append(newp)
    return result


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    log = logging.getLogger("pillsbot.app")

    token = get_bot_token()

    # Break constructor cycle: adapter needs engine, engine needs adapter
    adapter = TelegramAdapter(
        bot_token=token,
        engine=None,  # placeholder; set real engine below
        patient_groups=[p["group_id"] for p in PATIENTS],
    )

    engine = ReminderEngine(config=cfg, adapter=adapter)

    # Attach engine back to adapter
    if hasattr(adapter, "attach_engine"):
        adapter.attach_engine(engine)
    else:
        adapter.engine = engine  # type: ignore[attr-defined]

    # Prepare scheduler and register jobs (do not start yet)
    sched, immediate = await schedule_jobs(engine, timezone=cfg.TZ)

    # Compute a single HH:MM substitute for all '*' doses at this startup
    now_hhmm = _now_hhmm(cfg.TZ)

    # Temporarily replace '*' with now_hhmm so engine/state pre-creates instances
    original_patients = cfg.PATIENTS
    try:
        cfg.PATIENTS = _patients_with_star_replaced(original_patients, now_hhmm)
        # Initialize engine (explicitly disable any legacy scheduler passthrough)
        await engine.start(scheduler=None)
    finally:
        cfg.PATIENTS = original_patients

    # --- IMPORTANT ORDER ---
    # 1) Startup greeting (one per group) BEFORE any reminders can publish
    for p in PATIENTS:
        await adapter.send_group_message(p["group_id"], MESSAGES["startup_greeting"])

    # 2) Trigger one-shot '*' doses immediately (use the same HH:MM as during init)
    for pid, _ in immediate:
        await engine._start_dose_job(patient_id=pid, time_str=now_hhmm)

    # 3) Only now start the scheduler
    sched.start()

    log.info("startup.ready patients=%d", len(PATIENTS))

    # Enter polling loop
    await adapter.run_polling()


if __name__ == "__main__":
    asyncio.run(main())
