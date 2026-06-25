from __future__ import annotations

from pathlib import Path
from typing import Optional

from services.db_service import claim_next_job, create_job, fetch_job


def enqueue_parse_job(upload_path: Path, original_filename: str) -> str:
    return create_job(
        upload_path=upload_path,
        original_filename=original_filename,
    )


def get_job_by_id(job_id: str) -> Optional[dict]:
    return fetch_job(job_id)


def claim_job_for_worker() -> Optional[dict]:
    return claim_next_job()
