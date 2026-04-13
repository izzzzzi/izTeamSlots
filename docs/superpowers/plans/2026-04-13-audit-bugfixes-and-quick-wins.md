# Audit Bugfixes & Quick Wins Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 6 bugs and 4 quick-win improvements found during the codebase audit of izTeamSlots.

**Architecture:** All changes are localized — each task modifies 1-2 backend Python files and adds/updates corresponding tests. No architectural changes, no UI changes, no new dependencies.

**Tech Stack:** Python 3.11+, pytest, threading, JSON file I/O

---

## File Map

| Task | Modifies | Tests |
|------|----------|-------|
| 1 | `backend/jobs.py` | `tests/test_jobs.py` |
| 2 | `backend/codex_switcher.py` | `tests/test_codex_switcher.py` |
| 3 | `backend/chatgpt_workspace_api.py` | `tests/test_workspace_api.py` (create) |
| 4 | `backend/file_logger.py` | `tests/test_jobs.py` (verify) |
| 5 | `backend/codex_switcher.py`, `backend/openai_web_auth.py` | `tests/test_codex_switcher.py` |
| 6 | `backend/ui_facade.py` | (manual verification) |
| 7 | `backend/rpc_server.py` | `tests/test_rpc_protocol.py` |
| 8 | `backend/codex_switcher.py`, `backend/openai_web_auth.py` | (grep verification) |
| 9 | `backend/account_store.py` | `tests/test_account_store.py` |
| 10 | `backend/slot_orchestrator.py`, `backend/ui_facade.py` | `tests/test_slot_orchestrator.py` |

---

### Task 1: Fix race condition in JobManager.start()

**Files:**
- Modify: `backend/jobs.py:55-89`
- Test: `tests/test_jobs.py`

