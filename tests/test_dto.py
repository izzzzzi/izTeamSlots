from __future__ import annotations

import unittest

from backend.account_store import AdminAccount, WorkerAccount
from backend.dto import AdminRow, AppStateDTO, WorkerRow


class TestDTO(unittest.TestCase):
    def test_admin_row_statuses(self) -> None:
        account = AdminAccount(id="1", email="admin@example.com", password="pw")
        self.assertEqual(AdminRow.from_account(account).status_label, "Не настроен")
        self.assertEqual(AdminRow.from_account(account, has_browser_profile=True).status_label, "Нужен вход")

        account.access_token = "token"
        self.assertEqual(AdminRow.from_account(account).status_label, "Есть токен")
        self.assertEqual(AdminRow.from_account(account, has_browser_profile=True).status_label, "Готов")

    def test_worker_row_statuses(self) -> None:
        account = WorkerAccount(id="1", email="slot@example.com", password="pw", admin_email="admin@example.com")
        self.assertEqual(WorkerRow.from_account(account).status_label, "Создан")

        account.status = "invited"
        self.assertEqual(WorkerRow.from_account(account).status_label, "Инвайт отправлен")

        account.status = "registered"
        self.assertEqual(WorkerRow.from_account(account).status_label, "Зарегистрирован")

        account.access_token = "token"
        self.assertEqual(WorkerRow.from_account(account, has_browser_profile=True).status_label, "Готов")

    def test_app_state_to_dict(self) -> None:
        dto = AppStateDTO(
            admins=[AdminRow.from_account(AdminAccount(id="1", email="admin@example.com", password="pw"))],
            workers=[WorkerRow.from_account(WorkerAccount(id="2", email="slot@example.com", password="pw"))],
        )

        result = dto.to_dict()

        self.assertIn("admins", result)
        self.assertIn("workers", result)
        self.assertEqual(result["admins"][0]["email"], "admin@example.com")
        self.assertEqual(result["workers"][0]["email"], "slot@example.com")
