from config import Config
from services.db_service import init_db, requeue_stale_processing_jobs
from services.job_service import claim_job_for_worker, enqueue_parse_job, get_job_by_id


def test_enqueue_and_claim_job(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "SQLITE_DB_PATH", tmp_path / "test_jobs.db")
    init_db()

    upload_file = tmp_path / "input.xlsx"
    upload_file.write_text("demo", encoding="utf-8")

    job_id = enqueue_parse_job(upload_path=upload_file, original_filename="input.xlsx")
    job = get_job_by_id(job_id)

    assert job is not None
    assert job["state"] == "queued"

    claimed = claim_job_for_worker()
    assert claimed is not None
    assert claimed["id"] == job_id
    assert claimed["state"] == "processing"


def test_requeue_stale_processing_job(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "SQLITE_DB_PATH", tmp_path / "test_jobs.db")
    init_db()

    upload_file = tmp_path / "input.xlsx"
    upload_file.write_text("demo", encoding="utf-8")
    job_id = enqueue_parse_job(upload_path=upload_file, original_filename="input.xlsx")
    claim_job_for_worker()

    requeued = requeue_stale_processing_jobs(stale_seconds=-1)
    assert requeued >= 1

    job = get_job_by_id(job_id)
    assert job is not None
    assert job["state"] == "queued"
