# LLM Context for Reminder Bot

This file provides structured context for language models to quickly understand, navigate, and work with the Reminder Bot project.

> **Placement**: Place this file in the project root directory alongside `bot.py`, `events.py`, etc.

---

## 1. Project Overview

- **Purpose**: A Telegram bot to schedule medication reminders for patients, track confirmations, retry if no response, and escalate to a nurse after final retry.
- **Primary Workflow**:
  1. Scheduler triggers an `Event` at specified time (Europe/Kyiv TZ).
  2. Bot sends reminder message defined in `events.py`.
  3. Waits for user to reply with the `event_name` in any text.
  4. On confirmation: cancel retries, log `CONFIRMED`.
  5. On no response: send retry messages up to `retries` count.
  6. After final retry: log `FAILED` and send escalation message to nurse.

---

## 2. Core Modules and Responsibilities

| File                           | Role                                                                         | Key Imports/Dependencies                                         |
| ------------------------------ | ---------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| `bot.py`                       | Entry point: initialize Bot, Dispatcher, Scheduler; start polling            | `aiogram`, `scheduler.create_scheduler`, `events`, `handlers`    |
| `events.py`                    | Defines static list of `Event` objects with schedule and messages            | `models.Event`                                                   |
| `models.py`                    | Data classes: `Event` and `RuntimeState`                                     | `dataclasses`                                                    |
| `scheduler.py`                 | Configure APScheduler (cron triggers) and register jobs                      | `apscheduler.schedulers.asyncio.AsyncIOScheduler`, `CronTrigger` |
| `services/reminder_manager.py` | Orchestrates initial reminders, retry logic, confirmation state, and logging | `apscheduler`, `utils.time`, `utils.logging`, `escalation`       |
| `services/escalation.py`       | Sends escalation message to nurse with timestamp                             | `aiogram.Bot`, `datetime`, `utils.logging`                       |
| `handlers/confirmation.py`     | Handler for user confirmation replies; marks events confirmed                | `aiogram.Router`, `services.reminder_manager._STATE`             |
| `handlers/common.py`           | Fallback handler for unrecognized messages                                   | `aiogram.Router`                                                 |
| `utils/time.py`                | Timezone helpers (`kyiv_now()`, `to_server_tz`)                              | `zoneinfo`, `datetime`                                           |
| `utils/logging.py`             | Logs reminder outcomes (`CONFIRMED`, `FAILED`, `ESCALATED`) to CSV           | `csv`, `datetime`, `pathlib`                                     |

---

## 3. File Relationship Map

```
bot.py
 ├─ imports events.py -> Event definitions
 ├─ imports scheduler.py -> APScheduler setup
 │    └─ scheduler.py imports reminder_manager -> uses AsyncIOScheduler
 ├─ creates ReminderManager
 │    ├─ services/reminder_manager.py
 │    │    ├─ uses utils/time.py for scheduling
 │    │    ├─ uses utils/logging.py for CSV logs
 │    │    └─ uses services/escalation.py for nurse alerts
 ├─ sets up handlers:
 │    ├─ handlers/confirmation.py -> marks confirmations via reminder_manager._STATE
 │    └─ handlers/common.py -> fallback replies
 └─ starts scheduler and polling
```

---

## 4. Runtime Flow Summary

1. **Start**: `bot.py` loads modules, builds scheduler, starts polling.
2. **Trigger**: APScheduler fires `trigger_event(event)` -> send `main_message`.
3. **Await**: in-memory `_STATE` tracks attempts (0).
4. **Confirmation**:
   - User reply with `event_name` → `mark_confirmed()`, cancel retry, log.
5. **Retries**:
   - After `retry_delay_seconds`, `handle_retry()` sends `retry_message`.
   - Repeat until `attempt == retries`.
6. **Escalation**:
   - On final retry expiration, log `FAILED` and call `escalation.escalate()`.
   - Nurse receives message with timestamp.

---

## 5. Key Data Models

```python
@dataclass(frozen=True)
class Event:
    event_name: str
    chat_id: int
    scheduler_args: dict      # passed to CronTrigger (e.g., {'hour': 9, 'minute': 0})
    main_message: str
    retry_message: str
    retries: int
    retry_delay_seconds: int
    escalate: bool = True

@dataclass
class RuntimeState:
    attempt: int = 0
    confirmed: bool = False
    retry_job_id: Optional[str] = None
```


## 6. Known Limitations & Assumptions

- **In-Memory State**: Restarting the bot resets all pending reminders.
- **Polling Mode**: No webhook support; uses long polling.
- **Single Nurse**: `NURSE_CHAT_ID` is global; no per-patient nurse assignment.
- **Static Scheduling**: Events cannot be edited at runtime.

