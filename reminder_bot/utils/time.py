from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

KYIV_TZ = ZoneInfo("Europe/Kyiv")

def kyiv_now() -> datetime:
    """Return now() in Europe/Kyiv."""
    return datetime.now(tz=KYIV_TZ)

def to_server_tz(dt_kyiv: datetime) -> datetime:
    """Convert a Kyiv‑tz datetime to the server's local timezone."""
    return dt_kyiv.astimezone()

def seconds_until(hour: int) -> int:
    """Return seconds until the next occurrence of `hour:00` (Kyiv time)."""
    now = kyiv_now()
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return int((target - now).total_seconds())