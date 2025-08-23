# Carer Bot (Minimal)

Python 3.11+, aiogram 3, MySQL. Single process with Ticker (60s) and Sweeper (5m).

## Setup

1. Create DB and apply schema:

   ```sql
   CREATE DATABASE carer CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

Then run `db/schema.sql` against it.

2. Edit `app/config.py`: BOT_TOKEN, NURSE_CHAT_ID, DB creds, PATIENTS list.

3. Install deps:

   ```bash
   python -m venv .venv && source .venv/bin/activate
   pip install -r app/requirements.txt
   ```

4. Run:

   ```bash
   PYTHONPATH=. python -m app.main
   ```

## Notes

* At-least-once send: initial reminder is **sent before** upsert; duplicates are OK.
* Repeat is sent once per day per dose (in-memory flag). Escalation handled by Sweeper.
* All timestamps stored in UTC; local date/time uses Europe/Kyiv.
* Nurse chat is a single private chat ID from config.
* Text confirmations map to the latest unconfirmed pill (today, else previous day).

```

####
