from __future__ import annotations

import base64
import json
import os
import tempfile
import unittest
from pathlib import Path

from backend.codex_switcher import CodexSwitcherService


def make_jwt(payload: dict) -> str:
    header = {"alg": "none", "typ": "JWT"}
    parts = []
    for item in (header, payload, "sig"):
        if isinstance(item, str):
            encoded = base64.urlsafe_b64encode(item.encode("utf-8")).decode("utf-8").rstrip("=")
        else:
            encoded = base64.urlsafe_b64encode(json.dumps(item).encode("utf-8")).decode("utf-8").rstrip("=")
        parts.append(encoded)
    return ".".join(parts)


def write_codex(path: Path, email: str, account_id: str, access_token: str, refresh_token: str) -> None:
    payload = {
        "id_token": make_jwt({
            "email": email,
            "https://api.openai.com/auth": {"chatgpt_account_id": account_id},
        }),
        "access_token": access_token,
        "refresh_token": refresh_token,
        "account_id": account_id,
        "last_refresh": "2026-03-07T00:00:00Z",
        "email": email,
        "type": "codex",
        "expired": "2026-03-08T00:00:00Z",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def write_auth(path: Path, account_id: str, access_token: str, email: str) -> None:
    payload = {
        "auth_mode": "chatgpt",
        "OPENAI_API_KEY": None,
        "tokens": {
            "id_token": make_jwt({
                "email": email,
                "https://api.openai.com/auth": {"chatgpt_account_id": account_id},
            }),
            "access_token": access_token,
            "refresh_token": "rt-active",
            "account_id": account_id,
        },
        "last_refresh": "2026-03-07T00:00:00Z",
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


class FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> dict:
        return self._payload


class FakeSession:
    def __init__(
        self,
        usage_by_account: dict[str, dict],
        refresh_by_token: dict[str, dict] | None = None,
        *,
        usage_401_once: set[str] | None = None,
    ) -> None:
        self.usage_by_account = usage_by_account
        self.refresh_by_token = refresh_by_token or {}
        self._usage_401_once = usage_401_once or set()

    def get(self, url: str, *, headers: dict, timeout: int) -> FakeResponse:
        account_id = headers.get("chatgpt-account-id", "")
        if account_id in self._usage_401_once:
            self._usage_401_once.discard(account_id)
            return FakeResponse(401, {"error": "unauthorized"})
        payload = self.usage_by_account.get(account_id)
        if payload is None:
            return FakeResponse(404, {"error": "not found"})
        return FakeResponse(200, payload)

    def post(self, url: str, *, data: dict, timeout: int) -> FakeResponse:
        refresh_token = data.get("refresh_token", "")
        payload = self.refresh_by_token.get(refresh_token)
        if payload is None:
            return FakeResponse(400, {"error": "missing"})
        return FakeResponse(200, payload)


class CodexSwitcherServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.codex_dir = Path(self.temp_dir.name) / "codex"
        self.auth_path = Path(self.temp_dir.name) / "auth.json"
        self.codex_dir.mkdir(parents=True, exist_ok=True)
        self._old_enabled = os.environ.get("CODEX_SWITCHER_ENABLED")
        self._old_interval = os.environ.get("CODEX_SWITCHER_INTERVAL_MINUTES")
        os.environ["CODEX_SWITCHER_ENABLED"] = "1"
        os.environ["CODEX_SWITCHER_INTERVAL_MINUTES"] = "15"

    def tearDown(self) -> None:
        if self._old_enabled is None:
            os.environ.pop("CODEX_SWITCHER_ENABLED", None)
        else:
            os.environ["CODEX_SWITCHER_ENABLED"] = self._old_enabled

        if self._old_interval is None:
            os.environ.pop("CODEX_SWITCHER_INTERVAL_MINUTES", None)
        else:
            os.environ["CODEX_SWITCHER_INTERVAL_MINUTES"] = self._old_interval
        self.temp_dir.cleanup()

    def test_refresh_switches_away_from_near_limit_active_account(self) -> None:
        token_a = make_jwt({"exp": 4102444800})
        token_b = make_jwt({"exp": 4102444800})
        write_codex(self.codex_dir / "codex-a.json", "a@example.com", "acc-a", token_a, "rt-a")
        write_codex(self.codex_dir / "codex-b.json", "b@example.com", "acc-b", token_b, "rt-b")
        write_auth(self.auth_path, "acc-a", token_a, "a@example.com")

        usage = {
            "acc-a": {
                "plan_type": "team",
                "rate_limit": {
                    "primary_window": {"used_percent": 95, "reset_at": "2026-03-07T05:00:00Z"},
                    "secondary_window": {"used_percent": 10, "reset_at": "2026-03-08T05:00:00Z"},
                },
            },
            "acc-b": {
                "plan_type": "team",
                "rate_limit": {
                    "primary_window": {"used_percent": 20, "reset_at": "2026-03-07T05:00:00Z"},
                    "secondary_window": {"used_percent": 10, "reset_at": "2026-03-08T05:00:00Z"},
                },
            },
        }
        service = CodexSwitcherService(
            codex_dir=self.codex_dir,
            auth_path=self.auth_path,
            session_factory=lambda: FakeSession(usage),
        )

        result = service.refresh_now(auto_switch=True)

        self.assertEqual(result["summary"]["switched_to"], "b@example.com")
        active = json.loads(self.auth_path.read_text(encoding="utf-8"))
        self.assertEqual(active["tokens"]["account_id"], "acc-b")
        state = service.get_state()
        rows = {item["email"]: item for item in state["items"]}
        self.assertTrue(rows["b@example.com"]["is_active"])
        self.assertTrue(rows["a@example.com"]["near_limit"])

    def test_refresh_updates_expiring_token_and_active_auth_json(self) -> None:
        old_access = make_jwt({"exp": 1})
        new_access = make_jwt({"exp": 4102444800})
        new_id = make_jwt({
            "email": "refresh@example.com",
            "https://api.openai.com/auth": {"chatgpt_account_id": "acc-refresh"},
        })
        write_codex(self.codex_dir / "codex-refresh.json", "refresh@example.com", "acc-refresh", old_access, "rt-refresh")
        write_auth(self.auth_path, "acc-refresh", old_access, "refresh@example.com")

        usage = {
            "acc-refresh": {
                "plan_type": "team",
                "rate_limit": {
                    "primary_window": {"used_percent": 11, "reset_at": "2026-03-07T05:00:00Z"},
                    "secondary_window": {"used_percent": 3, "reset_at": "2026-03-08T05:00:00Z"},
                },
            },
        }
        refresh_payload = {
            "rt-refresh": {
                "id_token": new_id,
                "access_token": new_access,
                "refresh_token": "rt-refresh-2",
            },
        }
        service = CodexSwitcherService(
            codex_dir=self.codex_dir,
            auth_path=self.auth_path,
            session_factory=lambda: FakeSession(usage, refresh_payload),
        )

        service.refresh_now(auto_switch=False)

        codex_data = json.loads((self.codex_dir / "codex-refresh.json").read_text(encoding="utf-8"))
        auth_data = json.loads(self.auth_path.read_text(encoding="utf-8"))
        self.assertEqual(codex_data["access_token"], new_access)
        self.assertEqual(codex_data["refresh_token"], "rt-refresh-2")
        self.assertEqual(auth_data["tokens"]["access_token"], new_access)
        state = service.get_state()
        self.assertEqual(state["items"][0]["token_status"], "refreshed")

    def test_state_skips_invalid_codex_files(self) -> None:
        write_codex(
            self.codex_dir / "codex-valid.json",
            "valid@example.com",
            "acc-valid",
            make_jwt({"exp": 4102444800}),
            "rt-valid",
        )
        (self.codex_dir / "codex-broken.json").write_text("{not-json", encoding="utf-8")

        service = CodexSwitcherService(
            codex_dir=self.codex_dir,
            auth_path=self.auth_path,
            session_factory=lambda: FakeSession({}),
        )

        state = service.get_state()

        self.assertEqual(len(state["items"]), 1)
        self.assertEqual(state["items"][0]["email"], "valid@example.com")

    def test_switch_now_activates_chosen_account(self) -> None:
        token_a = make_jwt({"exp": 4102444800})
        token_b = make_jwt({"exp": 4102444800})
        write_codex(self.codex_dir / "codex-a.json", "a@example.com", "acc-a", token_a, "rt-a")
        write_codex(self.codex_dir / "codex-b.json", "b@example.com", "acc-b", token_b, "rt-b")
        write_auth(self.auth_path, "acc-a", token_a, "a@example.com")

        service = CodexSwitcherService(
            codex_dir=self.codex_dir,
            auth_path=self.auth_path,
            session_factory=lambda: FakeSession({}),
        )

        result = service.switch_now("b@example.com")

        self.assertEqual(result["active_email"], "b@example.com")
        auth_data = json.loads(self.auth_path.read_text(encoding="utf-8"))
        self.assertEqual(auth_data["tokens"]["account_id"], "acc-b")
        self.assertEqual(auth_data["tokens"]["access_token"], token_b)

    def test_switch_now_raises_for_unknown_email(self) -> None:
        token_a = make_jwt({"exp": 4102444800})
        write_codex(self.codex_dir / "codex-a.json", "a@example.com", "acc-a", token_a, "rt-a")

        service = CodexSwitcherService(
            codex_dir=self.codex_dir,
            auth_path=self.auth_path,
            session_factory=lambda: FakeSession({}),
        )

        with self.assertRaises(RuntimeError):
            service.switch_now("nonexistent@example.com")

    def test_pick_first_ready_selects_lowest_usage(self) -> None:
        token_a = make_jwt({"exp": 4102444800})
        token_b = make_jwt({"exp": 4102444800})
        token_c = make_jwt({"exp": 4102444800})
        write_codex(self.codex_dir / "codex-a.json", "a@example.com", "acc-a", token_a, "rt-a")
        write_codex(self.codex_dir / "codex-b.json", "b@example.com", "acc-b", token_b, "rt-b")
        write_codex(self.codex_dir / "codex-c.json", "c@example.com", "acc-c", token_c, "rt-c")
        write_auth(self.auth_path, "acc-c", token_c, "c@example.com")

        usage = {
            "acc-a": {"plan_type": "team", "rate_limit": {
                "primary_window": {"used_percent": 30, "reset_at": "2026-03-07T05:00:00Z"},
                "secondary_window": {"used_percent": 5, "reset_at": "2026-03-08T05:00:00Z"},
            }},
            "acc-b": {"plan_type": "team", "rate_limit": {
                "primary_window": {"used_percent": 50, "reset_at": "2026-03-07T05:00:00Z"},
                "secondary_window": {"used_percent": 5, "reset_at": "2026-03-08T05:00:00Z"},
            }},
            "acc-c": {"plan_type": "team", "rate_limit": {
                "primary_window": {"used_percent": 91, "reset_at": "2026-03-07T05:00:00Z"},
                "secondary_window": {"used_percent": 5, "reset_at": "2026-03-08T05:00:00Z"},
            }},
        }
        service = CodexSwitcherService(
            codex_dir=self.codex_dir,
            auth_path=self.auth_path,
            session_factory=lambda: FakeSession(usage),
        )

        result = service.pick_first_ready()

        self.assertTrue(result["switched"])
        self.assertEqual(result["active_email"], "a@example.com")
        auth_data = json.loads(self.auth_path.read_text(encoding="utf-8"))
        self.assertEqual(auth_data["tokens"]["account_id"], "acc-a")

    def test_pick_first_ready_returns_false_when_all_near_limit(self) -> None:
        token_a = make_jwt({"exp": 4102444800})
        token_b = make_jwt({"exp": 4102444800})
        write_codex(self.codex_dir / "codex-a.json", "a@example.com", "acc-a", token_a, "rt-a")
        write_codex(self.codex_dir / "codex-b.json", "b@example.com", "acc-b", token_b, "rt-b")
        write_auth(self.auth_path, "acc-a", token_a, "a@example.com")

        usage = {
            "acc-a": {"plan_type": "team", "rate_limit": {
                "primary_window": {"used_percent": 95, "reset_at": "2026-03-07T05:00:00Z"},
                "secondary_window": {"used_percent": 5, "reset_at": "2026-03-08T05:00:00Z"},
            }},
            "acc-b": {"plan_type": "team", "rate_limit": {
                "primary_window": {"used_percent": 92, "reset_at": "2026-03-07T05:00:00Z"},
                "secondary_window": {"used_percent": 5, "reset_at": "2026-03-08T05:00:00Z"},
            }},
        }
        service = CodexSwitcherService(
            codex_dir=self.codex_dir,
            auth_path=self.auth_path,
            session_factory=lambda: FakeSession(usage),
        )

        result = service.pick_first_ready()

        self.assertFalse(result["switched"])

    def test_refresh_raises_without_refresh_token(self) -> None:
        expired_access = make_jwt({"exp": 1})
        write_codex(self.codex_dir / "codex-noref.json", "noref@example.com", "acc-noref", expired_access, "")

        service = CodexSwitcherService(
            codex_dir=self.codex_dir,
            auth_path=self.auth_path,
            session_factory=lambda: FakeSession({}),
        )

        result = service.refresh_now(auto_switch=False)

        state = service.get_state()
        row = state["items"][0]
        self.assertEqual(row["token_status"], "invalid")
        self.assertIn("Missing refresh_token", row["last_error"])

    def test_usage_retries_after_401_with_token_refresh(self) -> None:
        old_access = make_jwt({"exp": 4102444800})
        new_access = make_jwt({"exp": 4102444800})
        new_id = make_jwt({
            "email": "retry@example.com",
            "https://api.openai.com/auth": {"chatgpt_account_id": "acc-retry"},
        })
        write_codex(self.codex_dir / "codex-retry.json", "retry@example.com", "acc-retry", old_access, "rt-retry")

        usage = {
            "acc-retry": {"plan_type": "team", "rate_limit": {
                "primary_window": {"used_percent": 25, "reset_at": "2026-03-07T05:00:00Z"},
                "secondary_window": {"used_percent": 5, "reset_at": "2026-03-08T05:00:00Z"},
            }},
        }
        refresh_payload = {
            "rt-retry": {
                "id_token": new_id,
                "access_token": new_access,
                "refresh_token": "rt-retry-2",
            },
        }
        service = CodexSwitcherService(
            codex_dir=self.codex_dir,
            auth_path=self.auth_path,
            session_factory=lambda: FakeSession(usage, refresh_payload, usage_401_once={"acc-retry"}),
        )

        service.refresh_now(auto_switch=False)

        state = service.get_state()
        row = state["items"][0]
        self.assertEqual(row["usage_status"], "ok")
        self.assertEqual(row["primary_used_percent"], 25)
        codex_data = json.loads((self.codex_dir / "codex-retry.json").read_text(encoding="utf-8"))
        self.assertEqual(codex_data["access_token"], new_access)

    def test_no_switch_when_active_below_threshold(self) -> None:
        token_a = make_jwt({"exp": 4102444800})
        token_b = make_jwt({"exp": 4102444800})
        write_codex(self.codex_dir / "codex-a.json", "a@example.com", "acc-a", token_a, "rt-a")
        write_codex(self.codex_dir / "codex-b.json", "b@example.com", "acc-b", token_b, "rt-b")
        write_auth(self.auth_path, "acc-a", token_a, "a@example.com")

        usage = {
            "acc-a": {"plan_type": "team", "rate_limit": {
                "primary_window": {"used_percent": 50, "reset_at": "2026-03-07T05:00:00Z"},
                "secondary_window": {"used_percent": 10, "reset_at": "2026-03-08T05:00:00Z"},
            }},
            "acc-b": {"plan_type": "team", "rate_limit": {
                "primary_window": {"used_percent": 20, "reset_at": "2026-03-07T05:00:00Z"},
                "secondary_window": {"used_percent": 10, "reset_at": "2026-03-08T05:00:00Z"},
            }},
        }
        service = CodexSwitcherService(
            codex_dir=self.codex_dir,
            auth_path=self.auth_path,
            session_factory=lambda: FakeSession(usage),
        )

        result = service.refresh_now(auto_switch=True)

        self.assertIsNone(result["summary"]["switched_to"])
        auth_data = json.loads(self.auth_path.read_text(encoding="utf-8"))
        self.assertEqual(auth_data["tokens"]["account_id"], "acc-a")


if __name__ == "__main__":
    unittest.main()