The bug: `self._active_thread` and `self._active_job_id` are assigned **outside** `self._lock`, so two concurrent calls to `start()` can both pass the `busy` check.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_jobs.py`:

```python
def test_start_is_thread_safe_under_contention(self) -> None:
    """Ensure only one job starts even with concurrent start() calls."""
    manager = JobManager(self.emit, file_logger=self.logger)
    barrier = threading.Barrier(10)
    release = threading.Event()
    results: list[str | None] = [None] * 10
    errors: list[str | None] = [None] * 10

    def handler(_ctx):
        release.wait(timeout=5)

    def try_start(index: int) -> None:
        barrier.wait()
        try:
            job_id = manager.start(f"job-{index}", handler)
            results[index] = job_id
        except RuntimeError as e:
            errors[index] = str(e)

    threads = [threading.Thread(target=try_start, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    release.set()
    manager.wait_all()

    started = [r for r in results if r is not None]
    failed = [e for e in errors if e is not None]
    self.assertEqual(len(started), 1, f"Expected exactly 1 job to start, got {len(started)}")
    self.assertEqual(len(failed), 9, f"Expected 9 rejections, got {len(failed)}")
```

Also add `import threading` at the top of the file if not already present.

- [ ] **Step 2: Run test to verify it fails (or is flaky)**

Run: `python -m pytest tests/test_jobs.py::TestJobManager::test_start_is_thread_safe_under_contention -v`

Expected: May pass sometimes, fail sometimes (race condition is timing-dependent). The fix makes it deterministic.

- [ ] **Step 3: Fix — move all state mutation inside the lock**

In `backend/jobs.py`, replace the `start` method (lines 55-89) with:

```python
def start(self, title: str, handler: Callable[[JobContext], Any]) -> str:
    with self._lock:
        if self.busy:
            raise RuntimeError(f"Задача уже выполняется: {self._active_job_id}")

        job_id = uuid.uuid4().hex
        job_logger = self._file_logger.create_job_logger(job_id, title)
        self._emit("job.started", {"job_id": job_id, "title": title, "log_path": job_logger.rel_path})

        def runner() -> None:
            ctx = JobContext(job_id=job_id, _emit=self._emit, _logger=job_logger)
            try:
                result = handler(ctx)
                job_logger.done(result)
                self._emit("job.done", {"job_id": job_id, "result": result, "log_path": job_logger.rel_path})
            except Exception as e:
                message = str(e)
                if len(message) > 1200:
                    message = message[:1200] + "…"
                tb = traceback.format_exc()
                job_logger.error(message, traceback_text=tb)
                self._emit(
                    "job.error",
                    {
                        "job_id": job_id,
                        "error": message,
                        "log_path": job_logger.rel_path,
                    },
                )

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        self._active_thread = thread
        self._active_job_id = job_id
    return job_id
```

Key change: the closing of `with self._lock` now happens **after** `self._active_thread = thread` and `self._active_job_id = job_id`, and after `return job_id` (i.e., the entire body is inside the lock).

- [ ] **Step 4: Run all tests**

Run: `python -m pytest tests/test_jobs.py -v`

Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/jobs.py tests/test_jobs.py
git commit -m "fix(jobs): move thread assignment inside lock to prevent race condition"
```

---

### Task 2: Fix triple _load_accounts in pick_first_ready

**Files:**
- Modify: `backend/codex_switcher.py:200-218`
- Test: `tests/test_codex_switcher.py`

The bug: `pick_first_ready()` calls `_load_accounts()` 3 times and `_detect_active_account()` 2 times. Disk state could change between calls, producing inconsistent results.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_codex_switcher.py`:

```python
def test_pick_first_ready_returns_consistent_state_after_switch(self) -> None:
    """After switching, returned active_email must match the auth.json on disk."""
    token_a = make_jwt({"exp": 4102444800})
    token_b = make_jwt({"exp": 4102444800})
    write_codex(self.codex_dir / "codex-a.json", "a@example.com", "acc-a", token_a, "rt-a")
    write_codex(self.codex_dir / "codex-b.json", "b@example.com", "acc-b", token_b, "rt-b")
    write_auth(self.auth_path, "acc-a", token_a, "a@example.com")

    usage = {
        "acc-a": {"plan_type": "team", "rate_limit": {
            "primary_window": {"used_percent": 10, "reset_at": "2026-03-07T05:00:00Z"},
            "secondary_window": {"used_percent": 5, "reset_at": "2026-03-08T05:00:00Z"},
        }},
        "acc-b": {"plan_type": "team", "rate_limit": {
            "primary_window": {"used_percent": 20, "reset_at": "2026-03-07T05:00:00Z"},
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
    # The active_email in result MUST match what auth.json says
    auth_data = json.loads(self.auth_path.read_text(encoding="utf-8"))
    auth_account_id = auth_data["tokens"]["account_id"]
    # Find which account has this account_id
    for path in self.codex_dir.glob("codex-*.json"):
        codex = json.loads(path.read_text(encoding="utf-8"))
        if codex.get("account_id") == auth_account_id:
            self.assertEqual(result["active_email"], codex["email"])
            break
    else:
        self.fail(f"No codex file found with account_id={auth_account_id}")
```

- [ ] **Step 2: Run test to verify it passes (baseline)**

Run: `python -m pytest tests/test_codex_switcher.py::CodexSwitcherServiceTests::test_pick_first_ready_returns_consistent_state_after_switch -v`

Expected: PASS (the bug is about *potential* inconsistency, the test validates the fix is correct).

- [ ] **Step 3: Fix — reuse single load in pick_first_ready**

In `backend/codex_switcher.py`, replace the `pick_first_ready` method (lines 200-218) with:

```python
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
        # Re-detect active from the same accounts list (auth.json was just written)
        active = self._detect_active_account(accounts)
        for row in rows:
            row["is_active"] = row["email"] == active
        self._status["active_email"] = active
        return {"active_email": active, "switched": True, "summary": summary}
```

Key change: removed 2 extra `_load_accounts()` calls on lines 213-214. After `_activate_account(target)`, we re-detect active from the **same** `accounts` list (auth.json was just written by `_activate_account`, and the accounts data hasn't changed).

- [ ] **Step 4: Run all codex switcher tests**

Run: `python -m pytest tests/test_codex_switcher.py -v`

Expected: All tests PASS (including the existing `test_pick_first_ready_selects_lowest_usage`).

- [ ] **Step 5: Commit**

```bash
git add backend/codex_switcher.py tests/test_codex_switcher.py
git commit -m "fix(codex-switcher): eliminate redundant _load_accounts calls in pick_first_ready"
```

---

### Task 3: Add pagination to workspace API

**Files:**
- Modify: `backend/chatgpt_workspace_api.py:93-107`
- Create: `tests/test_workspace_api.py`

The bug: `get_members` and `get_pending_invites` fetch `limit=100` and ignore the rest. If a workspace has 150 members, 50 are silently dropped.

- [ ] **Step 1: Create test file with pagination test**

Create `tests/test_workspace_api.py`:

```python
from __future__ import annotations

import json
import unittest
from typing import Any
from unittest.mock import MagicMock


class FakePage:
    """Minimal Page stub that returns canned responses from page.evaluate."""

    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self._call_index = 0

    def evaluate(self, script: str, args: Any = None) -> Any:
        if self._call_index >= len(self._responses):
            raise RuntimeError("No more canned responses")
        resp = self._responses[self._call_index]
        self._call_index += 1
        return resp


class TestChatGPTWorkspaceAPIPagination(unittest.TestCase):
    def _make_api(self, page: FakePage):
        from backend.chatgpt_workspace_api import ChatGPTWorkspaceAPI
        return ChatGPTWorkspaceAPI(page, "acc-123", "token-123")

    def test_get_members_fetches_all_pages(self) -> None:
        page1_body = json.dumps({
            "items": [{"id": f"u{i}", "email": f"u{i}@x.com"} for i in range(100)],
            "has_more": True,
        })
        page2_body = json.dumps({
            "items": [{"id": f"u{i}", "email": f"u{i}@x.com"} for i in range(100, 130)],
            "has_more": False,
        })
        page = FakePage([
            {"status": 200, "body": page1_body},
            {"status": 200, "body": page2_body},
        ])
        api = self._make_api(page)

        members = api.get_members()

        self.assertEqual(len(members), 130)

    def test_get_members_single_page(self) -> None:
        body = json.dumps({
            "items": [{"id": "u1", "email": "u1@x.com"}],
        })
        page = FakePage([{"status": 200, "body": body}])
        api = self._make_api(page)

        members = api.get_members()

        self.assertEqual(len(members), 1)

    def test_get_pending_invites_fetches_all_pages(self) -> None:
        page1_body = json.dumps({
            "invites": [{"email": f"i{i}@x.com"} for i in range(100)],
            "has_more": True,
        })
        page2_body = json.dumps({
            "invites": [{"email": f"i{i}@x.com"} for i in range(100, 110)],
            "has_more": False,
        })
        page = FakePage([
            {"status": 200, "body": page1_body},
            {"status": 200, "body": page2_body},
        ])
        api = self._make_api(page)

        invites = api.get_pending_invites()

        self.assertEqual(len(invites), 110)

    def test_get_pending_invites_single_page(self) -> None:
        body = json.dumps({
            "invites": [{"email": "i1@x.com"}],
        })
        page = FakePage([{"status": 200, "body": body}])
        api = self._make_api(page)

        invites = api.get_pending_invites()

        self.assertEqual(len(invites), 1)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_workspace_api.py -v`

Expected: `test_get_members_fetches_all_pages` and `test_get_pending_invites_fetches_all_pages` FAIL (only 100 items returned, second page never fetched).

- [ ] **Step 3: Implement pagination**

In `backend/chatgpt_workspace_api.py`, replace `get_pending_invites` and `get_members` (lines 93-107) with:

```python
def get_pending_invites(self) -> list[dict]:
    """Получить список ожидающих инвайтов (с пагинацией)."""
    return self._paginate(
        f"/backend-api/accounts/{self.account_id}/invites",
        items_key="invites",
    )

def get_members(self) -> list[dict]:
    """Получить список участников workspace (с пагинацией)."""
    return self._paginate(
        f"/backend-api/accounts/{self.account_id}/users",
        items_key="items",
        fallback_key="users",
    )

def _paginate(
    self,
    path: str,
    items_key: str,
    fallback_key: str | None = None,
    page_size: int = 100,
    max_pages: int = 20,
) -> list[dict]:
    """Fetch all pages from a paginated endpoint."""
    all_items: list[dict] = []
    for page_num in range(max_pages):
        offset = page_num * page_size
        data = self._request("GET", f"{path}?offset={offset}&limit={page_size}")
        items = data.get(items_key) or (data.get(fallback_key, []) if fallback_key else [])
        all_items.extend(items)
        if not data.get("has_more") and len(items) >= page_size:
            # API didn't send has_more — check if we got a full page
            continue
        if len(items) < page_size:
            break
        if data.get("has_more") is False:
            break
    return all_items
```

- [ ] **Step 4: Run all workspace API tests**

Run: `python -m pytest tests/test_workspace_api.py -v`

Expected: All 4 tests PASS.

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `python -m pytest tests/ -v`

Expected: All tests PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/chatgpt_workspace_api.py tests/test_workspace_api.py
git commit -m "fix(workspace-api): add pagination to get_members and get_pending_invites"
```

---

### Task 4: Fix file_logger timestamp to use UTC

**Files:**
- Modify: `backend/file_logger.py:1-14`

The bug: `_timestamp()` uses `datetime.now()` (local time), but the rest of the codebase uses UTC. Log timestamps will diverge from data timestamps.

- [ ] **Step 1: Fix the import and function**

In `backend/file_logger.py`, change line 6 and line 13-14:

Replace:
```python
from datetime import datetime
```
with:
```python
from datetime import UTC, datetime
```

Replace:
```python
def _timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
```
with:
```python
def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%SZ")
```

Also update `create_job_logger` at line 49:

Replace:
```python
stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
```
with:
```python
stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
```

- [ ] **Step 2: Run existing tests**

Run: `python -m pytest tests/test_jobs.py -v`

Expected: All 3 tests PASS (they don't assert on timestamp format, just behavior).

- [ ] **Step 3: Commit**

```bash
git add backend/file_logger.py
git commit -m "fix(logger): use UTC timestamps consistent with rest of codebase"
```

---

### Task 5: Deduplicate _decode_jwt_payload

**Files:**
- Modify: `backend/codex_switcher.py:48-65` (keep as canonical)
- Modify: `backend/openai_web_auth.py:709-719` (replace with import)
- Test: `tests/test_codex_switcher.py`

The bug: Two copies of `_decode_jwt_payload` exist with different return types (`dict` vs `dict | None`). The `codex_switcher.py` version is safer (returns `{}` instead of `None`).

- [ ] **Step 1: Write test for the canonical implementation**

Add to `tests/test_codex_switcher.py` (top-level, outside the class, or inside a new test class):

```python
class TestDecodeJwtPayload(unittest.TestCase):
    def test_valid_jwt_returns_payload(self) -> None:
        from backend.codex_switcher import _decode_jwt_payload

        token = make_jwt({"sub": "user123", "exp": 4102444800})
        result = _decode_jwt_payload(token)
        self.assertEqual(result["sub"], "user123")

    def test_empty_string_returns_empty_dict(self) -> None:
        from backend.codex_switcher import _decode_jwt_payload

        self.assertEqual(_decode_jwt_payload(""), {})

    def test_malformed_token_returns_empty_dict(self) -> None:
        from backend.codex_switcher import _decode_jwt_payload

        self.assertEqual(_decode_jwt_payload("not.a.jwt"), {})
        self.assertEqual(_decode_jwt_payload("only-one-part"), {})

    def test_non_dict_payload_returns_empty_dict(self) -> None:
        from backend.codex_switcher import _decode_jwt_payload

        # Create a JWT where payload is a JSON array, not object
        array_payload = base64.urlsafe_b64encode(b'[1,2,3]').decode().rstrip("=")
        header = base64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
        sig = base64.urlsafe_b64encode(b'sig').decode().rstrip("=")
        token = f"{header}.{array_payload}.{sig}"
        self.assertEqual(_decode_jwt_payload(token), {})
```

- [ ] **Step 2: Run new tests**

Run: `python -m pytest tests/test_codex_switcher.py::TestDecodeJwtPayload -v`

Expected: All 4 tests PASS.

- [ ] **Step 3: Make _decode_jwt_payload public in codex_switcher**

In `backend/codex_switcher.py`, rename `_decode_jwt_payload` to `decode_jwt_payload` (remove underscore prefix) at line 48.

Then update all internal references in `codex_switcher.py`:
- Line 70 (`_parse_jwt_exp`): change `_decode_jwt_payload` to `decode_jwt_payload`
- Line 77 (`_parse_id_token_claims`): change `_decode_jwt_payload` to `decode_jwt_payload`

- [ ] **Step 4: Replace the duplicate in openai_web_auth.py**

In `backend/openai_web_auth.py`:

1. Add import at the top (after the existing `from .mail import ...` line):
```python
from .codex_switcher import decode_jwt_payload
```

2. Delete the `_decode_jwt_payload` function at lines 709-719.

3. Replace the single call site at line 881:
```python
jwt_data = _decode_jwt_payload(id_token or access_token)
```
with:
```python
jwt_data = decode_jwt_payload(id_token or access_token)
```

4. The call site uses `jwt_data` as a dict with `.get()` calls — the `codex_switcher` version returns `{}` on failure (not `None`), so existing code `if jwt_data:` still works correctly (empty dict is falsy).

- [ ] **Step 5: Update test imports**

In `tests/test_codex_switcher.py`, update the `TestDecodeJwtPayload` class to import the renamed function:

```python
from backend.codex_switcher import decode_jwt_payload
```

And update the test methods to use `decode_jwt_payload` instead of `_decode_jwt_payload`.

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest tests/ -v`

Expected: All tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/codex_switcher.py backend/openai_web_auth.py tests/test_codex_switcher.py
git commit -m "fix: deduplicate _decode_jwt_payload — single canonical implementation in codex_switcher"
```

---

### Task 6: Remove redundant Mailbox creation in relogin_worker_email

**Files:**
- Modify: `backend/ui_facade.py:294-296`

The bug: `Mailbox(email=worker.email, password=worker.password)` is created twice — once for `create_provider_for_mailbox` and again on the next line.

- [ ] **Step 1: Fix — create Mailbox once**

In `backend/ui_facade.py`, replace lines 294-296:

```python
        mail = create_provider_for_mailbox(Mailbox(email=worker.email, password=worker.password))
        try:
            mailbox = Mailbox(email=worker.email, password=worker.password)
```

with:

```python
        mailbox = Mailbox(email=worker.email, password=worker.password)
        mail = create_provider_for_mailbox(mailbox)
        try:
```

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/ -v`

Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/ui_facade.py
git commit -m "fix: remove redundant Mailbox creation in relogin_worker_email"
```

---

### Task 7: Strengthen API key masking

**Files:**
- Modify: `backend/rpc_server.py:78-84`
- Test: `tests/test_rpc_protocol.py`

The bug: For keys 13-16 chars, `value[:4] + "***" + value[-4:]` reveals 8 out of 13-16 characters (more than half).

- [ ] **Step 1: Write tests for masking**

Add to `tests/test_rpc_protocol.py`:

```python
from backend.rpc_server import RPCServer


class TestMaskSettingValue(unittest.TestCase):
    def test_empty_value_returns_empty(self) -> None:
        self.assertEqual(RPCServer._mask_setting_value("BOOMLIFY_API_KEY", ""), "")

    def test_short_key_fully_masked(self) -> None:
        self.assertEqual(RPCServer._mask_setting_value("BOOMLIFY_API_KEY", "abc123"), "***")

    def test_long_key_shows_only_first_and_last_two(self) -> None:
        key = "sk-abcdefghijklmnop"  # 18 chars
        masked = RPCServer._mask_setting_value("BOOMLIFY_API_KEY", key)
        self.assertEqual(masked, "sk***op")
        self.assertNotIn("abcdef", masked)

    def test_medium_key_fully_masked(self) -> None:
        key = "1234567890123"  # 13 chars
        masked = RPCServer._mask_setting_value("BOOMLIFY_API_KEY", key)
        self.assertEqual(masked, "***")

    def test_non_key_setting_not_masked(self) -> None:
        self.assertEqual(RPCServer._mask_setting_value("BOOMLIFY_DOMAIN", "example.com"), "example.com")
```

- [ ] **Step 2: Run tests to verify failures**

Run: `python -m pytest tests/test_rpc_protocol.py::TestMaskSettingValue -v`

Expected: `test_long_key_shows_only_first_and_last_two` and `test_medium_key_fully_masked` FAIL.

- [ ] **Step 3: Fix masking logic**

In `backend/rpc_server.py`, replace lines 78-84:

```python
@staticmethod
def _mask_setting_value(key: str, value: str) -> str:
    if not value:
        return ""
    if "KEY" in key:
        return value[:4] + "***" + value[-4:] if len(value) > 12 else "***"
    return value
```

with:

```python
@staticmethod
def _mask_setting_value(key: str, value: str) -> str:
    if not value:
        return ""
    if "KEY" in key:
        if len(value) <= 16:
            return "***"
        return value[:2] + "***" + value[-2:]
    return value
```

Now: keys <= 16 chars are fully masked; longer keys show only first 2 + last 2 (4 out of 17+ chars = ~24% max).

- [ ] **Step 4: Run masking tests**

Run: `python -m pytest tests/test_rpc_protocol.py -v`

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/rpc_server.py tests/test_rpc_protocol.py
git commit -m "fix(security): strengthen API key masking — show at most 4 chars for long keys"
```

---

### Task 8: Extract CLIENT_ID to shared constant

**Files:**
- Modify: `backend/codex_switcher.py:18`
- Modify: `backend/openai_web_auth.py:837,855`

The bug: `"app_EMoamEEZ73f0CkXaXp7hrann"` is hardcoded in 3 places (1 constant + 2 inline strings). Should be defined once.

- [ ] **Step 1: Verify current locations**

Run: `grep -rn "app_EMoamEEZ73f0CkXaXp7hrann" backend/`

Expected: 3 matches — `codex_switcher.py:18`, `openai_web_auth.py:837`, `openai_web_auth.py:855`.

- [ ] **Step 2: Import and use the constant from codex_switcher**

In `backend/openai_web_auth.py`, add to the existing imports from `.codex_switcher` (or add a new import line after the existing `from .mail import ...` line):

```python
from .codex_switcher import CLIENT_ID
```

Note: if Task 5 already added an import from `.codex_switcher`, extend that line:
```python
from .codex_switcher import CLIENT_ID, decode_jwt_payload
```

Then replace the two inline strings:

Line 837: replace `"app_EMoamEEZ73f0CkXaXp7hrann"` with `CLIENT_ID`
Line 855: replace `"app_EMoamEEZ73f0CkXaXp7hrann"` with `CLIENT_ID`

- [ ] **Step 3: Verify no more inline duplicates**

Run: `grep -rn "app_EMoamEEZ73f0CkXaXp7hrann" backend/`

Expected: Only 1 match — `codex_switcher.py:18` (the constant definition).

- [ ] **Step 4: Run full test suite**

Run: `python -m pytest tests/ -v`

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/openai_web_auth.py
git commit -m "refactor: use shared CLIENT_ID constant instead of inline duplicates"
```

---

### Task 9: Set chmod 0600 on account meta.json files

**Files:**
- Modify: `backend/account_store.py:75-79`
- Test: `tests/test_account_store.py`

The bug: `_atomic_write_json` writes meta.json (containing passwords) without restrictive permissions. `codex_switcher.py` already does `chmod 0o600` for auth files — meta.json should too.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_account_store.py`:

```python
import os
import stat

class TestAccountStorePermissions(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name) / "accounts"
        self.store = AccountStore(self.base_dir)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @unittest.skipIf(os.name == "nt", "chmod not meaningful on Windows")
    def test_meta_json_has_restrictive_permissions(self) -> None:
        admin = self.store.add_admin("admin@example.com", "secret-password")
        meta_path = self.store.admin_dir / admin.id / "meta.json"
        mode = stat.S_IMODE(meta_path.stat().st_mode)
        self.assertEqual(mode, 0o600, f"Expected 0600, got {oct(mode)}")

    @unittest.skipIf(os.name == "nt", "chmod not meaningful on Windows")
    def test_index_json_has_restrictive_permissions(self) -> None:
        self.store.add_admin("admin@example.com", "pw")
        index_path = self.store.admin_dir / "index.json"
        mode = stat.S_IMODE(index_path.stat().st_mode)
        self.assertEqual(mode, 0o600, f"Expected 0600, got {oct(mode)}")
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_account_store.py::TestAccountStorePermissions -v`

Expected: FAIL — default umask gives 0o644.

- [ ] **Step 3: Add chmod to _atomic_write_json**

In `backend/account_store.py`, add `import os` at the top (if not already present — it's not in the current imports), then replace lines 75-79:

```python
def _atomic_write_json(self, path: Path, data: dict) -> None:
    """Write JSON atomically: temp file + rename to prevent corruption on crash."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
```

with:

```python
def _atomic_write_json(self, path: Path, data: dict) -> None:
    """Write JSON atomically: temp file + rename to prevent corruption on crash."""
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    if os.name != "nt":
        os.chmod(path, 0o600)
```

- [ ] **Step 4: Run permission tests**

Run: `python -m pytest tests/test_account_store.py -v`

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/account_store.py tests/test_account_store.py
git commit -m "fix(security): set chmod 0600 on meta.json and index.json files"
```

---

### Task 10: Replace private _close_admin_page call with public method

**Files:**
- Modify: `backend/slot_orchestrator.py:89-96`
- Modify: `backend/ui_facade.py:280`
- Test: `tests/test_slot_orchestrator.py`

The bug: `ui_facade.py:280` calls `manager._close_admin_page()` — a private method. `SlotManager` already has a public `close()` method, but it also closes mail providers. We need a public method that only closes the admin page.

- [ ] **Step 1: Add public method to SlotManager**

In `backend/slot_orchestrator.py`, add a public method after `_close_admin_page` (after line 96):

```python
def close_admin_page(self) -> None:
    """Закрыть браузер админа (публичный интерфейс)."""
    self._close_admin_page()
```

- [ ] **Step 2: Update UIFacade to use the public method**

In `backend/ui_facade.py`, replace line 280:

```python
        manager._close_admin_page()
```

with:

```python
        manager.close_admin_page()
```

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/ -v`

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/slot_orchestrator.py backend/ui_facade.py
git commit -m "refactor: expose close_admin_page as public method on SlotManager"
```

---

## Final Verification

After all 10 tasks are complete:

- [ ] Run full test suite: `python -m pytest tests/ -v`
- [ ] Run ruff linter: `ruff check backend/ tests/`
- [ ] Verify no inline CLIENT_ID duplicates: `grep -rn "app_EMoamEEZ73f0CkXaXp7hrann" backend/`
- [ ] Verify no duplicate `_decode_jwt_payload`: `grep -rn "_decode_jwt_payload" backend/`
