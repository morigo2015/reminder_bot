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
    parser_kind: str  # "int3" | "float1"
    separators: Optional[List[str]] = None  # for pressure
    decimal_commas: Optional[bool] = None  # for weight


class MeasurementRegistry:
    """
    Central registry for measurement parsing + storage.

    * Start-anchored dispatch by configured patterns.
    * Optional punctuation after keyword (':' or '-') is allowed.
    * Per-measure syntax validation/parsing.
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
                parser_kind=m["parser_kind"],
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

    # ---- Dispatch (start-anchored) ----
    def match(self, text: str | None) -> Optional[Tuple[str, str]]:
        t = text or ""
        for mid, rx in self._compiled.items():
            m = rx.match(t)
            if m:
                body = (m.group("body") or "").strip()
                return mid, body
        return None

    # ---- Parsing per measure ----
    def parse(self, measure_id: str, body: str) -> Dict[str, Any]:
        md = self.measures[measure_id]
        if md.parser_kind == "int3":
            # pressure: exactly three integers; separators: space/comma/slash
            seps = md.separators or [" ", ",", "/"]
            s = body.strip()
            if not s:
                return {"ok": False, "error": "arity"}
            for sep in seps:
                s = s.replace(sep, " ")
            parts = [p for p in s.strip().split() if p]
            if len(parts) != 3:
                return {"ok": False, "error": "arity"}
            vals: List[int] = []
            for p in parts:
                if p.startswith("+"):
                    p = p[1:]
                if not p.isdigit():
                    return {"ok": False, "error": "format"}
                vals.append(int(p))
            return {"ok": True, "values": tuple(vals)}
        elif md.parser_kind == "float1":
            # weight: exactly one number (dot or comma decimal), non-negative
            tok = (body or "").strip()
            toks = tok.split()
            if len(toks) != 1:
                return {"ok": False, "error": "arity_one"}
            token = toks[0]
            if md.decimal_commas:
                token = token.replace(",", ".")
            if token.startswith("+"):
                token = token[1:]
            try:
                v = float(token)
            except ValueError:
                return {"ok": False, "error": "format_one"}
            if v < 0 or v != v or v in (float("inf"), float("-inf")):
                return {"ok": False, "error": "format_one"}
            return {"ok": True, "values": (v,)}
        else:
            raise ValueError(f"Unknown parser_kind for {measure_id}: {md.parser_kind}")

    # ---- CSV writing ----
    def append_csv(
        self,
        measure_id: str,
        dt_local: datetime,
        patient_id: int,
        patient_label: str,
        values: tuple,
    ) -> None:
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
                sys, dia, pul = values
                f.write(f"{ts},{patient_id},{patient_label},{sys},{dia},{pul}\n")
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
