#!/usr/bin/env python3
"""
Слушатель GitHub webhook (push): только stdlib, HMAC X-Hub-Signature-256,
ветка DEPLOY_BRANCH, фоновый запуск обёртки redeploy. GET /health -> JSON.
Порт по умолчанию 9848 — не пересекается с ai_parser (9847).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, unquote

DEFAULT_PORT = 9848


def _env(name: str, default: str | None = None) -> str:
    v = os.environ.get(name, default)
    if v is None or v == "":
        raise RuntimeError(f"Переменная окружения {name} не задана")
    return v


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _verify_signature(secret: bytes, body: bytes, header_val: str | None) -> bool:
    if not header_val or not header_val.startswith("sha256="):
        return False
    want = header_val[7:]
    digest = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(digest, want)


def _should_deploy_push(payload: dict[str, Any], branch: str) -> bool:
    ref = payload.get("ref")
    if ref != f"refs/heads/{branch}":
        return False
    if "commits" in payload or payload.get("head_commit") is not None:
        return True
    return False


_HOOK_PREFIX = "/hooks/avito-parser"


def _normalize_request_path(raw_path: str) -> str:
    p = unquote(urlparse(raw_path).path)
    if not p:
        return "/"
    while "//" in p:
        p = p.replace("//", "/")
    p = p.rstrip("/") or "/"
    return p


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), fmt % args))

    def _send(self, code: int, body: bytes, content_type: str = "application/json") -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = _normalize_request_path(self.path)
        health_paths = ("/", "/health", _HOOK_PREFIX, f"{_HOOK_PREFIX}/health")
        if path in health_paths:
            data = json.dumps(
                {
                    "status": "ok",
                    "service": "avito_parser_github_webhook",
                    "deploy_branch": os.environ.get("DEPLOY_BRANCH", "main"),
                },
                ensure_ascii=False,
            ).encode("utf-8")
            self._send(200, data)
            return
        sys.stderr.write(f"github_webhook_listener: 404 GET raw={self.path!r} norm={path!r}\n")
        self._send(404, b'{"error":"not_found"}')

    def do_POST(self) -> None:
        path = _normalize_request_path(self.path)
        if path not in ("/", "/webhook", _HOOK_PREFIX):
            sys.stderr.write(f"github_webhook_listener: 404 POST raw={self.path!r} norm={path!r}\n")
            self._send(404, b'{"error":"not_found"}')
            return

        secret = _env("GITHUB_WEBHOOK_SECRET").encode("utf-8")
        length = int(self.headers.get("Content-Length", "0"))
        if length > 8 * 1024 * 1024:
            self._send(413, b'{"error":"payload_too_large"}')
            return
        body = self.rfile.read(length)
        sig = self.headers.get("X-Hub-Signature-256")
        if not _verify_signature(secret, body, sig):
            self._send(401, b'{"error":"bad_signature"}')
            return

        event = self.headers.get("X-GitHub-Event", "")
        try:
            payload = json.loads(body.decode("utf-8")) if body else {}
        except json.JSONDecodeError:
            self._send(400, b'{"error":"invalid_json"}')
            return

        branch = os.environ.get("DEPLOY_BRANCH", "main")

        if event == "ping":
            self._send(202, b'{"status":"accepted","reason":"ping"}')
            return

        if event != "push":
            self._send(200, b'{"status":"ignored","reason":"not_push"}')
            return

        if not _should_deploy_push(payload, branch):
            self._send(200, b'{"status":"ignored","reason":"wrong_branch_or_empty"}')
            return

        wrapper = os.environ.get(
            "REDEPLOY_WRAPPER",
            str(_repo_root() / "deploy" / "avito-parser-redeploy-wrapper.sh"),
        )
        if not os.path.isfile(wrapper):
            self._send(500, b'{"error":"wrapper_missing"}')
            return

        env = os.environ.copy()
        try:
            subprocess.Popen(
                ["/bin/bash", wrapper],
                cwd=str(_repo_root()),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as e:
            self._send(500, json.dumps({"error": "spawn_failed", "detail": str(e)}).encode("utf-8"))
            return

        self._send(202, b'{"status":"accepted","reason":"push_deploy_queued"}')


def main() -> None:
    host = os.environ.get("WEBHOOK_LISTEN_HOST", "127.0.0.1")
    port = int(os.environ.get("WEBHOOK_LISTEN_PORT", str(DEFAULT_PORT)))
    _ = _env("GITHUB_WEBHOOK_SECRET")
    httpd = HTTPServer((host, port), Handler)
    sys.stderr.write(
        f"github_webhook_listener: listen={host}:{port} "
        f"POST / or {_HOOK_PREFIX}; GET /health or {_HOOK_PREFIX}/health\n"
    )
    httpd.serve_forever()


if __name__ == "__main__":
    main()
