from __future__ import annotations

import sqlite3
import uuid
from contextlib import contextmanager
from pathlib import Path
from time import time
from typing import Iterator, Optional

from config import Config


def _db_path() -> Path:
    return Path(Config.SQLITE_DB_PATH)


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    Config.ensure_directories()
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                upload_path TEXT NOT NULL,
                result_path TEXT,
                original_filename TEXT NOT NULL,
                total_rows INTEGER NOT NULL DEFAULT 0,
                processed_rows INTEGER NOT NULL DEFAULT 0,
                failed_rows INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                created_at INTEGER NOT NULL,
                started_at INTEGER,
                finished_at INTEGER
            );

            CREATE TABLE IF NOT EXISTS cleanup_schedule (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                file_path TEXT NOT NULL,
                delete_after_ts INTEGER NOT NULL,
                processed INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_jobs_state_created_at
                ON jobs(state, created_at);
            CREATE INDEX IF NOT EXISTS idx_cleanup_due
                ON cleanup_schedule(processed, delete_after_ts);
            """
        )
        conn.commit()


def create_job(upload_path: Path, original_filename: str) -> str:
    job_id = uuid.uuid4().hex
    now_ts = int(time())
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO jobs (
                id, state, upload_path, result_path, original_filename,
                total_rows, processed_rows, failed_rows, error, created_at
            ) VALUES (?, 'queued', ?, '', ?, 0, 0, 0, NULL, ?)
            """,
            (job_id, str(upload_path), original_filename, now_ts),
        )
        conn.commit()
    return job_id


def fetch_job(job_id: str) -> Optional[dict]:
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    return dict(row) if row else None


def requeue_stale_processing_jobs(stale_seconds: int) -> int:
    threshold = int(time()) - stale_seconds
    with get_connection() as conn:
        cursor = conn.execute(
            """
            UPDATE jobs
            SET state = 'queued', started_at = NULL, error = 'job_requeued_after_stale_timeout'
            WHERE state = 'processing'
              AND started_at IS NOT NULL
              AND started_at < ?
            """,
            (threshold,),
        )
        conn.commit()
        return cursor.rowcount


def claim_next_job() -> Optional[dict]:
    with get_connection() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """
            SELECT id
            FROM jobs
            WHERE state = 'queued'
            ORDER BY created_at ASC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            conn.commit()
            return None

        job_id = row["id"]
        now_ts = int(time())
        conn.execute(
            """
            UPDATE jobs
            SET state = 'processing', started_at = ?, error = NULL
            WHERE id = ? AND state = 'queued'
            """,
            (now_ts, job_id),
        )
        conn.commit()
    return fetch_job(job_id)


def update_job_progress(job_id: str, processed_rows: int, failed_rows: int) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET processed_rows = ?, failed_rows = ?
            WHERE id = ?
            """,
            (processed_rows, failed_rows, job_id),
        )
        conn.commit()


def update_job_total_rows(job_id: str, total_rows: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE jobs SET total_rows = ? WHERE id = ?",
            (total_rows, job_id),
        )
        conn.commit()


def update_job_state(job_id: str, state: str) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE jobs SET state = ? WHERE id = ?",
            (state, job_id),
        )
        conn.commit()


def finish_job(job_id: str, result_path: Path, failed_rows: int) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET state = 'finished', result_path = ?, failed_rows = ?, finished_at = ?
            WHERE id = ?
            """,
            (str(result_path), failed_rows, int(time()), job_id),
        )
        conn.commit()


def fail_job(job_id: str, error: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET state = 'failed', error = ?, finished_at = ?
            WHERE id = ?
            """,
            (error, int(time()), job_id),
        )
        conn.commit()


def schedule_cleanup(file_path: Path, delete_after_ts: int) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO cleanup_schedule (file_path, delete_after_ts, processed)
            VALUES (?, ?, 0)
            """,
            (str(file_path), delete_after_ts),
        )
        conn.commit()


def fetch_due_cleanup_entries(current_ts: int, limit: int = 100) -> list[dict]:
    with get_connection() as conn:
        rows = conn.execute(
            """
            SELECT id, file_path
            FROM cleanup_schedule
            WHERE processed = 0
              AND delete_after_ts <= ?
            ORDER BY delete_after_ts ASC
            LIMIT ?
            """,
            (current_ts, limit),
        ).fetchall()
    return [dict(row) for row in rows]


def mark_cleanup_processed(entry_id: int) -> None:
    with get_connection() as conn:
        conn.execute(
            "UPDATE cleanup_schedule SET processed = 1 WHERE id = ?",
            (entry_id,),
        )
        conn.commit()
