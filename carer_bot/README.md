# Care Companion Bot (PoC)

Simple Telegram “care companion”:
- Reminds about meds & routine measurements
- Confirms via text or photo-in-window
- Logs CSV events (Kyiv time)
- Nags (+30m, +90m, +24h), then escalates missed dose to caregiver group
- Immediate caregiver alerts: Temp ≥ 38.5°C, BP ≥ 180/110
- Extendable scenario-based design (no FSM)
- **/status** command for quick field diagnostics (TZ, scheduler, jobs count, last 3 log entries)
- **DEBUG_MODE** to shorten nag intervals (seconds) and print detailed debug traces

## Quick start

1) **Python 3.11+** is required.

2) Create venv & install deps:
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

3) Open `app/config.py` and set:
- `BOT_TOKEN` — your Telegram bot token (from @BotFather)
- `PATIENTS` — map patient -> Telegram user id
- `CARE_GIVER_CHAT_ID` — Telegram chat id of your caregiver group (negative int for supergroup)

4) Run:
```bash
python -m app.main
```

Logs appear under `./logs/` (CSV, local Kyiv timestamps).

### Debug / field testing

- Toggle `DEBUG_MODE = True` in `app/config.py` to:
  - Use short nag delays from `DEBUG_NAG_SECONDS` (e.g., 10s, 30s, 90s)
  - Print debug messages: take-off, job seeding, timer fires, classifier decisions, nags, escalations, etc.
- `/status` command summarizes TZ, scheduler state, job count, and last 3 CSV entries.

> Notes
> - Timezone is fixed to Europe/Kyiv by design (per spec).
> - This PoC keeps state in RAM and uses APScheduler in-memory jobstore.
> - Add more meds/measurements in `config.py` (one cron job per item).
