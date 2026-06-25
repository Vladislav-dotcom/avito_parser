from unittest.mock import patch

import pandas as pd
import pytest

from config import Config
from services.checkpoint_service import append_checkpoint
from services.db_service import init_db, requeue_stale_processing_jobs, update_job_progress
from services.job_service import claim_job_for_worker, enqueue_parse_job, get_job_by_id
from tasks import process_xlsx_job


def _make_xlsx(path, rows: int = 3) -> None:
    dataframe = pd.DataFrame(
        [
            {
                "Наименование": f"Позиция {index}",
                "Цена": 1000 + index,
                "Валюта": "RUB",
                "Кол-во в наличии": 1,
                "Раздел": "A",
                "Категория": "B",
                "Описание": f"desc {index}",
            }
            for index in range(1, rows + 1)
        ]
    )
    dataframe.to_excel(path, index=False)


def test_process_xlsx_job_resumes_from_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "SQLITE_DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setattr(Config, "STORAGE_DIR", tmp_path / "storage")
    monkeypatch.setattr(Config, "UPLOAD_DIR", tmp_path / "storage" / "uploads")
    monkeypatch.setattr(Config, "RESULT_DIR", tmp_path / "storage" / "results")
    monkeypatch.setattr(Config, "CHECKPOINT_DIR", tmp_path / "storage" / "checkpoints")
    init_db()

    upload_file = tmp_path / "storage" / "uploads" / "input.xlsx"
    upload_file.parent.mkdir(parents=True, exist_ok=True)
    _make_xlsx(upload_file, rows=3)

    job_id = enqueue_parse_job(
        upload_path=upload_file,
        original_filename="input.xlsx",
    )
    claim_job_for_worker()

    parsed_item = [{
        "brand": "ABB",
        "article": "A-1",
        "price": 1001,
        "quantity": 1,
        "condition": "новое",
        "generated_description": "desc",
    }]
    append_checkpoint(job_id, 1, parsed_item, False)
    update_job_progress(job_id=job_id, processed_rows=1, failed_rows=0)
    requeue_stale_processing_jobs(stale_seconds=-1)

    with patch("tasks.parse_description", return_value=(parsed_item, None)) as parse_mock:
        claim_job_for_worker()
        process_xlsx_job(job_id)

    assert parse_mock.call_count == 2

    job = get_job_by_id(job_id)
    assert job is not None
    assert job["state"] == "finished"
    assert job["processed_rows"] == 3
