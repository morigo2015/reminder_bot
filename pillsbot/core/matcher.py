# pillsbot/core/matcher.py
from __future__ import annotations

import re
from typing import Iterable, List, Pattern


class Matcher:
    """
    Regex-based confirmation matcher (Unicode + case-insensitive).
    All matching semantics live in the provided patterns (see config.CONFIRM_PATTERNS).
    No input normalization or pattern rewriting happens here.
    """

    def __init__(self, patterns: Iterable[str]) -> None:
        flags = re.IGNORECASE | re.UNICODE
        self._compiled: List[Pattern[str]] = [re.compile(p, flags) for p in patterns]

    def matches_confirmation(self, text: str | None) -> bool:
        if not text:
            return False
        return any(rx.search(text) for rx in self._compiled)


__all__ = ["Matcher"]
