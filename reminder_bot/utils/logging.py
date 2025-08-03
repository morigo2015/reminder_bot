"""Very simple CSV log helper."""
import csv
from datetime import datetime, timezone
from pathlib import Path

LOG_FILE = Path("logs.csv")
FIELDS = ("timestamp", "event_name", "chat_id", "status", "attempts")

def _ensure_header() -> None:
    if not LOG_FILE.exists():
        LOG_FILE.write_text(",".join(FIELDS) + "\n", encoding="utf‑8")

def log(event_name: str, chat_id: int, status: str, attempts: int) -> None:
    _ensure_header()
    ts_utc = datetime.now(tz=timezone.utc).isoformat()
    row = (ts_utc, event_name, str(chat_id), status, str(attempts))
    with LOG_FILE.open("a", newline="", encoding="utf‑8") as f:
        csv.writer(f).writerow(row)
