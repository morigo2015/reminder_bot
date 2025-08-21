# app/regex_bank.py
from __future__ import annotations
import re
from typing import Final

LABEL_PILL_NEGATE: Final[str] = "pill_negate"
LABEL_OTHER: Final[str] = "other"

# Boundaries to avoid partial words; small multilingual list.
_NEG_PAT = re.compile(
    r"\b(ні|не|нет|не\s+пив|не\s*прийм\w*)\b", re.IGNORECASE | re.UNICODE
)
_OK_PAT = re.compile(
    r"\b(так|ок|ok|окей|готово|done|yes|прийняв\w*|випив\w*|принял\w*)\b",
    re.IGNORECASE | re.UNICODE,
)


def is_negation(text: str) -> bool:
    return bool(_NEG_PAT.search(text or ""))


def is_confirmation(text: str) -> bool:
    return bool(_OK_PAT.search(text or ""))


def classify_text(text: str) -> str:
    # Minimal: "pill_negate" or generic "other"
    return LABEL_PILL_NEGATE if is_negation(text) else LABEL_OTHER
