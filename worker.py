from __future__ import annotations

import argparse
import logging
import os
import signal
import threading
import time

from config import Config
from services.cleanup_service import cleanup_expired_files
from services.db_service import (
    fetch_job,
    init_db,
    release_job_to_queue,
    requeue_orphan_jobs,
    requeue_stale_processing_jobs,
)
from services.job_service import claim_job_for_worker
from services.logging_config import configure_logging
from tasks import process_xlsx_job

logger = logging.getLogger(__name__)

_shutdown_requested = False
_current_job_id: str | None = None


def _handle_shutdown(signum: int, _frame: object) -> None:
    global _shutdown_requested
    _shutdown_requested = True
    logger.info(
        f"Получен сигнал завершения ({signum}), ожидаем завершение текущей строки...",
        extra={"job_id": "worker"},
    )


def _maybe_requeue_stale_jobs(last_check_at: float) -> float:
    now = time.monotonic()
    if now - last_check_at < Config.STALE_REQUEUE_INTERVAL_SECONDS:
        return last_check_at

    requeued = requeue_stale_processing_jobs(Config.STALE_PROGRESS_SECONDS)
    if requeued:
        logger.warning(
            f"В очередь возвращено зависших задач: {requeued}",
            extra={"job_id": "worker"},
        )
    return now


def _watchdog_loop() -> None:
    while not _shutdown_requested:
        job_id = _current_job_id
        if job_id:
            job = fetch_job(job_id)
            if job and job.get("state") in {"processing", "finalizing"}:
                last_progress_at = job.get("last_progress_at") or job.get("started_at")
                if last_progress_at:
                    age = int(time.time()) - int(last_progress_at)
                    if age > Config.STALE_PROGRESS_SECONDS:
                        logger.error(
                            f"Watchdog: нет прогресса {age}с, release и exit",
                            extra={"job_id": job_id},
                        )
                        release_job_to_queue(job_id)
                        os._exit(1)
        time.sleep(Config.STALE_REQUEUE_INTERVAL_SECONDS)


def run_worker() -> None:
    global _shutdown_requested, _current_job_id

    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    orphans = requeue_orphan_jobs()
    if orphans:
        logger.warning(
            f"На старте в очередь возвращено orphan-задач: {orphans}",
            extra={"job_id": "worker"},
        )

    watchdog = threading.Thread(target=_watchdog_loop, name="worker-watchdog", daemon=True)
    watchdog.start()

    logger.info("Запущен worker loop", extra={"job_id": "worker"})
    last_stale_check = time.monotonic()

    while not _shutdown_requested:
        job = claim_job_for_worker()
        if job is None:
            last_stale_check = _maybe_requeue_stale_jobs(last_stale_check)
            time.sleep(Config.JOB_POLL_INTERVAL_SECONDS)
            continue

        job_id = str(job["id"])
        _current_job_id = job_id
        try:
            result = process_xlsx_job(job_id=job_id, shutdown_check=lambda: _shutdown_requested)
            if result.get("status") == "interrupted":
                break
        except Exception:  # noqa: BLE001
            logger.exception("Ошибка обработки job", extra={"job_id": job_id})
        finally:
            _current_job_id = None

    if _shutdown_requested and _current_job_id:
        release_job_to_queue(_current_job_id)

    logger.info("Worker loop завершён", extra={"job_id": "worker"})


def run_cleanup_loop() -> None:
    logger.info("Запущен cleanup loop", extra={"job_id": "cleanup-loop"})
    last_cleanup_at = 0.0
    while True:
        now = time.monotonic()
        if now - last_cleanup_at >= Config.CLEANUP_INTERVAL_SECONDS:
            deleted_count = cleanup_expired_files()
            if deleted_count:
                logger.info(
                    f"Удалено файлов: {deleted_count}",
                    extra={"job_id": "cleanup-loop"},
                )
            last_cleanup_at = now

        requeued = requeue_stale_processing_jobs(Config.STALE_PROGRESS_SECONDS)
        if requeued:
            logger.warning(
                f"Cleanup: в очередь возвращено зависших задач: {requeued}",
                extra={"job_id": "cleanup-loop"},
            )

        time.sleep(Config.STALE_REQUEUE_INTERVAL_SECONDS)


def main() -> None:
    configure_logging()
    Config.ensure_directories()
    init_db()

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["worker", "cleanup"],
        default="worker",
        help="worker - запуск SQLite worker, cleanup - запуск периодической очистки",
    )
    args = parser.parse_args()

    if args.mode == "cleanup":
        run_cleanup_loop()
    else:
        run_worker()


if __name__ == "__main__":
    main()
