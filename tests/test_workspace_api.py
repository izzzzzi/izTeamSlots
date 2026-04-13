from __future__ import annotations

import json
import unittest
from typing import Any


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
