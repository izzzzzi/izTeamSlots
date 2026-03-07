from __future__ import annotations

import base64
import json
import os
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Callable

import requests

from . import DATA_ROOT

CHATGPT_BACKEND_API = "https://chatgpt.com/backend-api"
AUTH_ISSUER = "https://auth.openai.com"
CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_USER_AGENT = "codex-cli/1.0.0"
NEAR_LIMIT_THRESHOLD = 90.0
EXPIRY_SKEW_SECONDS = 60


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _iso_now() -> str:
    return _utc_now().isoformat().replace("+00:00", "Z")


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    if not token or "." not in token:
        return {}
    parts = token.split(".")
    if len(parts) != 3:
        return {}

    payload = parts[1]
    missing_padding = len(payload) % 4
    if missing_padding:
        payload += "=" * (4 - missing_padding)

    try:
        decoded = base64.urlsafe_b64decode(payload.encode("utf-8"))
        data = json.loads(decoded.decode("utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _parse_jwt_exp(token: str) -> datetime | None:
    payload = _decode_jwt_payload(token)
    exp = payload.get("exp")
    if not isinstance(exp, (int, float)):
        return None
    return datetime.fromtimestamp(exp, tz=UTC)


def _parse_id_token_claims(token: str) -> tuple[str | None, str | None]:
    payload = _decode_jwt_payload(token)
    email = payload.get("email") if isinstance(payload.get("email"), str) else None
    auth_claims = payload.get("https://api.openai.com/auth")
    account_id = None
    if isinstance(auth_claims, dict):
        raw_account_id = auth_claims.get("chatgpt_account_id")
        if isinstance(raw_account_id, str):
            account_id = raw_account_id
    return email, account_id


def _is_token_expiring(token: str) -> bool:
    expires_at = _parse_jwt_exp(token)
    if expires_at is None:
        return False
    return expires_at <= _utc_now() + timedelta(seconds=EXPIRY_SKEW_SECONDS)


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile("w", encoding="utf-8", dir=str(path.parent), delete=False) as fh:
        tmp_path = Path(fh.name)
        fh.write(content)
    try:
        os.replace(tmp_path, path)
        if os.name != "nt":
            os.chmod(path, 0o600)
    finally:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)


class CodexSwitcherService:
    def __init__(
        self,
        *,
        codex_dir: Path | None = None,
        auth_path: Path | None = None,
        session_factory: Callable[[], requests.Session] | None = None,
    ) -> None:
        self.codex_dir = codex_dir or (DATA_ROOT / "codex")
        self.auth_path = auth_path or self._resolve_codex_home() / "auth.json"
        self._session_factory = session_factory or requests.Session
        self._runtime: dict[str, dict[str, Any]] = {}
        self._status: dict[str, Any] = {
            "enabled": self.enabled,
            "interval_minutes": self.interval_minutes,
            "last_run_at": None,
            "last_switch_at": None,
            "active_email": None,
            "last_error": None,
        }
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def enabled(self) -> bool:
        return _parse_bool(os.environ.get("CODEX_SWITCHER_ENABLED"), default=False)

    @property
    def interval_minutes(self) -> int:
        return _parse_int(os.environ.get("CODEX_SWITCHER_INTERVAL_MINUTES"), default=15)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._scheduler_loop, daemon=True, name="codex-switcher")
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=2)
        self._thread = None

    def get_state(self) -> dict[str, Any]:
        with self._lock:
            accounts = self._compose_rows(self._load_accounts())
            active = self._detect_active_account(accounts)
            for account in accounts:
                account["is_active"] = account["email"] == active
            self._status["active_email"] = active
            self._status["enabled"] = self.enabled
            self._status["interval_minutes"] = self.interval_minutes
            return {
                "items": accounts,
                "status": dict(self._status),
            }

    def refresh_now(self, *, auto_switch: bool) -> dict[str, Any]:
        with self._lock:
            summary = self._refresh_all(auto_switch=auto_switch)
            return {
                "status": dict(self._status),
                "summary": summary,
            }

    def switch_now(self, email: str) -> dict[str, Any]:
        with self._lock:
            accounts = self._load_accounts()
            target = next((account for account in accounts if account["email"] == email), None)
            if not target:
                raise RuntimeError(f"Codex account not found: {email}")

            refreshed = self._refresh_account(target, refresh_usage=False)
            runtime = self._runtime.get(email, {})
            if runtime.get("token_status") == "invalid":
                raise RuntimeError(runtime.get("last_error") or f"Token refresh failed for {email}")
            for index, account in enumerate(accounts):
                if account["email"] == email:
                    accounts[index] = refreshed
                    break
            self._activate_account(refreshed)
            rows = self._compose_rows(accounts)
            active = self._detect_active_account(rows)
            for row in rows:
                row["is_active"] = row["email"] == active
            self._status["active_email"] = active
            return {"active_email": active, "item": next((row for row in rows if row["email"] == email), None)}

    def pick_first_ready(self) -> dict[str, Any]:
        with self._lock:
            summary = self._refresh_all(auto_switch=False)
            accounts = self._load_accounts()
            rows = self._compose_rows(accounts)
            active = self._detect_active_account(accounts)
            candidate = self._pick_first_ready(rows, exclude_email=None)
            if not candidate:
                return {"active_email": active, "switched": False}
            target = next((account for account in accounts if account["email"] == candidate["email"]), None)
            if not target:
                return {"active_email": active, "switched": False}
            self._activate_account(target)
            rows = self._compose_rows(self._load_accounts())
            active = self._detect_active_account(self._load_accounts())
            for row in rows:
                row["is_active"] = row["email"] == active
            self._status["active_email"] = active
            return {"active_email": active, "switched": True, "summary": summary}

    def _scheduler_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                with self._lock:
                    self._status["enabled"] = self.enabled
                    self._status["interval_minutes"] = self.interval_minutes
                if self.enabled:
                    self.refresh_now(auto_switch=True)
            except Exception as exc:
                with self._lock:
                    self._status["last_error"] = str(exc)
            wait_seconds = self.interval_minutes * 60 if self.enabled else 30
            if self._stop_event.wait(timeout=max(1, wait_seconds)):
                break

    def _resolve_codex_home(self) -> Path:
        value = os.environ.get("CODEX_HOME")
        if value:
            return Path(value)
        return Path.home() / ".codex"

    def _load_accounts(self) -> list[dict[str, Any]]:
        self.codex_dir.mkdir(parents=True, exist_ok=True)
        accounts: list[dict[str, Any]] = []
        known = set()

        for path in sorted(self.codex_dir.glob("codex-*.json"), key=lambda item: item.name.lower()):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(raw, dict):
                continue

            email = raw.get("email")
            access_token = raw.get("access_token")
            refresh_token = raw.get("refresh_token")
            if not isinstance(email, str) or not email or not isinstance(access_token, str) or not access_token:
                continue

            account = {
                "email": email,
                "id_token": raw.get("id_token") if isinstance(raw.get("id_token"), str) else "",
                "access_token": access_token,
                "refresh_token": refresh_token if isinstance(refresh_token, str) else "",
                "account_id": raw.get("account_id") if isinstance(raw.get("account_id"), str) else "",
                "expired": raw.get("expired") if isinstance(raw.get("expired"), str) else "",
                "last_refresh": raw.get("last_refresh") if isinstance(raw.get("last_refresh"), str) else "",
                "path": path,
                "type": raw.get("type") if isinstance(raw.get("type"), str) else "codex",
            }
            accounts.append(account)
            known.add(email)

        stale = [email for email in self._runtime if email not in known]
        for email in stale:
            del self._runtime[email]

        return accounts

    def _compose_rows(self, accounts: list[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for account in accounts:
            runtime = self._runtime.get(account["email"], {})
            row = {
                "email": account["email"],
                "is_active": False,
                "primary_used_percent": runtime.get("primary_used_percent"),
                "primary_resets_at": runtime.get("primary_resets_at"),
                "secondary_used_percent": runtime.get("secondary_used_percent"),
                "secondary_resets_at": runtime.get("secondary_resets_at"),
                "usage_status": runtime.get("usage_status", "idle"),
                "token_status": runtime.get("token_status", self._token_status_from_account(account)),
                "last_checked_at": runtime.get("last_checked_at"),
                "last_error": runtime.get("last_error"),
                "near_limit": runtime.get("near_limit", False),
            }
            rows.append(row)
        return rows

    def _token_status_from_account(self, account: dict[str, Any]) -> str:
        if _is_token_expiring(account.get("access_token", "")):
            return "expiring"
        return "fresh"

    def _read_auth_json(self) -> dict[str, Any] | None:
        if not self.auth_path.exists():
            return None
        try:
            data = json.loads(self.auth_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        return data if isinstance(data, dict) else None

    def _detect_active_account(self, accounts: list[dict[str, Any]]) -> str | None:
        auth = self._read_auth_json()
        if not auth:
            return None
        tokens = auth.get("tokens")
        if not isinstance(tokens, dict):
            return None

        current_access = tokens.get("access_token") if isinstance(tokens.get("access_token"), str) else ""
        current_account_id = tokens.get("account_id") if isinstance(tokens.get("account_id"), str) else ""
        id_token = tokens.get("id_token") if isinstance(tokens.get("id_token"), str) else ""
        email, token_account_id = _parse_id_token_claims(id_token)
        current_account_id = current_account_id or token_account_id or ""

        for account in accounts:
            if current_account_id and account.get("account_id") == current_account_id:
                return account["email"]
        for account in accounts:
            if current_access and account.get("access_token") == current_access:
                return account["email"]
        if email:
            for account in accounts:
                if account["email"] == email:
                    return account["email"]
        return None

    def _refresh_all(self, *, auto_switch: bool) -> dict[str, Any]:
        accounts = self._load_accounts()
        active_email = self._detect_active_account(accounts)
        checked = 0
        current_near_limit = False

        for index, account in enumerate(accounts):
            refreshed = self._refresh_account(account, refresh_usage=True)
            accounts[index] = refreshed
            checked += 1
            if refreshed["email"] == active_email:
                current_near_limit = bool(self._runtime.get(refreshed["email"], {}).get("near_limit"))

        rows = self._compose_rows(accounts)
        active_email = self._detect_active_account(accounts) or active_email
        for row in rows:
            row["is_active"] = row["email"] == active_email

        switched_to = None
        if auto_switch and self.enabled:
            needs_switch = False
            if active_email is None:
                needs_switch = True
            else:
                active_runtime = self._runtime.get(active_email, {})
                token_status = active_runtime.get("token_status")
                needs_switch = bool(active_runtime.get("near_limit")) or token_status == "invalid"
            if needs_switch:
                candidate = self._pick_first_ready(rows, exclude_email=active_email)
                if candidate:
                    target = next((account for account in accounts if account["email"] == candidate["email"]), None)
                    if target:
                        self._activate_account(target)
                        switched_to = target["email"]
                        active_email = target["email"]
                    for row in rows:
                        row["is_active"] = row["email"] == active_email

        self._status["enabled"] = self.enabled
        self._status["interval_minutes"] = self.interval_minutes
        self._status["last_run_at"] = _iso_now()
        self._status["active_email"] = active_email
        if switched_to:
            self._status["last_switch_at"] = _iso_now()
        return {
            "checked": checked,
            "active_email": active_email,
            "switched_to": switched_to,
            "current_near_limit": current_near_limit,
        }

    def _pick_first_ready(self, rows: list[dict[str, Any]], exclude_email: str | None) -> dict[str, Any] | None:
        candidates = sorted(rows, key=lambda item: item["email"].lower())
        for row in candidates:
            if exclude_email and row["email"] == exclude_email:
                continue
            if row.get("usage_status") != "ok":
                continue
            if row.get("token_status") == "invalid":
                continue
            if row.get("near_limit"):
                continue
            return row
        return None

    def _refresh_account(self, account: dict[str, Any], *, refresh_usage: bool) -> dict[str, Any]:
        email = account["email"]
        runtime = self._runtime.setdefault(email, {})
        runtime["last_error"] = None
        runtime["token_status"] = self._token_status_from_account(account)

        try:
            if _is_token_expiring(account["access_token"]):
                account = self._refresh_tokens(account)
                runtime["token_status"] = "refreshed"
            else:
                runtime["token_status"] = "fresh"
        except Exception as exc:
            runtime["last_error"] = str(exc)
            runtime["usage_status"] = "error"
            runtime["near_limit"] = False
            runtime["last_checked_at"] = _iso_now()
            runtime["token_status"] = "invalid"
            return account

        if refresh_usage:
            try:
                usage = self._fetch_usage(account)
                runtime["usage_status"] = "ok"
                runtime["primary_used_percent"] = usage.get("primary_used_percent")
                runtime["primary_resets_at"] = usage.get("primary_resets_at")
                runtime["secondary_used_percent"] = usage.get("secondary_used_percent")
                runtime["secondary_resets_at"] = usage.get("secondary_resets_at")
                runtime["near_limit"] = self._is_near_limit(runtime["primary_used_percent"])
                runtime["last_checked_at"] = _iso_now()
                runtime["last_error"] = None
            except Exception as exc:
                runtime["usage_status"] = "error"
                runtime["near_limit"] = False
                runtime["last_checked_at"] = _iso_now()
                runtime["last_error"] = str(exc)
        else:
            runtime["usage_status"] = runtime.get("usage_status", "idle")

        return account

    def _refresh_tokens(self, account: dict[str, Any]) -> dict[str, Any]:
        refresh_token = account.get("refresh_token") or ""
        if not refresh_token:
            raise RuntimeError(f"Missing refresh_token for {account['email']}")

        session = self._session_factory()
        response = session.post(
            f"{AUTH_ISSUER}/oauth/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": CLIENT_ID,
            },
            timeout=20,
        )
        if not response.ok:
            raise RuntimeError(f"Token refresh failed: {response.status_code}")

        payload = response.json()
        if not isinstance(payload, dict) or not isinstance(payload.get("access_token"), str):
            raise RuntimeError("Token refresh returned invalid payload")

        next_id_token = payload.get("id_token") if isinstance(payload.get("id_token"), str) else account.get("id_token", "")
        next_access_token = payload["access_token"]
        next_refresh_token = payload.get("refresh_token") if isinstance(payload.get("refresh_token"), str) else refresh_token
        email_from_token, account_id_from_token = _parse_id_token_claims(next_id_token)

        updated = dict(account)
        updated["id_token"] = next_id_token
        updated["access_token"] = next_access_token
        updated["refresh_token"] = next_refresh_token
        updated["account_id"] = account_id_from_token or account.get("account_id", "")
        updated["email"] = email_from_token or account["email"]
        updated["last_refresh"] = _iso_now()
        exp = _parse_jwt_exp(next_access_token)
        updated["expired"] = exp.isoformat().replace("+00:00", "Z") if exp else account.get("expired", "")

        self._write_codex_file(updated)

        active_email = self._detect_active_account([updated])
        if active_email == updated["email"]:
            self._activate_account(updated, record_switch=False)

        return updated

    def _fetch_usage(self, account: dict[str, Any]) -> dict[str, Any]:
        session = self._session_factory()
        headers = {
            "Authorization": f"Bearer {account['access_token']}",
            "User-Agent": CODEX_USER_AGENT,
        }
        if account.get("account_id"):
            headers["chatgpt-account-id"] = account["account_id"]

        response = session.get(
            f"{CHATGPT_BACKEND_API}/wham/usage",
            headers=headers,
            timeout=20,
        )
        if response.status_code == 401 and account.get("refresh_token"):
            account = self._refresh_tokens(account)
            headers["Authorization"] = f"Bearer {account['access_token']}"
            if account.get("account_id"):
                headers["chatgpt-account-id"] = account["account_id"]
            response = session.get(
                f"{CHATGPT_BACKEND_API}/wham/usage",
                headers=headers,
                timeout=20,
            )
        if not response.ok:
            raise RuntimeError(f"Usage request failed: {response.status_code}")

        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Usage response is not a JSON object")

        rate_limit = payload.get("rate_limit") if isinstance(payload.get("rate_limit"), dict) else {}
        primary = rate_limit.get("primary_window") if isinstance(rate_limit.get("primary_window"), dict) else {}
        secondary = rate_limit.get("secondary_window") if isinstance(rate_limit.get("secondary_window"), dict) else {}
        return {
            "primary_used_percent": self._as_float(primary.get("used_percent")),
            "primary_resets_at": primary.get("reset_at") if isinstance(primary.get("reset_at"), str) else None,
            "secondary_used_percent": self._as_float(secondary.get("used_percent")),
            "secondary_resets_at": secondary.get("reset_at") if isinstance(secondary.get("reset_at"), str) else None,
        }

    def _as_float(self, value: Any) -> float | None:
        if isinstance(value, (int, float)):
            return float(value)
        return None

    def _is_near_limit(self, value: float | None) -> bool:
        if value is None:
            return False
        return value >= NEAR_LIMIT_THRESHOLD

    def _activate_account(self, account: dict[str, Any], *, record_switch: bool = True) -> None:
        auth_json = {
            "auth_mode": "chatgpt",
            "OPENAI_API_KEY": None,
            "tokens": {
                "id_token": account.get("id_token", ""),
                "access_token": account.get("access_token", ""),
                "refresh_token": account.get("refresh_token", ""),
                "account_id": account.get("account_id", ""),
            },
            "last_refresh": _iso_now(),
        }
        _atomic_write_text(self.auth_path, json.dumps(auth_json, indent=2, ensure_ascii=False) + "\n")
        self._status["active_email"] = account["email"]
        if record_switch:
            self._status["last_switch_at"] = _iso_now()

    def _write_codex_file(self, account: dict[str, Any]) -> None:
        payload = {
            "id_token": account.get("id_token", ""),
            "access_token": account.get("access_token", ""),
            "refresh_token": account.get("refresh_token", ""),
            "account_id": account.get("account_id", ""),
            "last_refresh": account.get("last_refresh") or _iso_now(),
            "email": account.get("email", ""),
            "type": account.get("type", "codex"),
            "expired": account.get("expired", ""),
        }
        path = Path(account["path"])
        _atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
