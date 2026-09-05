#!/usr/bin/env python3
"""Minimal GitHub webhook receiver that redeploys this project on push.

No third-party dependencies (stdlib only) so it can run under aaPanel's
Process Guard Manager (or any process supervisor) without a virtualenv.

Configuration is via environment variables:
  WEBHOOK_SECRET  - required. Must match the GitHub webhook's secret.
  REPO_DIR        - path to the git checkout (default: this script's repo root).
  BRANCH          - branch to track (default: "main").
  PORT            - port to listen on (default: 9000).
  LOG_FILE        - path to the deploy log (default: <REPO_DIR>/deploy.log).

On a push to BRANCH, it runs in the background:
  git fetch origin BRANCH
  git reset --hard origin/BRANCH
  docker compose up -d --build

Bind this only to 127.0.0.1 and put it behind an aaPanel reverse-proxy
site with HTTPS enabled - never expose it directly on a public port.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO_DIR = Path(os.environ.get("REPO_DIR") or Path(__file__).resolve().parent.parent)
BRANCH = os.environ.get("BRANCH", "main")
PORT = int(os.environ.get("PORT", "9000"))
SECRET = os.environ.get("WEBHOOK_SECRET", "")
LOG_FILE = Path(os.environ.get("LOG_FILE") or (REPO_DIR / "deploy.log"))

_lock = threading.Lock()


def log(message: str) -> None:
    line = f"[{datetime.now(timezone.utc).isoformat()}] {message}\n"
    with _lock:
        with open(LOG_FILE, "a", encoding="utf-8") as handle:
            handle.write(line)
    print(line, end="")


def run_deploy() -> None:
    with _lock:
        pass  # ensure log writes above are flushed before the long deploy starts
    steps = [
        ["git", "-C", str(REPO_DIR), "fetch", "origin", BRANCH],
        ["git", "-C", str(REPO_DIR), "reset", "--hard", f"origin/{BRANCH}"],
        ["docker", "compose", "-f", str(REPO_DIR / "docker-compose.yml"), "--env-file", str(REPO_DIR / ".env"), "up", "-d", "--build"],
    ]
    for step in steps:
        log("$ " + " ".join(step))
        result = subprocess.run(step, cwd=REPO_DIR, capture_output=True, text=True)
        if result.stdout:
            log(result.stdout.strip())
        if result.stderr:
            log(result.stderr.strip())
        if result.returncode != 0:
            log(f"DEPLOY FAILED at step: {' '.join(step)} (exit {result.returncode})")
            return
    log("DEPLOY OK")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # noqa: A002 - silence default stderr access log
        pass

    def _respond(self, status: int, body: str) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):  # noqa: N802 - required by BaseHTTPRequestHandler
        self._respond(200, "ok")

    def do_POST(self):  # noqa: N802 - required by BaseHTTPRequestHandler
        if not SECRET:
            self._respond(500, "WEBHOOK_SECRET not configured")
            return
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        signature = self.headers.get("X-Hub-Signature-256", "")
        expected = "sha256=" + hmac.new(SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            log("REJECTED: invalid signature")
            self._respond(401, "invalid signature")
            return
        try:
            payload = json.loads(body or b"{}")
        except json.JSONDecodeError:
            payload = {}
        ref = payload.get("ref", "")
        if ref != f"refs/heads/{BRANCH}":
            self._respond(200, f"ignored ref {ref!r}")
            return
        self._respond(202, "deploy started")
        threading.Thread(target=run_deploy, daemon=True).start()


def main() -> None:
    if not SECRET:
        raise SystemExit("WEBHOOK_SECRET environment variable is required")
    log(f"listening on 127.0.0.1:{PORT}, repo={REPO_DIR}, branch={BRANCH}")
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
