from __future__ import annotations

from time import time

# AI по строке обычно секунды–десятки секунд; >1 строки/сек после resume = сломанный started_at.
_MAX_PLAUSIBLE_ROWS_PER_SEC = 1.0


def compute_progress_eta(
    *,
    processed_rows: int,
    total_rows: int,
    state: str,
    started_at: int | None,
    created_at: int | None,
    now_ts: int | None = None,
) -> tuple[int | None, float | None, int | None]:
    """Вернуть (elapsed_seconds, rows_per_minute, eta_seconds)."""
    if state not in {"processing", "finalizing"}:
        return None, None, None

    now = int(now_ts if now_ts is not None else time())
    anchor = started_at or created_at
    if not anchor:
        return None, None, None

    elapsed_seconds = max(0, now - int(anchor))
    if state != "processing" or processed_rows <= 0 or elapsed_seconds <= 0:
        return elapsed_seconds, None, None

    rate = processed_rows / elapsed_seconds
    if rate > _MAX_PLAUSIBLE_ROWS_PER_SEC and created_at:
        elapsed_seconds = max(1, now - int(created_at))
        rate = processed_rows / elapsed_seconds

    rows_per_minute = round(rate * 60, 2)
    remaining = max(0, total_rows - processed_rows)
    eta_seconds = int(remaining / rate) if rate > 0 else None
    return elapsed_seconds, rows_per_minute, eta_seconds
