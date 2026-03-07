from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from typing import Any

from backend.account_store import AccountStore
from backend.slot_orchestrator import SlotManager


class FakeWorkspaceAPI:
    def __init__(self, members: list[dict[str, Any]], invites: list[dict[str, Any]]) -> None:
        self._members = members
        self._invites = invites
        self.deleted_members: list[str] = []
        self.deleted_invites: list[str] = []

    def get_members(self) -> list[dict[str, Any]]:
        return list(self._members)

    def get_pending_invites(self) -> list[dict[str, Any]]:
        return list(self._invites)

    def delete_member(self, user_id: str) -> dict[str, Any]:
        self.deleted_members.append(user_id)
        return {"ok": True}

    def delete_invite(self, email: str) -> dict[str, Any]:
        self.deleted_invites.append(email)
        return {"ok": True}


class TestSlotManagerWorkspaceSync(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.store = AccountStore(Path(self.temp_dir.name) / "accounts")
        admin = self.store.add_admin("owner@example.com", "secret")
        admin.access_token = "token"
        admin.account_id = "acc-123"
        admin.workspace_id = "acc-123"
        self.store.update_admin(admin)
        self.store.add_worker("slot1@example.com", "pw", "owner@example.com")
        self.store.add_worker("slot2@example.com", "pw", "owner@example.com")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def make_manager(self) -> SlotManager:
        return SlotManager(store=self.store, admin_email="owner@example.com", log=lambda _msg: None, headless=True)

    def test_build_workspace_sync_plan_filters_local_and_protected_entries(self) -> None:
        manager = self.make_manager()
        members = [
            {"id": "owner-id", "email": "owner@example.com", "role": "account-owner"},
            {"id": "slot-id", "email": "slot1@example.com", "role": "standard-user"},
            {"id": "extra-id", "email": "extra@example.com", "role": "standard-user"},
            {"id": "admin-id", "email": "admin2@example.com", "role": "workspace-admin"},
        ]
        invites = [
            {"email": "slot2@example.com"},
            {"email": "invite@example.com"},
            {"email_address": "owner@example.com"},
        ]

        plan = manager._build_workspace_sync_plan(members, invites)

        self.assertEqual([item["email"] for item in plan["extra_members"]], ["extra@example.com"])
        self.assertEqual([item["email"] for item in plan["extra_invites"]], ["invite@example.com"])
        self.assertEqual(
            sorted((item["email"], item["reason"]) for item in plan["skipped"]),
            [
                ("admin2@example.com", "role:workspace-admin"),
                ("owner@example.com", "self"),
                ("owner@example.com", "self"),
            ],
        )

    def test_sync_workspace_dry_run_does_not_delete_anything(self) -> None:
        manager = self.make_manager()
        api = FakeWorkspaceAPI(
            members=[{"id": "extra-id", "email": "extra@example.com", "role": "standard-user"}],
            invites=[{"email": "invite@example.com"}],
        )
        manager._ensure_admin_page = lambda: object()  # type: ignore[method-assign]
        manager._get_api = lambda _page: api  # type: ignore[method-assign]

        result = manager.sync_workspace(dry_run=True)

        self.assertTrue(result["dry_run"])
        self.assertEqual([item["email"] for item in result["extra_members"]], ["extra@example.com"])
        self.assertEqual([item["email"] for item in result["extra_invites"]], ["invite@example.com"])
        self.assertEqual(api.deleted_members, [])
        self.assertEqual(api.deleted_invites, [])

    def test_sync_workspace_apply_deletes_extra_members_and_invites(self) -> None:
        manager = self.make_manager()
        api = FakeWorkspaceAPI(
            members=[{"id": "extra-id", "email": "extra@example.com", "role": "standard-user"}],
            invites=[{"email": "invite@example.com"}],
        )
        manager._ensure_admin_page = lambda: object()  # type: ignore[method-assign]
        manager._get_api = lambda _page: api  # type: ignore[method-assign]

        result = manager.sync_workspace(dry_run=False)

        self.assertFalse(result["dry_run"])
        self.assertEqual(result["removed_members"], ["extra@example.com"])
        self.assertEqual(result["removed_invites"], ["invite@example.com"])
        self.assertEqual(api.deleted_members, ["extra-id"])
        self.assertEqual(api.deleted_invites, ["invite@example.com"])


if __name__ == "__main__":
    unittest.main()
