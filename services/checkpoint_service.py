from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from config import Config


def checkpoint_path(job_id: str) -> Path:
    return Config.CHECKPOINT_DIR / f"{job_id}.jsonl"


def append_checkpoint(
    job_id: str,
    row_index: int,
    parsed_items: list[dict[str, Any]],
    had_error: bool,
) -> None:
    Config.CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    entry = {
        "row_index": row_index,
        "parsed_items": parsed_items,
        "had_error": had_error,
    }
    with checkpoint_path(job_id).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def load_checkpoint(job_id: str) -> dict[int, dict[str, Any]]:
    path = checkpoint_path(job_id)
    if not path.exists():
        return {}

    rows: dict[int, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            entry = json.loads(line)
            rows[int(entry["row_index"])] = entry
    return rows


def delete_checkpoint(job_id: str) -> None:
    path = checkpoint_path(job_id)
    if path.exists():
        path.unlink()
