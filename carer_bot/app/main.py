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
from .policies import (
    handle_timer_fired,
    handle_user_message,
    emit_config_digest_on_startup,
)
from .utils import dbg
from . import prompts

router = Router()

# Global scheduler reference for /status
SCHEDULER: Optional[AsyncIOScheduler] = None


def _patient_id_for_group(chat_id: int) -> Optional[int]:
    for pid, p in config.PATIENTS.items():
        if p.get("group_chat_id") == chat_id:
            return pid
    return None


def _patient_user_id(pid: int) -> Optional[int]:
    return config.PATIENTS.get(pid, {}).get("patient_user_id")


async def _warn_not_patient(msg: Message, pid: int) -> None:
    name = config.PATIENTS.get(pid, {}).get("name", "пацієнт")
    await msg.answer(prompts.only_patient_can_write(name))


@router.message(Command("status"))
async def on_status(msg: Message):
    tz_str = getattr(config.TZ, "key", str(config.TZ))
    sched_status = "unknown"
    jobs_count = 0
    if SCHEDULER:
        try:
            if hasattr(SCHEDULER, "running"):
                sched_status = "running" if SCHEDULER.running else "stopped"
            elif hasattr(SCHEDULER, "state"):
                state = getattr(SCHEDULER, "state")
                sched_status = {0: "stopped", 1: "running", 2: "paused"}.get(
                    state, "unknown"
                )
            jobs_count = len(SCHEDULER.get_jobs())
        except Exception as e:
            sched_status = f"error: {e}"

    tail = _tail_csv_events(3)
    lines = [
        f"TZ: {tz_str}",
        f"Scheduler: {sched_status}",
        f"Jobs scheduled: {jobs_count}",
        "Last log entries:" if tail else "Last log entries: —",
        *tail,
    ]
    await msg.answer("\n".join(lines))


def _tail_csv_events(n: int) -> List[str]:
    """Return last n event rows (semicolon-separated) from the most recent events_*.csv file."""
    try:
        files = [
            f
            for f in os.listdir(config.LOG_DIR)
            if f.startswith("events_") and f.endswith(".csv")
        ]
        if not files:
            return []
        files.sort()
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
    pid = _patient_id_for_group(msg.chat.id)
    if pid is None:
        # Unknown group: ignore silently (PoC)
        return
    # Only patient may send actionable messages
    if (
        msg.from_user
        and not msg.from_user.is_bot
        and msg.from_user.id != _patient_user_id(pid)
    ):
        await _warn_not_patient(msg, pid)
        return
    file_id = msg.photo[-1].file_id if msg.photo else None
    await handle_user_message(
        bot=msg.bot, scheduler=SCHEDULER, patient_id=pid, photo_file_id=file_id
    )


@router.message(F.voice)
async def on_voice(msg: Message):
    pid = _patient_id_for_group(msg.chat.id)
    if pid is None:
        return
    if (
        msg.from_user
        and not msg.from_user.is_bot
        and msg.from_user.id != _patient_user_id(pid)
    ):
        await _warn_not_patient(msg, pid)
        return
    await msg.answer("Будь ласка, напишіть коротко текстом.")


@router.message(F.text)
async def on_text(msg: Message):
    pid = _patient_id_for_group(msg.chat.id)
    if pid is None:
        # Unknown group: ignore silently (PoC)
        return
    if (
        msg.from_user
        and not msg.from_user.is_bot
        and msg.from_user.id != _patient_user_id(pid)
    ):
        await _warn_not_patient(msg, pid)
        return
    await handle_user_message(
        bot=msg.bot, scheduler=SCHEDULER, patient_id=pid, text=msg.text or ""
    )


def _fail_fast_config():
    problems = []
    if not config.BOT_TOKEN:
        problems.append("BOT_TOKEN is empty in app/config.py")
    if not isinstance(config.CARE_GIVER_CHAT_ID, int) or config.CARE_GIVER_CHAT_ID == 0:
        problems.append(
            "CARE_GIVER_CHAT_ID is not set to a valid Telegram chat id (negative int for groups)"
        )
    if not config.PATIENTS:
        problems.append("PATIENTS is empty; add at least one patient")
    for pid, p in config.PATIENTS.items():
        if not p.get("group_chat_id"):
            problems.append(f"patient {pid}: group_chat_id missing")
        if not p.get("patient_user_id"):
            problems.append(f"patient {pid}: patient_user_id missing")
    if problems:
        print("Configuration errors:\n - " + "\n - ".join(problems), file=sys.stderr)
        sys.exit(2)


def _seed_jobs(scheduler: AsyncIOScheduler, bot: Bot):
    # Pills: derive from per-patient pill_times_hhmm; med_id = index position
    for pid, p in config.PATIENTS.items():
        for idx, hhmm in enumerate(p.get("pill_times_hhmm", [])):
            hh, mm = map(int, hhmm.split(":"))
            jid = config.job_id_for_med(pid, idx)
            trig = CronTrigger(hour=hh, minute=mm, timezone=config.TZ)
            scheduler.add_job(
                handle_timer_fired,
                trigger=trig,
                id=jid,
                replace_existing=True,
                kwargs=dict(
                    bot=bot,
                    scheduler=scheduler,
                    kind="med_due",
                    patient_id=pid,
                    med_id=idx,
                    scheduled_due_at=None,  # default to now in handler
                ),
            )
            dbg(
                f"Seeded job {jid} (pill) at {hh:02d}:{mm:02d} TZ={getattr(config.TZ, 'key', str(config.TZ))}"
            )

    # BP measurements: keep PoC-style slots from config.MEASURES
    for meas in config.MEASURES:
        if meas.get("kind") != "bp":
            continue
        jid = config.job_id_for_measure(meas["patient_id"], meas["kind"])
        sched = meas["schedule"]
        if sched.get("type") != "cron":
            raise ValueError("Only 'cron' schedules are supported in PoC")
        trig = CronTrigger(
            hour=sched["hour"], minute=sched["minute"], timezone=config.TZ
        )
        scheduler.add_job(
            handle_timer_fired,
            trigger=trig,
            id=jid,
            replace_existing=True,
            kwargs=dict(
                bot=bot,
                scheduler=scheduler,
                kind="measure_due",
                patient_id=meas["patient_id"],
                measure_kind=meas["kind"],
            ),
        )
        dbg(
            f"Seeded job {jid} (measure:{meas['kind']}) at {sched['hour']:02d}:{sched['minute']:02d} TZ={getattr(config.TZ, 'key', str(config.TZ))}"
        )


async def main():
    _fail_fast_config()

    bot = Bot(token=config.BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    scheduler = AsyncIOScheduler(timezone=config.TZ)
    _seed_jobs(scheduler, bot)
    scheduler.start()

    global SCHEDULER
    SCHEDULER = scheduler

    # Emit config digest rows on startup
    emit_config_digest_on_startup()

    dbg("Bot take-off:")
    dbg(f"  TZ = {getattr(config.TZ, 'key', str(config.TZ))}")
    dbg(f"  DEBUG_MODE = {config.DEBUG_MODE}")
    dbg(f"  Patients = {len(config.PATIENTS)}")
    dbg(
        f"  Pill jobs scheduled = {sum(len(p.get('pill_times_hhmm', [])) for p in config.PATIENTS.values())}"
    )
    dbg(
        f"  BP measure slots scheduled = {len([m for m in config.MEASURES if m.get('kind') == 'bp'])}"
    )

    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
