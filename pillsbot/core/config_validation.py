# pillsbot/core/config_validation.py
from __future__ import annotations

from typing import Any, Dict, List
import re


_TIME_RE = re.compile(r"^\d{2}:\d{2}$")


def _is_valid_hhmm(s: str) -> bool:
    if not _TIME_RE.match(s):
        return False
    hh, mm = (int(x) for x in s.split(":", 1))
    return 0 <= hh <= 23 and 0 <= mm <= 59


def validate_config(cfg: Any) -> None:
    """Validate runtime configuration before starting the bot.

    v5 changes:
    - Dose time may be '*' (fire immediately after startup) OR HH:MM.
    - All other rules are preserved.
    """
    patients: List[Dict[str, Any]] = getattr(cfg, "PATIENTS", None)
    if not isinstance(patients, list) or not patients:
        raise ValueError("PATIENTS must be a non-empty list")

    seen_keys: set[tuple[int, str]] = set()
    for p in patients:
        for key in ("patient_id", "patient_label", "group_id", "nurse_user_id", "doses"):
            if key not in p:
                raise ValueError(f"patient missing required field: {key}")
        pid = p["patient_id"]
        doses = p["doses"]
        if not isinstance(doses, list) or not doses:
            raise ValueError(f"patient {pid}: 'doses' must be a non-empty list")

        for d in doses:
            if "time" not in d or "text" not in d:
                raise ValueError(f"patient {pid}: each dose must have 'time' and 'text'")
            t = d["time"]
            if t != "*" and not _is_valid_hhmm(t):
                raise ValueError(f"patient {pid}: invalid dose time '{t}' (expected HH:MM or '*')")
            if t != "*":
                # Uniqueness per patient (ignore '*' which is one-shot at startup)
                k = (pid, t)
                if k in seen_keys:
                    raise ValueError(f"patient {pid}: duplicate dose time '{t}'")
                seen_keys.add(k)
            if not str(d["text"]).strip():
                raise ValueError(f"patient {pid}: dose 'text' must be non-empty")

    # Confirmation patterns
    pats = getattr(cfg, "CONFIRM_PATTERNS", None)
    if not isinstance(pats, list) or not pats or not all(isinstance(x, str) and x for x in pats):
        raise ValueError("CONFIRM_PATTERNS must be a non-empty list of strings")

    # Measures (consistent with v4)
    measures = getattr(cfg, "MEASURES", None)
    if not isinstance(measures, dict) or not measures:
        raise ValueError("MEASURES must be a non-empty dict")
    for mid, m in measures.items():
        if not isinstance(m, dict):
            raise ValueError(f"Measure '{mid}' must be a dict")
        if not m.get("label"):
            raise ValueError(f"Measure '{mid}' is missing 'label'")
        patterns = m.get("patterns")
        if not isinstance(patterns, list) or not patterns:
            raise ValueError(f"Measure '{mid}' must define non-empty 'patterns'")
        if not m.get("csv_file"):
            raise ValueError(f"Measure '{mid}' must define 'csv_file'")
