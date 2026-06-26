from __future__ import annotations

import re
from typing import Optional

_CONDITION_MARKERS: list[tuple[str, re.Pattern[str]]] = [
    ("демонтаж", re.compile(r"демонтаж", re.IGNORECASE)),
    ("были смонтированы", re.compile(r"(?:были\s+)?смонтирован[аы]?", re.IGNORECASE)),
    ("в работе не было", re.compile(r"(?:в\s+работе\s+не\s+было|не\s+было\s+в\s+работе)", re.IGNORECASE)),
]


def extract_condition_markers(text: str) -> list[str]:
    if not text or not text.strip():
        return []

    found: list[str] = []
    for label, pattern in _CONDITION_MARKERS:
        if pattern.search(text):
            found.append(label)
    return found


def merge_condition(base: Optional[str], markers: list[str]) -> Optional[str]:
    parts: list[str] = []

    if base and base.strip():
        parts.extend(part.strip() for part in base.split(",") if part.strip())

    existing = {part.casefold() for part in parts}
    for marker in markers:
        if marker.casefold() not in existing:
            parts.append(marker)
            existing.add(marker.casefold())

    if not parts:
        return None
    return ", ".join(parts)
