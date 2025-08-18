# app/main.py
import asyncio
import os
import sys
from typing import Optional, List

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.types import Message

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from . import config
from .policies import handle_timer_fired, handle_user_message
from .utils import dbg

router = Router()

# Global scheduler reference for /status
SCHEDULER: Optional[AsyncIOScheduler] = None

# Track unknown users we've already notified (runtime only; resets on restart)
_ONBOARD_FEEDBACK_SENT_USER_IDS: set[int] = set()

def _patient_id_for_user(tg_user_id: int) -> Optional[int]:
    for pid, p in config.PATIENTS.items():
        if p.get("tg_user_id") == tg_user_id:
            return pid
    return None

async def _handle_unknown_user_message(msg: Message) -> None:
    """
    Send a one-time onboarding feedback if feature flag is on.
    """
    if not config.FEATURE_ONBOARD_FEEDBACK:
        return
    if msg.from_user and msg.from_user.id not in _ONBOARD_FEEDBACK_SENT_USER_IDS:
        _ONBOARD_FEEDBACK_SENT_USER_IDS.add(msg.from_user.id)
        await msg.answer("Вас не знайдено в списку пацієнтів")
        dbg(f"Onboarding feedback sent to unknown user_id={msg.from_user.id}")

@router.message(Command("status"))
async def on_status(msg: Message):
    """
    /status: PoC-lite observability
    - TZ
    - Scheduler status
    - Number of scheduled jobs
    - Last 3 CSV entries
    """
    tz_str = getattr(config.TZ, "key", str(config.TZ))
    sched_status = "unknown"
    jobs_count = 0
    if SCHEDULER:
        try:
            # Try common attributes across APScheduler versions
            if hasattr(SCHEDULER, "running"):
                sched_status = "running" if SCHEDULER.running else "stopped"
            elif hasattr(SCHEDULER, "state"):
                state = getattr(SCHEDULER, "state")
                sched_status = {0: "stopped", 1: "running", 2: "paused"}.get(state, "unknown")
            jobs_count = len(SCHEDULER.get_jobs())
        except Exception as e:
            sched_status = f"error: {e}"

    tail = _tail_csv_events(3)
    lines = [
        f"TZ: {tz_str}",
        f"Scheduler: {sched_status}",
        f"Jobs scheduled: {jobs_count}",
        "Last log entries:" if tail else "Last log entries: —",
        *tail
    ]
    await msg.answer("\n".join(lines))

def _tail_csv_events(n: int) -> List[str]:
    """
    Return last n event rows (semicolon-separated) from the most recent events_*.csv file.
    """
    try:
        files = [f for f in os.listdir(config.LOG_DIR) if f.startswith("events_") and f.endswith(".csv")]
        if not files:
            return []
        files.sort()  # events_YYYY-MM-DD.csv — lexicographic sort works
        latest = os.path.join(config.LOG_DIR, files[-1])
        with open(latest, "r", encoding="utf-8") as f:
            rows = [line.strip() for line in f if line.strip()]
        if len(rows) <= 1:
            return []
        data = rows[1:]  # skip header
        return data[-n:]
    except Exception as e:
        dbg(f"/status tail read failed: {e}")
        return []

@router.message(F.photo)
async def on_photo(msg: Message):
    pid = _patient_id_for_user(msg.from_user.id)
    if pid is None:
        await _handle_unknown_user_message(msg)
        return
    file_id = msg.photo[-1].file_id if msg.photo else None
    await handle_user_message(bot=msg.bot, patient_id=pid, photo_file_id=file_id)

@router.message(F.voice)
async def on_voice(msg: Message):
    pid = _patient_id_for_user(msg.from_user.id)
    if pid is None:
        await _handle_unknown_user_message(msg)
        return
    await msg.answer("Будь ласка, напишіть коротко текстом.")

@router.message(F.text)
async def on_text(msg: Message):
    pid = _patient_id_for_user(msg.from_user.id)
    if pid is None:
        await _handle_unknown_user_message(msg)
        return
    await handle_user_message(bot=msg.bot, patient_id=pid, text=msg.text or "")

def _fail_fast_config():
    problems = []
    if not config.BOT_TOKEN:
        problems.append("BOT_TOKEN is empty in app/config.py")
    if not isinstance(config.CARE_GIVER_CHAT_ID, int) or config.CARE_GIVER_CHAT_ID == 0:
        problems.append("CARE_GIVER_CHAT_ID is not set to a valid Telegram chat id (negative int for groups)")
    if not config.PATIENTS:
        problems.append("PATIENTS is empty; add at least one patient with 'tg_user_id'")
    if problems:
        print("Configuration errors:\n - " + "\n - ".join(problems), file=sys.stderr)
        sys.exit(2)

def _seed_jobs(scheduler: AsyncIOScheduler, bot: Bot):
    # Meds
    for m in config.MEDS:
        jid = config.job_id_for_med(m["patient_id"], m["med_id"])
        sched = m["schedule"]
        if sched.get("type") != "cron":
            raise ValueError("Only 'cron' schedules are supported in PoC")
        trig = CronTrigger(hour=sched["hour"], minute=sched["minute"], timezone=config.TZ)
        scheduler.add_job(
            handle_timer_fired,
            trigger=trig,
            id=jid,
            replace_existing=True,
            kwargs=dict(
                bot=bot, scheduler=scheduler,
                kind="med_due",
                patient_id=m["patient_id"], med_id=m["med_id"],
                med_name=m["name"], dose=m["dose"],
                scheduled_due_at=None,  # default to now in handler
            ),
        )
        dbg(f"Seeded job {jid} (med) at {sched['hour']:02d}:{sched['minute']:02d} TZ={getattr(config.TZ, 'key', str(config.TZ))}")
    # Measurements
    for meas in config.MEASURES:
        jid = config.job_id_for_measure(meas["patient_id"], meas["kind"])
        sched = meas["schedule"]
        if sched.get("type") != "cron":
            raise ValueError("Only 'cron' schedules are supported in PoC")
        trig = CronTrigger(hour=sched["hour"], minute=sched["minute"], timezone=config.TZ)
        scheduler.add_job(
            handle_timer_fired,
            trigger=trig,
            id=jid,
            replace_existing=True,
            kwargs=dict(
                bot=bot, scheduler=scheduler,
                kind="measure_due",
                patient_id=meas["patient_id"], measure_kind=meas["kind"]
            ),
        )
        dbg(f"Seeded job {jid} (measure:{meas['kind']}) at {sched['hour']:02d}:{sched['minute']:02d} TZ={getattr(config.TZ, 'key', str(config.TZ))}")

async def main():
    _fail_fast_config()

    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    scheduler = AsyncIOScheduler(timezone=config.TZ)
    _seed_jobs(scheduler, bot)
    scheduler.start()

    # Expose scheduler for /status
    global SCHEDULER
    SCHEDULER = scheduler

    dbg("Bot take-off:")
    dbg(f"  TZ = {getattr(config.TZ, 'key', str(config.TZ))}")
    dbg(f"  DEBUG_MODE = {config.DEBUG_MODE}")
    dbg(f"  Patients = {len(config.PATIENTS)}")
    dbg(f"  Meds scheduled = {len(config.MEDS)}")
    dbg(f"  Measures scheduled = {len(config.MEASURES)}")

    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
