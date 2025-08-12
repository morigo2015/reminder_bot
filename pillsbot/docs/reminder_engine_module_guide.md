# module guide 

**File:** `core/reminder_engine.py`
**Purpose:** Orchestrates pill-taking reminders, confirmations (text + inline buttons), simple daily measurement checks (BP/weight), and escalation. One group chat = one patient (+ nurse + bot). State is in-memory, reset daily; CSV logs are the durable audit.

## Public API

* `async start(scheduler)` – validates config, seeds today’s state, installs cron jobs:

  * Dose jobs: one per (patient, time) → reminder w/ inline confirm, refresh reply keyboard, start retry loop.
  * Measurement checks: optional one per (patient, measure, time) → “missing today” notice.
* `async on_patient_message(IncomingMessage)` – handles patient text:

  1. **Measurement** (start-anchored) → append CSV + ack; else
  2. **Confirmation** (search-anywhere) → confirm/ack or preconfirm within grace; else
  3. **Unknown indicator** reply.
* `async on_inline_confirm(group_id, from_user_id, data)` – validates who pressed; confirms if awaiting/escalated; cancels retry; logs OK; on late confirm DMs nurse; returns dict for ephemeral callback.

## UX details

* **Inline confirm** button lives on reminder & retries.
* **Fixed reply keyboard** is always kept fresh via a dedicated follow-up “keyboard refresh” message (invisible text) right after reminders & retries.
* **Prompts** for “Тиск” / “Вага” use **ForceReply (selective)**.
* All patient-facing replies include either the fixed keyboard or a ForceReply (as appropriate).

## Time/logging/storage

* All times in `Europe/Kyiv`.
* Per-day state; pruning ensures bounded memory.
* Outcome CSV appends: dose datetime, patient id/label, pill text, status, attempts.
* Logging: INFO for user-visible messages; DEBUG for jobs/state/retries.

## Config notes

* `INLINE_CONFIRM_ENABLED` (bool, default `True`) can disable inline buttons; the engine will still refresh the reply keyboard for UX.

