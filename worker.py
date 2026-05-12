from __future__ import annotations

import argparse
import logging
import time

from config import Config
from services.cleanup_service import cleanup_expired_files
from services.db_service import init_db, requeue_stale_processing_jobs
from services.job_service import claim_job_for_worker
from services.logging_config import configure_logging
from tasks import process_xlsx_job

logger = logging.getLogger(__name__)


def run_worker() -> None:
    requeued = requeue_stale_processing_jobs(Config.STALE_PROCESSING_SECONDS)
    if requeued:
        logger.warning(f"В очередь возвращено зависших задач: {requeued}", extra={"job_id": "worker"})

    logger.info("Запущен worker loop", extra={"job_id": "worker"})
    while True:
        job = claim_job_for_worker()
        if job is None:
            time.sleep(Config.JOB_POLL_INTERVAL_SECONDS)
            continue

        job_id = str(job["id"])
        try:
            process_xlsx_job(job_id=job_id)
        except Exception:  # noqa: BLE001
            logger.exception("Ошибка обработки job", extra={"job_id": job_id})


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
