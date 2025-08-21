# app/regex_bank.py
from __future__ import annotations
import re
from typing import Final

# Minimal, on-purpose.
LABEL_PILL_NEGATE: Final[str] = "pill_negate"
LABEL_OTHER: Final[str] = "other"

_NEG_PAT = re.compile(r"\b(ні|не|нет|не\s+пив|не\s+прийм)\b", re.IGNORECASE)
_OK_PAT = re.compile(
    r"\b(так|ок|окей|прийняв|випив|принял|приняла|приняла)\b", re.IGNORECASE
)


def is_negation(text: str) -> bool:
    return bool(_NEG_PAT.search(text))


def is_confirmation(text: str) -> bool:
    return bool(_OK_PAT.search(text))


def classify_text(text: str) -> str:
    # Keep it intentionally tiny: only one special label for pill negation.
    # All else treated as "other" (symptom/free text).
    return LABEL_PILL_NEGATE if is_negation(text) else LABEL_OTHER
