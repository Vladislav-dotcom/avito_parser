from __future__ import annotations

import hmac
import logging
from pathlib import Path
from time import time
from typing import Optional
from uuid import uuid4

from flask import Flask, jsonify, redirect, render_template, request, send_file, session, url_for
from flask_cors import CORS
from werkzeug.utils import secure_filename

from config import Config
from services.cleanup_service import cleanup_expired_files, schedule_file_deletion
from services.db_service import init_db
from services.job_service import enqueue_parse_job, get_job_by_id
from services.logging_config import configure_logging
from services.supplier_service import (
    SupplierValidationError,
    create_supplier,
    get_all_suppliers,
    get_supplier,
)

logger = logging.getLogger(__name__)


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in Config.ALLOWED_EXTENSIONS


def _is_authenticated() -> bool:
    return bool(session.get("is_authenticated"))


def _is_api_request() -> bool:
    return request.path.startswith("/api/")


def _is_public_endpoint(endpoint: Optional[str]) -> bool:
    if endpoint is None:
        return False
    if endpoint == "static":
        return True
    return endpoint in {"login"}


def _build_job_status(job: dict) -> dict:
    processed_rows = int(job.get("processed_rows", 0) or 0)
    total_rows = int(job.get("total_rows", 0) or 0)
    progress_percent = int((processed_rows / total_rows) * 100) if total_rows else 0
    state = str(job.get("state", "queued"))
    is_finished = state == "finished"
    last_progress_at = job.get("last_progress_at") or job.get("started_at")
    stale_warning = False
    if state == "processing" and last_progress_at:
        stale_warning = (int(time()) - int(last_progress_at)) > Config.STALE_PROGRESS_SECONDS

    return {
        "job_id": job["id"],
        "state": state,
        "processed_rows": processed_rows,
        "total_rows": total_rows,
        "failed_rows": int(job.get("failed_rows", 0) or 0),
        "progress_percent": progress_percent,
        "error": job.get("error"),
        "is_finished": is_finished,
        "result_ready": bool(job.get("result_path")) and is_finished,
        "last_progress_at": last_progress_at,
        "stale_warning": stale_warning,
    }


def create_app() -> Flask:
    configure_logging()
    Config.ensure_directories()
    init_db()

    app = Flask(__name__)
    app.config.from_object(Config)
    CORS(app)

    @app.before_request
    def require_authentication():
        if _is_public_endpoint(request.endpoint):
            return None
        if _is_authenticated():
            return None
        if _is_api_request():
            return jsonify({"error": "Требуется авторизация."}), 401
        return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if _is_authenticated():
            return redirect(url_for("index"))

        error_message = None
        if request.method == "POST":
            username = str(request.form.get("username", ""))
            password = str(request.form.get("password", ""))
            valid_username = hmac.compare_digest(username, Config.AUTH_USERNAME)
            valid_password = hmac.compare_digest(password, Config.AUTH_PASSWORD)
            if valid_username and valid_password:
                session["is_authenticated"] = True
                return redirect(url_for("index"))
            error_message = "Неверный логин или пароль."

        return render_template("login.html", error_message=error_message)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/suppliers")
    def list_suppliers_api():
        suppliers = get_all_suppliers()
        return jsonify({"suppliers": suppliers})

    @app.post("/api/suppliers")
    def create_supplier_api():
        payload = request.get_json(silent=True) or {}
        name = str(payload.get("name", ""))
        try:
            supplier = create_supplier(name=name)
        except SupplierValidationError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"supplier": supplier}), 201

    @app.post("/api/upload")
    def upload_file():
        cleanup_expired_files()
        supplier_id = str(request.form.get("supplier_id", "")).strip()
        if not supplier_id:
            return jsonify({"error": "Выберите поставщика."}), 400
        if get_supplier(supplier_id) is None:
            return jsonify({"error": "Поставщик не найден."}), 400

        file = request.files.get("file")
        if file is None or file.filename is None or file.filename == "":
            return jsonify({"error": "Файл не выбран."}), 400
        if not _allowed_file(file.filename):
            return jsonify({"error": "Допустим только .xlsx файл."}), 400

        safe_name = secure_filename(file.filename)
        upload_name = f"{uuid4().hex}_{safe_name}"
        upload_path = Path(Config.UPLOAD_DIR) / upload_name
        file.save(upload_path)

        job_id = enqueue_parse_job(
            upload_path=upload_path,
            original_filename=file.filename,
            supplier_id=supplier_id,
        )
        logger.info("Файл поставлен в очередь", extra={"job_id": job_id})
        return jsonify({"job_id": job_id, "message": "Файл загружен. Анализ запущен."})

    @app.get("/api/status/<job_id>")
    def get_status(job_id: str):
        cleanup_expired_files()
        job = get_job_by_id(job_id)
        if job is None:
            return jsonify({"error": "Задача не найдена."}), 404
        return jsonify(_build_job_status(job))

    @app.get("/api/download/<job_id>")
    def download_result(job_id: str):
        cleanup_expired_files()
        job = get_job_by_id(job_id)
        if job is None:
            return jsonify({"error": "Задача не найдена."}), 404

        result_path_raw = job.get("result_path")
        if job.get("state") != "finished" or not result_path_raw:
            return jsonify({"error": "Результат пока не готов."}), 400

        result_path = Path(result_path_raw)
        if not result_path.exists():
            return jsonify({"error": "Файл результата не найден."}), 404

        upload_path_raw = job.get("upload_path")
        schedule_file_deletion(result_path, Config.DELETE_AFTER_DOWNLOAD_SECONDS)
        if upload_path_raw:
            schedule_file_deletion(Path(str(upload_path_raw)), Config.DELETE_AFTER_DOWNLOAD_SECONDS)

        download_name = f"{result_path.stem}.xlsx"
        return send_file(result_path, as_attachment=True, download_name=download_name)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
