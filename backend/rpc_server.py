from __future__ import annotations

import json
import os
import sys
import threading
import traceback
from pathlib import Path
from typing import Any

from .file_logger import FileLogger
from .jobs import JobManager
from .rpc_protocol import (
    RPCError,
    RPCRequest,
    make_error_response,
    make_event,
    make_success_response,
    parse_request,
)
from .ui_facade import UIFacade


class RPCServer:
    def __init__(self) -> None:
        self.logger = FileLogger()
        self.facade = UIFacade()
        self._out_lock = threading.Lock()
        self.jobs = JobManager(self.emit_event, file_logger=self.logger)
        self.logger.info("RPC server initialized")

    def emit_event(self, event: str, data: dict[str, Any]) -> None:
        self._write_json(make_event(event, data))

    def _write_json(self, payload: dict[str, Any]) -> None:
        line = json.dumps(payload, ensure_ascii=False)
        with self._out_lock:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()

    def _as_str_param(self, params: dict[str, Any], key: str) -> str:
        value = params.get(key)
        if not isinstance(value, str) or not value:
            raise RPCError(-32602, "Invalid params", {"details": f"'{key}' must be non-empty string"})
        return value

    def _as_int_param(self, params: dict[str, Any], key: str) -> int:
        value = params.get(key)
        if not isinstance(value, int):
            raise RPCError(-32602, "Invalid params", {"details": f"'{key}' must be integer"})
        return value

    def _run_job(self, title: str, fn):
        return self.jobs.start(title, fn)

    _SETTINGS_KEYS = [
        ("BOOMLIFY_API_KEY", "Boomlify API ключ"),
        ("BOOMLIFY_DOMAIN", "Домен временной почты"),
        ("BOOMLIFY_TIME", "Время жизни ящика"),
        ("SLOT_MAIL_PROVIDER", "Провайдер почты для слотов"),
        ("MAIL_PROVIDER", "Провайдер почты для админов"),
    ]

    @staticmethod
    def _settings_path() -> Path:
        return Path.home() / ".izteamslots" / ".env"

    def _get_settings(self) -> dict[str, Any]:
        items = []
        for key, label in self._SETTINGS_KEYS:
            value = os.environ.get(key, "")
            masked = ""
            if value:
                masked = value[:4] + "***" + value[-4:] if len(value) > 12 else "***"
            items.append({"key": key, "label": label, "masked": masked})
        return {"items": items, "path": str(self._settings_path())}

    def _set_setting(self, key: str, value: str) -> None:
        allowed = {k for k, _ in self._SETTINGS_KEYS}
        if key not in allowed:
            raise RPCError(-32602, "Unknown setting", {"key": key})

        env_path = self._settings_path()
        env_path.parent.mkdir(parents=True, exist_ok=True)

        # Read existing lines
        lines: list[str] = []
        if env_path.is_file():
            lines = env_path.read_text(encoding="utf-8").splitlines()

        # Update or append
        found = False
        for i, line in enumerate(lines):
            if line.startswith(f"{key}=") or line.startswith(f"{key} ="):
                lines[i] = f"{key}={value}"
                found = True
                break
        if not found:
            lines.append(f"{key}={value}")

        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

        # Update runtime env
        if value:
            os.environ[key] = value
        elif key in os.environ:
            del os.environ[key]

    def _handle_request(self, req: RPCRequest) -> dict[str, Any]:
        m = req.method
        p = req.params

        if m == "ping":
            return make_success_response(req.request_id, {"pong": True})

        if m == "state.get":
            return make_success_response(req.request_id, self.facade.get_state())

        if m == "admin.add":
            email = self._as_str_param(p, "email")
            password = self._as_str_param(p, "password")
            item = self.facade.add_admin(email, password)
            return make_success_response(req.request_id, {"item": item})

        if m == "job.add_admin_manual":
            job_id = self._run_job(
                "Ручное добавление админа",
                lambda ctx: self.facade.add_admin_manual(ctx.log),
            )
            return make_success_response(req.request_id, {"job_id": job_id})

        if m == "admin.delete":
            email = self._as_str_param(p, "email")
            self.facade.delete_admin(email)
            return make_success_response(req.request_id, {"deleted": True})

        if m == "worker.delete":
            email = self._as_str_param(p, "email")
            self.facade.delete_worker(email)
            return make_success_response(req.request_id, {"deleted": True})

        if m == "job.login_admin":
            email = self._as_str_param(p, "email")
            job_id = self._run_job(
                f"Логин админа: {email}",
                lambda ctx: self.facade.login_admin(email, ctx.log),
            )
            return make_success_response(req.request_id, {"job_id": job_id})

        if m == "job.login_admin_manual":
            email = self._as_str_param(p, "email")
            job_id = self._run_job(
                f"Ручной логин админа: {email}",
                lambda ctx: self.facade.login_admin_manual(email, ctx.log),
            )
            return make_success_response(req.request_id, {"job_id": job_id})

        if m == "job.open_admin_browser":
            email = self._as_str_param(p, "email")
            job_id = self._run_job(
                f"Браузер админа: {email}",
                lambda ctx: self.facade.open_admin_browser(email, ctx.log),
            )
            return make_success_response(req.request_id, {"job_id": job_id})

        if m == "job.run_slots":
            admin_email = self._as_str_param(p, "admin_email")
            count = self._as_int_param(p, "count")
            if count <= 0:
                raise RPCError(-32602, "Invalid params", {"details": "'count' must be > 0"})
            job_id = self._run_job(
                f"Пайплайн слотов ({admin_email})",
                lambda ctx: self.facade.run_slots_pipeline(
                    admin_email,
                    count,
                    ctx.log,
                    progress=ctx.progress,
                ),
            )
            return make_success_response(req.request_id, {"job_id": job_id})

        if m == "job.relogin_worker":
            email = self._as_str_param(p, "email")
            job_id = self._run_job(
                f"Перелогин: {email}",
                lambda ctx: self.facade.relogin_worker_email(email, ctx.log),
            )
            return make_success_response(req.request_id, {"job_id": job_id})

        if m == "job.relogin_all_workers":
            job_id = self._run_job(
                "Перелогин всех слотов",
                lambda ctx: self.facade.relogin_all_workers(ctx.log, progress=ctx.progress),
            )
            return make_success_response(req.request_id, {"job_id": job_id})

        if m == "job.open_worker_browser":
            email = self._as_str_param(p, "email")
            job_id = self._run_job(
                f"Браузер слота: {email}",
                lambda ctx: self.facade.open_worker_browser(email, ctx.log),
            )
            return make_success_response(req.request_id, {"job_id": job_id})

        if m == "settings.get":
            return make_success_response(req.request_id, self._get_settings())

        if m == "settings.set":
            key = self._as_str_param(p, "key")
            value = p.get("value")
            if not isinstance(value, str):
                raise RPCError(-32602, "Invalid params", {"details": "'value' must be string"})
            self._set_setting(key, value)
            return make_success_response(req.request_id, {"ok": True})

        if m == "shutdown":
            self.facade.shutdown()
            return make_success_response(req.request_id, {"ok": True})

        raise RPCError(-32601, "Method not found", {"method": m})

    def serve(self) -> None:
        for raw in sys.stdin:
            line = raw.strip()
            if not line:
                continue

            req: RPCRequest | None = None
            try:
                req = parse_request(line)
                response = self._handle_request(req)
            except RPCError as e:
                self.logger.error(f"RPC error for request {req.request_id if req else 'unknown'}: {e}")
                request_id = req.request_id if req else "unknown"
                if request_id == "unknown":
                    try:
                        maybe = json.loads(line)
                        if isinstance(maybe, dict) and isinstance(maybe.get("id"), str):
                            request_id = maybe["id"]
                    except Exception:
                        pass
                response = make_error_response(request_id, e)
            except Exception as e:
                tb = traceback.format_exc()
                self.logger.error(f"Unhandled server error: {e}", traceback_text=tb)
                request_id = req.request_id if req else "unknown"
                response = make_error_response(
                    request_id,
                    RPCError(
                        -32000,
                        "Server error",
                        {"details": str(e)},
                    ),
                )

            self._write_json(response)

        self.facade.shutdown()
        self.logger.info("RPC server stopped")


def main() -> int:
    from pathlib import Path

    from dotenv import load_dotenv

    # Priority: ~/.izteamslots/.env > CWD/.env > package .env
    home_env = Path.home() / ".izteamslots" / ".env"
    cwd_env = Path.cwd() / ".env"
    pkg_env = Path(__file__).resolve().parent.parent / ".env"

    for env_path in (home_env, cwd_env, pkg_env):
        if env_path.is_file():
            load_dotenv(env_path)
            break

    server = RPCServer()
    server.serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
