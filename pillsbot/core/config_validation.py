# pillsbot/core/config_validation.py
from __future__ import annotations

from typing import Any, Dict, List
from datetime import datetime


def validate_config(cfg: Any) -> None:
    """
    Validate runtime configuration before starting the bot.

    - PATIENTS must be a non-empty list.
    - Each patient must have required fields.
    - Dose times must be valid HH:MM strings and unique per patient.
    - Dose text must be present (field 'text').
    - CONFIRM_PATTERNS must be a non-empty list of strings.
    - MEASURES must be a non-empty dict with minimal required fields.
    """
    required_fields = {
        "patient_id",
        "patient_label",
        "group_id",
        "nurse_user_id",
        "doses",
    }

    def parse_time_str(t: str) -> None:
        try:
            datetime.strptime(t, "%H:%M")
        except ValueError as e:
            raise ValueError(f"Invalid time '{t}', expected HH:MM") from e

    patients = getattr(cfg, "PATIENTS", None)
    if not isinstance(patients, list):
        raise ValueError("PATIENTS must be a list of patient dictionaries")
    if len(patients) == 0:
        raise ValueError("PATIENTS must not be empty")

    for p in patients:
        missing = required_fields - set(p.keys())
        if missing:
            raise ValueError(f"Patient missing fields: {missing}")

        seen_times = set()
        for d in p.get("doses", []):
            t = d.get("time")
            if not t:
                raise ValueError(
                    f"Missing 'time' in a dose for patient {p.get('patient_label')}"
                )
            if t in seen_times:
                raise ValueError(
                    f"Duplicate dose time for patient {p['patient_label']}: {t}"
                )
            seen_times.add(t)
            parse_time_str(t)

            if not d.get("text"):
                raise ValueError(
                    f"Dose text is required for patient {p['patient_label']} at {t}"
                )

    # Confirm patterns
    pats = getattr(cfg, "CONFIRM_PATTERNS", None)
    if not isinstance(pats, list) or not pats:
        raise ValueError("CONFIRM_PATTERNS must be a non-empty list of strings")

    # Measures
    measures = getattr(cfg, "MEASURES", None)
    if not isinstance(measures, dict) or not measures:
        raise ValueError("MEASURES must be a non-empty dict")
    for mid, m in measures.items():
        if not isinstance(m, dict):
            raise ValueError(f"Measure '{mid}' must be a dict")
        if not m.get("label"):
            raise ValueError(f"Measure '{mid}' is missing 'label'")
        pats = m.get("patterns")
        if not isinstance(pats, list) or not pats:
            raise ValueError(f"Measure '{mid}' must define non-empty 'patterns'")
        if not m.get("csv_file"):
            raise ValueError(f"Measure '{mid}' must define 'csv_file'")
