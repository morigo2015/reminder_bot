# pillsbot/core/measurements.py
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime, date
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class MeasureDef:
    id: str
    label: str
    patterns: List[str]
    csv_file: str
    parser_kind: str  # legacy hints: "int2" | "float1"
    separators: Optional[List[str]] = None  # legacy for pressure
    decimal_commas: Optional[bool] = None  # legacy for weight


class MeasurementRegistry:
    """
    Central registry for measurement parsing + storage (v4).

    * Start-anchored dispatch by configured patterns (typed keywords like "тиск", "вага").
    * Free-form tolerant parsers are provided below and should be used by the engine.
    * CSV append with header creation.
    * 'has_today' helper for daily checks.
    """

    def __init__(self, tz, measures_cfg: Dict[str, Dict[str, Any]] | None = None):
        self.tz = tz
        self.measures: Dict[str, MeasureDef] = {}
        self._compiled: Dict[str, re.Pattern[str]] = {}
        measures_cfg = measures_cfg or {}
        flags = re.IGNORECASE | re.UNICODE

        for mid, m in measures_cfg.items():
            md = MeasureDef(
                id=mid,
                label=m["label"],
                patterns=m["patterns"],
                csv_file=m["csv_file"],
                parser_kind=m.get("parser_kind", ""),
                separators=m.get("separators"),
                decimal_commas=m.get("decimal_commas"),
            )
            self.measures[mid] = md
            # ^\s*(kw1|kw2|...)\b[:\-]?\s*(?P<body>.*)?$
            union = "|".join(re.escape(p) for p in md.patterns)
            self._compiled[mid] = re.compile(
                rf"^\s*(?:{union})\b[:\-]?\s*(?P<body>.+)?$", flags
            )

    def available(self) -> List[str]:
        return list(self.measures.keys())

    def get_label(self, measure_id: str) -> str:
        return self.measures[measure_id].label

    # ---- Dispatch by typed keyword (start-anchored) ----
    def match(self, text: str | None) -> Optional[Tuple[str, str]]:
        t = text or ""
        for mid, rx in self._compiled.items():
            m = rx.match(t)
            if m:
                body = (m.group("body") or "").strip()
                return mid, body
        return None

    # ---- CSV writing ----
    def append_csv(
        self,
        measure_id: str,
        dt_local: datetime,
        patient_id: int,
        patient_label: str,
        values: tuple,
    ) -> None:
        """
        Appends one row to the measure CSV.

        For 'pressure' we always use the schema:
          date_time_local,patient_id,patient_label,systolic,diastolic,pulse
        If pulse is absent, the 'pulse' column is left blank.
        """
        md = self.measures[measure_id]
        path = md.csv_file
        os.makedirs(os.path.dirname(path), exist_ok=True)
        is_new = not os.path.exists(path)

        with open(path, "a", encoding="utf-8") as f:
            if is_new:
                if measure_id == "pressure":
                    f.write(
                        "date_time_local,patient_id,patient_label,systolic,diastolic,pulse\n"
                    )
                elif measure_id == "weight":
                    f.write("date_time_local,patient_id,patient_label,weight\n")
                else:
                    cols = ",".join(f"value{i + 1}" for i in range(len(values)))
                    f.write(f"date_time_local,patient_id,patient_label,{cols}\n")

            ts = dt_local.strftime("%Y-%m-%d %H:%M")
            if measure_id == "pressure":
                if len(values) == 3:
                    sys_v, dia_v, pulse_v = values
                    f.write(f"{ts},{patient_id},{patient_label},{sys_v},{dia_v},{pulse_v}\n")
                elif len(values) == 2:
                    sys_v, dia_v = values
                    f.write(f"{ts},{patient_id},{patient_label},{sys_v},{dia_v},\n")
                else:
                    f.write(f"{ts},{patient_id},{patient_label},,,\n")
            elif measure_id == "weight":
                (w,) = values
                f.write(f"{ts},{patient_id},{patient_label},{w}\n")
            else:
                vals = ",".join(str(x) for x in values)
                f.write(f"{ts},{patient_id},{patient_label},{vals}\n")

    # ---- Daily check helper ----
    def has_today(self, measure_id: str, patient_id: int, date_local: date) -> bool:
        md = self.measures[measure_id]
        path = md.csv_file
        if not os.path.exists(path):
            return False
        with open(path, "r", encoding="utf-8") as f:
            _ = f.readline()  # header
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(",")
                if len(parts) < 3:
                    continue
                dt_str = parts[0].strip()
                pid_str = parts[1].strip()
                try:
                    dt = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
                    pid = int(pid_str)
                except Exception:
                    continue
                if pid == patient_id and dt.date() == date_local:
                    return True
        return False


# ======================================================================================
# Free-form tolerant parsers used by the engine (Option A)
# ======================================================================================

_INT_RE = re.compile(r"(?<!\d)(\d{1,3})(?!\d)")
_FLOAT_RE = re.compile(r"(?<!\d)(\d{1,3}(?:[.,]\d{1,2})?)(?!\d)")


def parse_pressure_free(text: str) -> Dict[str, Any]:
    """
    Accepts:
      - 120/80
      - 120 80
      - 120-80
      - 120 на 80
      - optional 3rd number as pulse: "... 72"
    Returns:
      {"ok": True, "sys": int, "dia": int, "pulse": Optional[int]}
      or {"ok": False, "error": "one_number"|"range"|"unrecognized"}
    """
    t = (text or "").strip()
    # Normalize separators "на" and punctuation to space to make number extraction robust
    t = (
        t.replace("/", " ")
        .replace("-", " ")
        .replace("—", " ")
        .replace("–", " ")
        .replace(":", " ")
    )
    t = re.sub(r"\bна\b", " ", t, flags=re.IGNORECASE | re.UNICODE)

    nums = [int(m.group(1)) for m in _INT_RE.finditer(t)]
    if len(nums) == 1:
        return {"ok": False, "error": "one_number"}
    if len(nums) < 2:
        return {"ok": False, "error": "unrecognized"}

    sys_v = nums[0]
    dia_v = nums[1]
    pulse_v = nums[2] if len(nums) >= 3 else None

    # Range checks
    if not (70 <= sys_v <= 250) or not (40 <= dia_v <= 150):
        return {"ok": False, "error": "range"}
    if pulse_v is not None and not (30 <= pulse_v <= 220):
        return {"ok": False, "error": "range"}

    return {"ok": True, "sys": sys_v, "dia": dia_v, "pulse": pulse_v}


def parse_weight_free(text: str) -> Dict[str, Any]:
    """
    Accepts one numeric token (dot or comma decimal), units optional (кг/kg).
    Returns:
      {"ok": True, "kg": float} or
      {"ok": False, "error": "likely_pressure"|"range"|"unrecognized"}
    """
    t = (text or "").strip()
    # Strip units
    t = re.sub(r"\s*(кг|kg)\b", "", t, flags=re.IGNORECASE | re.UNICODE)
    nums = [m.group(1) for m in _FLOAT_RE.finditer(t)]

    if len(nums) == 0:
        return {"ok": False, "error": "unrecognized"}
    if len(nums) > 1:
        # Two or more numbers usually indicate pressure
        return {"ok": False, "error": "likely_pressure"}

    token = nums[0].replace(",", ".")
    try:
        v = float(token)
    except ValueError:
        return {"ok": False, "error": "unrecognized"}

    if not (25.0 <= v <= 300.0):
        return {"ok": False, "error": "range"}

    return {"ok": True, "kg": v}
