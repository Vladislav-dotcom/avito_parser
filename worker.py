from __future__ import annotations

import argparse
import logging
import signal
import time

from config import Config
from services.cleanup_service import cleanup_expired_files
from services.db_service import init_db, requeue_stale_processing_jobs, release_job_to_queue
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


def run_worker() -> None:
    global _shutdown_requested, _current_job_id

    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)

    requeued = requeue_stale_processing_jobs(Config.STALE_PROGRESS_SECONDS)
    if requeued:
        logger.warning(
            f"В очередь возвращено зависших задач: {requeued}",
            extra={"job_id": "worker"},
        )

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
    while True:
        deleted_count = cleanup_expired_files()
        if deleted_count:
            logger.info(
                f"Удалено файлов: {deleted_count}",
                extra={"job_id": "cleanup-loop"},
            )
        time.sleep(Config.CLEANUP_INTERVAL_SECONDS)


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
