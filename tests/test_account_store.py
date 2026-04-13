from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from backend.account_store import AccountStore


class TestAccountStore(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name) / "accounts"
        self.store = AccountStore(self.base_dir)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_admin_crud_roundtrip(self) -> None:
        admin = self.store.add_admin("admin@example.com", "pw")
        admin.access_token = "token"
        admin.workspace_id = "ws-1"
        admin.account_id = "acc-1"
        admin.workspaces = [{"workspace_id": "ws-1"}]
        admin.last_login = "2026-03-07T00:00:00Z"
        self.store.update_admin(admin)

        loaded = self.store.get_admin("admin@example.com")

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.access_token, "token")
        self.assertEqual(loaded.workspace_id, "ws-1")
        self.assertEqual(loaded.account_id, "acc-1")
        self.assertEqual(loaded.workspaces, [{"workspace_id": "ws-1"}])
        self.assertEqual(loaded.last_login, "2026-03-07T00:00:00Z")

        self.store.delete_admin("admin@example.com")
        self.assertIsNone(self.store.get_admin("admin@example.com"))

    def test_worker_crud_roundtrip(self) -> None:
        worker = self.store.add_worker("slot@example.com", "pw", "admin@example.com")
        worker.status = "registered"
        worker.openai_password = "openai-pw"
        worker.access_token = "token"
        worker.workspace_id = "ws-1"
        self.store.update_worker(worker)

        loaded = self.store.get_worker("slot@example.com")

        self.assertIsNotNone(loaded)
        assert loaded is not None
        self.assertEqual(loaded.status, "registered")
        self.assertEqual(loaded.openai_password, "openai-pw")
        self.assertEqual(loaded.access_token, "token")
        self.assertEqual(loaded.workspace_id, "ws-1")
        self.assertEqual(loaded.admin_email, "admin@example.com")

        self.store.delete_worker("slot@example.com")
        self.assertIsNone(self.store.get_worker("slot@example.com"))

    def test_doctor_rebuilds_broken_worker_index(self) -> None:
        worker = self.store.add_worker("slot@example.com", "pw", "admin@example.com")
        worker_dir = self.store.worker_dir / worker.id
        index_path = self.store.worker_dir / "index.json"
        index_path.write_text("{broken", encoding="utf-8")

        fixes = self.store.doctor()

        rebuilt = json.loads(index_path.read_text(encoding="utf-8"))
        self.assertIn("slot@example.com", rebuilt)
        self.assertTrue(any("index.json был повреждён" in fix for fix in fixes))
        self.assertTrue(worker_dir.exists())

    def test_doctor_recreates_missing_meta(self) -> None:
        worker = self.store.add_worker("slot@example.com", "pw", "admin@example.com")
        meta_path = self.store.worker_dir / worker.id / "meta.json"
        meta_path.unlink()

        fixes = self.store.doctor()

        rebuilt = json.loads(meta_path.read_text(encoding="utf-8"))
        self.assertEqual(rebuilt["email"], "slot@example.com")
        self.assertEqual(rebuilt["status"], "created")
        self.assertTrue(any("meta.json отсутствовал" in fix for fix in fixes))


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
