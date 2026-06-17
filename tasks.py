from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from config import Config
from services.ai_service import parse_description
from services.checkpoint_service import append_checkpoint, delete_checkpoint, load_checkpoint
from services.cleanup_service import schedule_file_deletion
from services.db_service import (
    fail_job,
    fetch_job,
    finish_job,
    get_connection,
    release_job_to_queue,
    update_job_progress,
    update_job_state,
    update_job_total_rows,
)
from services.excel_service import (
    build_result_dataframe,
    format_export_for_1c,
    read_excel,
    validate_columns,
    write_excel,
)
from services.supplier_service import get_supplier

logger = logging.getLogger(__name__)


def _get_job_paths(job_id: str) -> tuple[Path, str]:
    with get_connection() as conn:
        row = conn.execute(
            "SELECT upload_path, original_filename FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
    if row is None:
        raise ValueError(f"Job not found: {job_id}")
    return Path(row["upload_path"]), str(row["original_filename"])


def _process_row(
    job_id: str,
    row_number: int,
    row,
) -> tuple[list[dict], bool]:
    parsed_items, error_message = parse_description(
        description=str(row.get("Описание", "")),
        row_data=row.to_dict(),
        job_id=job_id,
    )
    had_error = bool(error_message)
    if had_error:
        logger.warning(
            f"Строка обработана с ошибкой: {error_message}",
            extra={"job_id": job_id, "row_index": row_number},
        )
    else:
        logger.info("Строка обработана успешно", extra={"job_id": job_id, "row_index": row_number})
    return parsed_items, had_error


def process_xlsx_job(
    job_id: str,
    shutdown_check: Callable[[], bool] | None = None,
) -> dict[str, str]:
    upload_path, _original_filename = _get_job_paths(job_id)
    job = fetch_job(job_id)
    if job is None:
        raise ValueError(f"Job not found: {job_id}")

    supplier_id = job.get("supplier_id")
    if not supplier_id:
        fail_job(job_id=job_id, error="Не указан поставщик для задачи.")
        delete_checkpoint(job_id)
        raise ValueError("Не указан поставщик для задачи.")

    if get_supplier(str(supplier_id)) is None:
        fail_job(job_id=job_id, error="Поставщик для задачи не найден.")
        delete_checkpoint(job_id)
        raise ValueError("Поставщик для задачи не найден.")

    try:
        dataframe = read_excel(upload_path)
        validate_columns(dataframe)
        total_rows = len(dataframe.index)
        update_job_total_rows(job_id, total_rows)

        checkpoint = load_checkpoint(job_id)
        resume_from = int(job.get("processed_rows") or 0)
        if checkpoint and resume_from > 0:
            max_checkpoint_row = max(checkpoint)
            if max_checkpoint_row != resume_from:
                logger.warning(
                    f"Checkpoint не совпадает с processed_rows: checkpoint={max_checkpoint_row}, db={resume_from}",
                    extra={"job_id": job_id},
                )

        parsed_rows: list[list[dict]] = []
        failed_rows = int(job.get("failed_rows") or 0)

        for row_number, (_, row) in enumerate(dataframe.iterrows(), start=1):
            if shutdown_check and shutdown_check():
                release_job_to_queue(job_id)
                logger.info("Job возвращён в очередь после сигнала завершения", extra={"job_id": job_id})
                return {"status": "interrupted"}

            if row_number <= resume_from:
                checkpoint_entry = checkpoint.get(row_number)
                if checkpoint_entry is not None:
                    parsed_rows.append(checkpoint_entry["parsed_items"])
                    continue
                parsed_items, had_error = _process_row(job_id, row_number, row)
                parsed_rows.append(parsed_items)
                if had_error:
                    failed_rows += 1
                append_checkpoint(job_id, row_number, parsed_items, had_error)
                update_job_progress(job_id=job_id, processed_rows=row_number, failed_rows=failed_rows)
                continue

            parsed_items, had_error = _process_row(job_id, row_number, row)
            parsed_rows.append(parsed_items)
            if had_error:
                failed_rows += 1
            append_checkpoint(job_id, row_number, parsed_items, had_error)
            update_job_progress(job_id=job_id, processed_rows=row_number, failed_rows=failed_rows)

        update_job_state(job_id=job_id, state="finalizing")
        result_dataframe = build_result_dataframe(dataframe, parsed_rows)
        result_dataframe = format_export_for_1c(result_dataframe)
        output_name = f"{upload_path.stem}_processed_{uuid4().hex[:8]}.xlsx"
        result_path = Path(Config.RESULT_DIR) / output_name
        write_excel(result_dataframe, result_path)

        schedule_file_deletion(upload_path, Config.FILE_TTL_SECONDS)
        schedule_file_deletion(result_path, Config.FILE_TTL_SECONDS)

        finish_job(job_id=job_id, result_path=result_path, failed_rows=failed_rows)
        delete_checkpoint(job_id)
        logger.info("Job завершен успешно", extra={"job_id": job_id})
        return {"status": "ok", "result_path": str(result_path)}
    except Exception as exc:  # noqa: BLE001
        fail_job(job_id=job_id, error=str(exc))
        delete_checkpoint(job_id)
        logger.exception("Job завершен с ошибкой", extra={"job_id": job_id})
        raise
