from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
    AUTH_USERNAME = os.getenv("AUTH_USERNAME", "admin")
    AUTH_PASSWORD = os.getenv("AUTH_PASSWORD", "MDSjsa9123LAq21")
    ROUTERAI_API_KEY = os.getenv("ROUTERAI_API_KEY", "")
    ROUTERAI_BASE_URL = os.getenv("ROUTERAI_BASE_URL", "https://routerai.ru/api/v1")
    ROUTERAI_MODEL = os.getenv("ROUTERAI_MODEL", "google/gemini-3.1-flash-lite-preview")

    MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "10"))
    MAX_CONTENT_LENGTH = MAX_FILE_SIZE_MB * 1024 * 1024

    FILE_TTL_SECONDS = int(os.getenv("FILE_TTL_SECONDS", "86400"))
    DELETE_AFTER_DOWNLOAD_SECONDS = int(os.getenv("DELETE_AFTER_DOWNLOAD_SECONDS", "1800"))
    CLEANUP_INTERVAL_SECONDS = int(os.getenv("CLEANUP_INTERVAL_SECONDS", "300"))

    AI_REQUEST_TIMEOUT_SECONDS = int(os.getenv("AI_REQUEST_TIMEOUT_SECONDS", "45"))
    AI_RETRIES = int(os.getenv("AI_RETRIES", "2"))
    AI_RETRY_DELAY_SECONDS = float(os.getenv("AI_RETRY_DELAY_SECONDS", "1.5"))
    JOB_POLL_INTERVAL_SECONDS = float(os.getenv("JOB_POLL_INTERVAL_SECONDS", "1.0"))
    STALE_PROCESSING_SECONDS = int(os.getenv("STALE_PROCESSING_SECONDS", "7200"))

    STORAGE_DIR = BASE_DIR / "storage"
    UPLOAD_DIR = STORAGE_DIR / "uploads"
    RESULT_DIR = STORAGE_DIR / "results"
    LOG_DIR = BASE_DIR / "logs"
    PROMPT_FILE = BASE_DIR / "prompts" / "parse_description.txt"
    SQLITE_DB_PATH = Path(os.getenv("SQLITE_DB_PATH", str(BASE_DIR / "storage" / "jobs.db")))

    ALLOWED_EXTENSIONS = {"xlsx"}

    @classmethod
    def ensure_directories(cls) -> None:
        cls.STORAGE_DIR.mkdir(parents=True, exist_ok=True)
        cls.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        cls.RESULT_DIR.mkdir(parents=True, exist_ok=True)
        cls.LOG_DIR.mkdir(parents=True, exist_ok=True)
