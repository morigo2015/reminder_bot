from datetime import datetime
from zoneinfo import ZoneInfo

KYIV_TZ = ZoneInfo("Europe/Kyiv")

def kyiv_now() -> datetime:
    """Return now() in Europe/Kyiv."""
    return datetime.now(tz=KYIV_TZ)

def to_server_tz(dt_kyiv: datetime) -> datetime:
    """Convert a Kyiv‑tz datetime to the server's local timezone."""
    return dt_kyiv.astimezone()
