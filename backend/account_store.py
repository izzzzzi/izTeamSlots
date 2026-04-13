from __future__ import annotations

import json
import os
import shutil
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import DATA_ROOT, PROJECT_ROOT

ACCOUNTS_DIR = DATA_ROOT / "accounts"


@dataclass
class AdminAccount:
    id: str
    email: str
    password: str
    access_token: str | None = None
    workspace_id: str | None = None
    account_id: str | None = None
    workspaces: list[dict] | None = None
    created_at: str | None = None
    last_login: str | None = None


@dataclass
class WorkerAccount:
    id: str
    email: str
    password: str
    status: str = "created"  # created -> invited -> registered -> logged_in
    openai_password: str | None = None
    access_token: str | None = None
    workspace_id: str | None = None
    admin_email: str | None = None
    created_at: str | None = None


class AccountStore:
    """Единый CRUD для admin и worker аккаунтов."""

    def __init__(self, base_dir: Path = ACCOUNTS_DIR) -> None:
        self.base_dir = base_dir
        self.admin_dir = base_dir / "admin"
        self.worker_dir = base_dir / "worker"
        self._lock = threading.Lock()
        self.admin_dir.mkdir(parents=True, exist_ok=True)
        self.worker_dir.mkdir(parents=True, exist_ok=True)

    # --- Helpers ---

    def _read_index(self, path: Path) -> dict:
        index_path = path / "index.json"
        if index_path.exists():
            return json.loads(index_path.read_text())
        return {}

    def _write_index(self, path: Path, data: dict) -> None:
        self._atomic_write_json(path / "index.json", data)

    def _read_meta(self, folder: Path) -> dict:
        meta_path = folder / "meta.json"
        if meta_path.exists():
            return json.loads(meta_path.read_text())
        return {}

    def _write_meta(self, folder: Path, data: dict) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        self._atomic_write_json(folder / "meta.json", data)

    def _atomic_write_json(self, path: Path, data: dict) -> None:
        """Write JSON atomically: temp file + rename to prevent corruption on crash."""
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
        if os.name != "nt":
            os.chmod(path, 0o600)

    # --- Admin CRUD ---

    def list_admins(self) -> list[AdminAccount]:
        index = self._read_index(self.admin_dir)
        admins = []
        for email, info in index.items():
            account_dir = self.admin_dir / info["id"]
            meta = self._read_meta(account_dir)
            admins.append(AdminAccount(
                id=info["id"],
                email=email,
                password=meta.get("password", ""),
                access_token=meta.get("access_token"),
                workspace_id=meta.get("workspace_id"),
                account_id=meta.get("account_id"),
                workspaces=meta.get("workspaces"),
                created_at=info.get("created_at"),
                last_login=info.get("last_login"),
            ))
        return admins

    def get_admin(self, email: str) -> AdminAccount | None:
        index = self._read_index(self.admin_dir)
        info = index.get(email)
        if not info:
            return None
        account_dir = self.admin_dir / info["id"]
        meta = self._read_meta(account_dir)
        return AdminAccount(
            id=info["id"],
            email=email,
            password=meta.get("password", ""),
            access_token=meta.get("access_token"),
            workspace_id=meta.get("workspace_id"),
            account_id=meta.get("account_id"),
            workspaces=meta.get("workspaces"),
            created_at=info.get("created_at"),
            last_login=info.get("last_login"),
        )

    def add_admin(self, email: str, password: str) -> AdminAccount:
        with self._lock:
            index = self._read_index(self.admin_dir)
            if email in index:
                raise ValueError(f"Админ {email} уже существует")
            account_id = uuid.uuid4().hex
            now = datetime.now(timezone.utc).isoformat()
            index[email] = {"id": account_id, "created_at": now}
            self._write_index(self.admin_dir, index)
            account_dir = self.admin_dir / account_id
            self._write_meta(account_dir, {"email": email, "password": password})
            return AdminAccount(id=account_id, email=email, password=password, created_at=now)

    def update_admin(self, account: AdminAccount) -> None:
        with self._lock:
            index = self._read_index(self.admin_dir)
            if account.email not in index:
                raise ValueError(f"Админ {account.email} не найден")
            info = index[account.email]
            if account.last_login:
                info["last_login"] = account.last_login
            self._write_index(self.admin_dir, index)
            account_dir = self.admin_dir / info["id"]
            meta: dict[str, Any] = {
                "email": account.email,
                "password": account.password,
            }
            if account.access_token is not None:
                meta["access_token"] = account.access_token
            if account.workspace_id is not None:
                meta["workspace_id"] = account.workspace_id
            if account.account_id is not None:
                meta["account_id"] = account.account_id
            if account.workspaces is not None:
                meta["workspaces"] = account.workspaces
            self._write_meta(account_dir, meta)

    def delete_admin(self, email: str) -> None:
        with self._lock:
            index = self._read_index(self.admin_dir)
            info = index.pop(email, None)
            if not info:
                return
            self._write_index(self.admin_dir, index)
            account_dir = self.admin_dir / info["id"]
            if account_dir.exists():
                shutil.rmtree(account_dir)

    def get_admin_profile_dir(self, account: AdminAccount) -> Path:
        profile_dir = self.admin_dir / account.id / "browser_profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        return profile_dir

    # --- Worker CRUD ---

    def list_workers(self) -> list[WorkerAccount]:
        index = self._read_index(self.worker_dir)
        workers = []
        for email, info in index.items():
            account_dir = self.worker_dir / info["id"]
            meta = self._read_meta(account_dir)
            workers.append(WorkerAccount(
                id=info["id"],
                email=email,
                password=meta.get("password", ""),
                status=meta.get("status", info.get("status", "created")),
                openai_password=meta.get("openai_password"),
                access_token=meta.get("access_token"),
                workspace_id=meta.get("workspace_id"),
                admin_email=info.get("admin_email"),
                created_at=info.get("created_at"),
            ))
        return workers

    def get_worker(self, email: str) -> WorkerAccount | None:
        index = self._read_index(self.worker_dir)
        info = index.get(email)
        if not info:
            return None
        account_dir = self.worker_dir / info["id"]
        meta = self._read_meta(account_dir)
        return WorkerAccount(
            id=info["id"],
            email=email,
            password=meta.get("password", ""),
            status=meta.get("status", info.get("status", "created")),
            openai_password=meta.get("openai_password"),
            access_token=meta.get("access_token"),
            workspace_id=meta.get("workspace_id"),
            admin_email=info.get("admin_email"),
            created_at=info.get("created_at"),
        )

    def add_worker(self, email: str, password: str, admin_email: str) -> WorkerAccount:
        with self._lock:
            index = self._read_index(self.worker_dir)
            if email in index:
                raise ValueError(f"Worker {email} уже существует")
            worker_id = uuid.uuid4().hex
            now = datetime.now(timezone.utc).isoformat()
            index[email] = {
                "id": worker_id,
                "status": "created",
                "admin_email": admin_email,
                "created_at": now,
            }
            self._write_index(self.worker_dir, index)
            account_dir = self.worker_dir / worker_id
            self._write_meta(account_dir, {
                "email": email,
                "password": password,
                "status": "created",
                "admin_email": admin_email,
            })
            return WorkerAccount(
                id=worker_id, email=email, password=password,
                admin_email=admin_email, created_at=now,
            )

    def update_worker(self, account: WorkerAccount) -> None:
        with self._lock:
            index = self._read_index(self.worker_dir)
            if account.email not in index:
                raise ValueError(f"Worker {account.email} не найден")
            info = index[account.email]
            info["status"] = account.status
            if account.admin_email is not None:
                info["admin_email"] = account.admin_email
            else:
                info.pop("admin_email", None)
            self._write_index(self.worker_dir, index)
            account_dir = self.worker_dir / info["id"]
            meta: dict[str, Any] = {
                "email": account.email,
                "password": account.password,
                "status": account.status,
            }
            if account.openai_password is not None:
                meta["openai_password"] = account.openai_password
            if account.access_token is not None:
                meta["access_token"] = account.access_token
            if account.workspace_id is not None:
                meta["workspace_id"] = account.workspace_id
            if account.admin_email is not None:
                meta["admin_email"] = account.admin_email
            self._write_meta(account_dir, meta)

    def delete_worker(self, email: str) -> None:
        with self._lock:
            index = self._read_index(self.worker_dir)
            info = index.pop(email, None)
            if not info:
                return
            self._write_index(self.worker_dir, index)
            account_dir = self.worker_dir / info["id"]
            if account_dir.exists():
                shutil.rmtree(account_dir)

    def get_worker_profile_dir(self, account: WorkerAccount) -> Path:
        profile_dir = self.worker_dir / account.id / "browser_profile"
        profile_dir.mkdir(parents=True, exist_ok=True)
        return profile_dir

    # --- Doctor ---

    def doctor(self) -> list[str]:
        """Проверяет целостность данных и исправляет проблемы.
        Возвращает список выполненных исправлений."""
        fixes: list[str] = []

        for role, role_dir in [("admin", self.admin_dir), ("worker", self.worker_dir)]:
            # 1. Проверяем index.json — читаемый ли
            index_path = role_dir / "index.json"
            if index_path.exists():
                try:
                    index = json.loads(index_path.read_text())
                except (json.JSONDecodeError, OSError):
                    # Битый index — пересобираем из папок
                    index = self._rebuild_index(role_dir, role)
                    fixes.append(f"{role}: index.json был повреждён — пересобран из папок")
            else:
                index = {}

            changed = False
            to_remove: list[str] = []

            for email, info in list(index.items()):
                account_id = info.get("id")
                if not account_id:
                    to_remove.append(email)
                    fixes.append(f"{role}: {email} — нет id в index, запись удалена")
                    continue

                account_dir = role_dir / account_id

                # 2. Папка аккаунта не существует — создаём с meta.json
                if not account_dir.exists():
                    account_dir.mkdir(parents=True, exist_ok=True)
                    meta = {"email": email}
                    if "password" not in info:
                        meta["password"] = ""
                    else:
                        meta["password"] = info["password"]
                    # Для worker берём данные из index
                    if role == "worker":
                        meta["status"] = info.get("status", "created")
                    self._write_meta(account_dir, meta)
                    fixes.append(f"{role}: {email} — папка {account_id} отсутствовала, создана заново")
                    continue

                # 3. meta.json отсутствует или битый
                meta_path = account_dir / "meta.json"
                if not meta_path.exists():
                    meta = {"email": email, "password": ""}
                    if role == "worker":
                        meta["status"] = info.get("status", "created")
                        meta["admin_email"] = info.get("admin_email", "")
                    self._write_meta(account_dir, meta)
                    fixes.append(f"{role}: {email} — meta.json отсутствовал, создан заново")
                else:
                    try:
                        json.loads(meta_path.read_text())
                    except (json.JSONDecodeError, OSError):
                        backup = meta_path.with_suffix(".json.bak")
                        try:
                            meta_path.replace(backup)
                        except OSError:
                            pass
                        meta = {"email": email, "password": ""}
                        if role == "worker":
                            meta["status"] = info.get("status", "created")
                            meta["admin_email"] = info.get("admin_email", "")
                        self._write_meta(account_dir, meta)
                        fixes.append(f"{role}: {email} — meta.json повреждён, .bak сохранён")

            # 4. browser_profile отсутствует (данные есть, но куки нет)
            for email, info in index.items():
                account_id = info.get("id")
                if not account_id:
                    continue
                account_dir = role_dir / account_id
                profile_dir = account_dir / "browser_profile"
                if account_dir.exists() and not profile_dir.exists():
                    meta = self._read_meta(account_dir)
                    if meta.get("access_token") or meta.get("password"):
                        fixes.append(f"{role}: {email} — browser_profile отсутствует, нужен перелогин")

            for email in to_remove:
                index.pop(email, None)
                changed = True

            # 5. Сироты — папки есть, но в index их нет
            if role_dir.exists():
                indexed_ids = {info["id"] for info in index.values() if "id" in info}
                for child in role_dir.iterdir():
                    if not child.is_dir() or child.name == "__pycache__":
                        continue
                    if child.name not in indexed_ids:
                        # Пробуем восстановить из meta.json
                        meta = self._read_meta(child)
                        email = meta.get("email")
                        if email and email not in index:
                            entry: dict[str, Any] = {"id": child.name}
                            if role == "worker":
                                entry["status"] = meta.get("status", "created")
                                entry["admin_email"] = meta.get("admin_email", "")
                            index[email] = entry
                            changed = True
                            fixes.append(f"{role}: папка {child.name} ({email}) — добавлена в index")
                        elif not email:
                            fixes.append(f"{role}: папка-сирота {child.name} без meta — требует ручной проверки")

            # Миграция: admin_email из index в meta.json для воркеров
            if role == "worker":
                for w_email, w_info in index.items():
                    w_admin = w_info.get("admin_email", "")
                    w_id = w_info.get("id")
                    if not w_admin or not w_id:
                        continue
                    w_dir = role_dir / w_id
                    w_meta = self._read_meta(w_dir)
                    if w_meta and not w_meta.get("admin_email"):
                        w_meta["admin_email"] = w_admin
                        self._write_meta(w_dir, w_meta)
                        fixes.append(f"worker: {w_email} — admin_email мигрирован в meta.json")

            if changed or to_remove:
                self._write_index(role_dir, index)

        return fixes

    def _rebuild_index(self, role_dir: Path, role: str) -> dict:
        """Пересобрать index.json из существующих папок с meta.json."""
        index: dict[str, Any] = {}
        for child in role_dir.iterdir():
            if not child.is_dir():
                continue
            meta = self._read_meta(child)
            email = meta.get("email")
            if email:
                entry: dict[str, Any] = {"id": child.name}
                if role == "worker":
                    entry["status"] = meta.get("status", "created")
                    entry["admin_email"] = meta.get("admin_email", "")
                index[email] = entry
        self._write_index(role_dir, index)
        return index

    # --- Миграция ---

    def migrate_from_profiles(self) -> int:
        """Импорт из старого profiles.json в новую структуру. Возвращает кол-во мигрированных."""
        profiles_json = PROJECT_ROOT / "profiles.json"
        if not profiles_json.exists():
            return 0

        data = json.loads(profiles_json.read_text())
        count = 0

        # Админы — ключи верхнего уровня кроме _slots
        for email, info in data.items():
            if email.startswith("_"):
                continue
            if self.get_admin(email):
                continue
            admin = self.add_admin(email, info.get("password", ""))
            admin.access_token = info.get("access_token")
            admin.workspace_id = info.get("workspace_id")
            admin.account_id = info.get("account_id")
            admin.workspaces = info.get("workspaces")
            self.update_admin(admin)

            # Копируем browser_profile
            old_profile = info.get("profile_dir")
            if old_profile:
                old_path = Path(old_profile)
                if old_path.exists():
                    new_profile = self.admin_dir / admin.id / "browser_profile"
                    if not new_profile.exists():
                        shutil.copytree(old_path, new_profile)
            count += 1

        # Workers — из _slots
        slots_data = data.get("_slots", {})
        # Определяем admin_email (первый найденный админ)
        admin_email = ""
        for email in data:
            if not email.startswith("_"):
                admin_email = email
                break

        for email, info in slots_data.items():
            if self.get_worker(email):
                continue
            worker = self.add_worker(email, info.get("password", ""), admin_email)
            worker.status = info.get("status", "created")
            worker.access_token = info.get("access_token")
            worker.workspace_id = info.get("workspace_id")
            self.update_worker(worker)
            count += 1

        return count
