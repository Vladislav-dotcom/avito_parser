from time import time

import pandas as pd
import pytest

from config import Config
from services.checkpoint_service import append_checkpoint, delete_checkpoint, load_checkpoint
from services.db_service import get_connection, init_db, list_suppliers, requeue_stale_processing_jobs
from services.job_service import claim_job_for_worker, enqueue_parse_job, get_job_by_id


def _first_supplier_id() -> str:
    suppliers = list_suppliers()
    assert suppliers
    return str(suppliers[0]["id"])


def test_enqueue_and_claim_job(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "SQLITE_DB_PATH", tmp_path / "test_jobs.db")
    init_db()

    upload_file = tmp_path / "input.xlsx"
    upload_file.write_text("demo", encoding="utf-8")

    job_id = enqueue_parse_job(
        upload_path=upload_file,
        original_filename="input.xlsx",
        supplier_id=_first_supplier_id(),
    )
    job = get_job_by_id(job_id)

    assert job is not None
    assert job["state"] == "queued"
    assert job["supplier_id"]

    claimed = claim_job_for_worker()
    assert claimed is not None
    assert claimed["id"] == job_id
    assert claimed["state"] == "processing"
    assert claimed["last_progress_at"] is not None


def test_requeue_stale_processing_job(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "SQLITE_DB_PATH", tmp_path / "test_jobs.db")
    init_db()

    upload_file = tmp_path / "input.xlsx"
    upload_file.write_text("demo", encoding="utf-8")
    job_id = enqueue_parse_job(
        upload_path=upload_file,
        original_filename="input.xlsx",
        supplier_id=_first_supplier_id(),
    )
    claim_job_for_worker()

    requeued = requeue_stale_processing_jobs(stale_seconds=-1)
    assert requeued >= 1

    job = get_job_by_id(job_id)
    assert job is not None
    assert job["state"] == "queued"


def test_requeue_does_not_touch_active_job(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "SQLITE_DB_PATH", tmp_path / "test_jobs.db")
    init_db()

    upload_file = tmp_path / "input.xlsx"
    upload_file.write_text("demo", encoding="utf-8")
    job_id = enqueue_parse_job(
        upload_path=upload_file,
        original_filename="input.xlsx",
        supplier_id=_first_supplier_id(),
    )
    claim_job_for_worker()

    with get_connection() as conn:
        conn.execute(
            "UPDATE jobs SET last_progress_at = ? WHERE id = ?",
            (int(time()), job_id),
        )
        conn.commit()

    requeued = requeue_stale_processing_jobs(stale_seconds=300)
    assert requeued == 0

    job = get_job_by_id(job_id)
    assert job is not None
    assert job["state"] == "processing"


def test_requeue_preserves_processed_rows(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "SQLITE_DB_PATH", tmp_path / "test_jobs.db")
    init_db()

    upload_file = tmp_path / "input.xlsx"
    upload_file.write_text("demo", encoding="utf-8")
    job_id = enqueue_parse_job(
        upload_path=upload_file,
        original_filename="input.xlsx",
        supplier_id=_first_supplier_id(),
    )
    claim_job_for_worker()

    with get_connection() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET processed_rows = 50, failed_rows = 2, last_progress_at = 1
            WHERE id = ?
            """,
            (job_id,),
        )
        conn.commit()

    requeued = requeue_stale_processing_jobs(stale_seconds=-1)
    assert requeued == 1

    job = get_job_by_id(job_id)
    assert job is not None
    assert job["state"] == "queued"
    assert job["processed_rows"] == 50
    assert job["failed_rows"] == 2


def test_checkpoint_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "SQLITE_DB_PATH", tmp_path / "test_jobs.db")
    monkeypatch.setattr(Config, "STORAGE_DIR", tmp_path / "storage")
    monkeypatch.setattr(Config, "CHECKPOINT_DIR", tmp_path / "storage" / "checkpoints")

    job_id = "abc123"
    parsed_items = [{"brand": "ABB", "article": "X-1"}]
    append_checkpoint(job_id, 1, parsed_items, False)

    loaded = load_checkpoint(job_id)
    assert loaded[1]["parsed_items"] == parsed_items

    delete_checkpoint(job_id)
    assert load_checkpoint(job_id) == {}
