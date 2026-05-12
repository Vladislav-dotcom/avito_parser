from __future__ import annotations

import logging
from pathlib import Path
from time import time

from services.db_service import fetch_due_cleanup_entries, mark_cleanup_processed, schedule_cleanup

logger = logging.getLogger(__name__)


def schedule_file_deletion(file_path: Path, delay_seconds: int) -> None:
    delete_at = int(time()) + max(delay_seconds, 1)
    schedule_cleanup(file_path=file_path, delete_after_ts=delete_at)


def cleanup_expired_files() -> int:
    current_timestamp = int(time())
    due_files = fetch_due_cleanup_entries(current_timestamp, limit=200)
    removed_count = 0

    for entry in due_files:
        file_path = Path(entry["file_path"])
        try:
            if file_path.exists():
                file_path.unlink()
                logger.info("Файл удален плановой очисткой", extra={"job_id": "cleanup"})
            removed_count += 1
        except OSError:
            logger.exception("Не удалось удалить файл при очистке", extra={"job_id": "cleanup"})
        finally:
            mark_cleanup_processed(entry["id"])

    return removed_count
