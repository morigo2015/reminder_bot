# pillsbot/core/config_validation.py
from __future__ import annotations

from datetime import datetime
from typing import Any


def validate_config(cfg: Any) -> None:
    """
    Validate runtime configuration before starting the bot.

    - Ensures patient records have required fields.
    - Ensures dose times are valid HH:MM strings and unique per patient.
    - Ensures dose text is present.
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
