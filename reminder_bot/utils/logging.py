"""CSV logging utilities for Reminder Bot."""
import csv
from datetime import datetime
from pathlib import Path

# Directory for log files
LOG_DIR = Path(__file__).parent.parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)

def log(event_name: str, chat_id: int, status: str, attempts: int, clarifications: int = 0) -> None:
    """Append a log entry for confirmation/failed events."""
    filepath = LOG_DIR / f"{event_name}.csv"
    first = not filepath.exists()
    with filepath.open('a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if first:
            writer.writerow(['timestamp', 'chat_id', 'event_name', 'status', 'attempts', 'clarifications'])
        timestamp = datetime.now().astimezone().isoformat()
        writer.writerow([timestamp, chat_id, event_name, status, attempts, clarifications])
