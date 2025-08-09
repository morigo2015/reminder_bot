from __future__ import annotations

import re
from typing import Iterable

class Matcher:
    def __init__(self, patterns: Iterable[str]) -> None:
        pattern = "|".join(f"({p})" for p in patterns)
        self._rx = re.compile(pattern, re.IGNORECASE | re.UNICODE)

    def matches_confirmation(self, text: str) -> bool:
        return bool(self._rx.search(text or ""))

__all__ = ["Matcher"]
