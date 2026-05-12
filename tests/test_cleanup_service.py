from pathlib import Path
from time import sleep

from config import Config
from services.db_service import init_db
from services.cleanup_service import cleanup_expired_files, schedule_file_deletion


def test_cleanup_deletes_due_file(tmp_path, monkeypatch):
    monkeypatch.setattr(Config, "SQLITE_DB_PATH", tmp_path / "test_jobs.db")
    init_db()

    file_path = tmp_path / "result.xlsx"
    file_path.write_text("demo", encoding="utf-8")

    schedule_file_deletion(file_path, delay_seconds=1)
    sleep(1.1)

    deleted = cleanup_expired_files()
    assert deleted >= 1
    assert not file_path.exists()
