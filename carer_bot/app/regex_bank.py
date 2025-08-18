# app/regex_bank.py
from __future__ import annotations
import re
from typing import Optional, Tuple
from . import config

# Compile confirmation pattern dynamically from lexicon
_confirm_tokens = sorted(config.CONFIRM_OK, key=len, reverse=True)
_CONFIRM_RE = re.compile(r"(?i)\b(" + "|".join(map(re.escape, _confirm_tokens)) + r")\b")

# Negation phrases (minimal PoC set)
_NEGATE_RE = re.compile(r"(?i)\b(не\s*прийняв|не\s*прийняла|забув|забула|пропустив|пропустила|не\s*встиг|не\s*можу)\b")

# Blood pressure like "130/85" or "130-85"
_BP_RE = re.compile(r"\b(\d{2,3})\s*[\/\-]\s*(\d{2,3})\b")

# Temperature like "37.2" or "38", optional degree/unit markers
_TEMP_RE = re.compile(r"(?i)\b(3[5-9](?:[.,]\d)?|4[0-2](?:[.,]\d)?)\s*°?\s*[cс]?\b")

LABEL_PILL_TAKEN = "pill_taken_affirm"
LABEL_PILL_NEGATE = "pill_taken_negation"
LABEL_MEAS_BP     = "measurement_bp"
LABEL_MEAS_TEMP   = "measurement_temp"
LABEL_SYMPTOM     = "symptom_report"
LABEL_UNKNOWN     = "unknown"

def classify_text(text: str) -> str:
    """
    Returns one of LABEL_* constants.
    Regex-only PoC classifier. Keep conservative.
    """
    if not text:
        return LABEL_UNKNOWN
    t = text.strip()

    if _NEGATE_RE.search(t):
        return LABEL_PILL_NEGATE

    if _CONFIRM_RE.search(t):
        return LABEL_PILL_TAKEN

    if _BP_RE.search(t):
        return LABEL_MEAS_BP

    if _TEMP_RE.search(t):
        return LABEL_MEAS_TEMP

    # Fallback: treat as symptom report (free text), not strictly unknown
    return LABEL_SYMPTOM

def extract_bp(text: str) -> Optional[Tuple[int, int]]:
    m = _BP_RE.search(text or "")
    if not m:
        return None
    try:
        sys = int(m.group(1))
        dia = int(m.group(2))
        if 60 <= dia <= 140 and 80 <= sys <= 260 and sys > dia:
            return sys, dia
    except ValueError:
        pass
    return None

def extract_temp(text: str) -> Optional[float]:
    m = _TEMP_RE.search(text or "")
    if not m:
        return None
    raw = m.group(1).replace(",", ".")
    try:
        val = float(raw)
        if 34.0 <= val <= 42.5:
            return val
    except ValueError:
        return None
    return None

def is_confirmation(text: str) -> bool:
    return bool(_CONFIRM_RE.search(text or ""))

def is_negation(text: str) -> bool:
    return bool(_NEGATE_RE.search(text or ""))
