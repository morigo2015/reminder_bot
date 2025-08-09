# Pill-Reminder Bot — Codebase Overview

This repository implements the Telegram pill-reminder bot per the provided specs.

**Quick start**

1) Create and activate a Python 3.11+ virtual environment.
2) `pip install -r requirements.txt`
3) Set the bot token (choose ONE):
   - Put it in `pillsbot/config.py` as `BOT_TOKEN = "123:ABC"` **OR**
   - Export env var: `export BOT_TOKEN=123:ABC` and leave `BOT_TOKEN = None` in config.
4) Run: `python -m pillsbot.app`

**Testing**
- `pytest -q` runs unit and integration tests (the integration tests use a fake adapter, no network).

**Logging**
- Appends to `pillsbot/logs/pills.log`. Ensure the `logs/` dir is writable when running in Docker/CI.

**Structure**

```
pillsbot/
  app.py
  config.py
  adapters/
    telegram_adapter.py
  core/
    reminder_engine.py
    matcher.py
    i18n.py
  logs/
    pills.log
  tests/
    unit/
      test_matcher.py
      test_preconfirm_logic.py
    integration/
      test_retry_and_escalation.py
requirements.txt
pyproject.toml
```

**Notes for developers**

- All human-facing times/logs are **Europe/Kyiv**; server timezone may differ.
- No database; in-memory state only, plus a flat log file.
- aiogram FSM is **not** used; the engine keeps minimal state per dose.
- APScheduler schedules daily dose starts; an internal async retry loop handles repeats & escalation.
- The adapter layer isolates aiogram. The core engine can be tested with a **FakeAdapter** (see tests).

**Extending the codebase**
- Add new locales in `core/i18n.py`.
- Add new matching patterns in `config.py` → `CONFIRM_PATTERNS`.
- To persist to a DB, replace the logger in `core/reminder_engine.py` with a repository layer.
- To support multiple messengers, add more adapters implementing `send_group_message` and `send_nurse_dm` and wire them in `app.py`.
