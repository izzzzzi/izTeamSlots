from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Any, Callable

from . import PROJECT_ROOT
from .account_store import AccountStore
from .dto import AdminRow, AppStateDTO, WorkerRow
from .mail import Mailbox, create_provider_for_mailbox
from .openai_web_auth import (
    close_browser as close_br,
)
from .openai_web_auth import (
    oauth_login,
    oauth_login_manual,
    open_browser,
    save_codex_file,
    wait_for_browser_close,
)
from .slot_orchestrator import SlotManager

LogFunc = Callable[[str], Any]
ProgressFunc = Callable[[int, int, str | None], None]


def _has_profile_files(profile_dir: Path) -> bool:
    return profile_dir.exists() and any(profile_dir.iterdir())


class UIFacade:
    def __init__(self, store: AccountStore | None = None) -> None:
        self.store = store or AccountStore()
        self.manager: SlotManager | None = None
        self.bootstrap()

    def bootstrap(self) -> None:
        profiles_json = PROJECT_ROOT / "profiles.json"
        admin_index_exists = (self.store.admin_dir / "index.json").exists()
        worker_index_exists = (self.store.worker_dir / "index.json").exists()

        auto_migrate_profiles = os.environ.get("IZTEAMSLOTS_AUTOMIGRATE_PROFILES") == "1"
        if auto_migrate_profiles and profiles_json.exists() and not admin_index_exists and not worker_index_exists:
            self.store.migrate_from_profiles()

        self.store.doctor()
        self.sync_codex_files()

    def shutdown(self) -> None:
        self.sync_codex_files()

    def sync_codex_files(self) -> None:
        codex_dir = PROJECT_ROOT / "codex"
        codex_dir.mkdir(parents=True, exist_ok=True)
        for src_dir in (self.store.admin_dir, self.store.worker_dir):
            if not src_dir.exists():
                continue
            for account_dir in src_dir.iterdir():
                if not account_dir.is_dir():
                    continue
                for f in account_dir.glob("codex-*.json"):
                    dst = codex_dir / f.name
                    if not dst.exists() or f.stat().st_mtime > dst.stat().st_mtime:
                        dst.write_text(f.read_text())

    def get_state(self) -> dict[str, Any]:
        raw_admins = self.store.list_admins()
        raw_workers = self.store.list_workers()
        admins = [
            AdminRow.from_account(
                a,
                has_browser_profile=_has_profile_files(self.store.get_admin_profile_dir(a)),
            )
            for a in raw_admins
        ]
        workers = [
            WorkerRow.from_account(
                w,
                has_browser_profile=_has_profile_files(self.store.get_worker_profile_dir(w)),
            )
            for w in raw_workers
        ]
        return AppStateDTO(admins=admins, workers=workers).to_dict()

    def add_admin(self, email: str, password: str) -> dict[str, Any]:
        admin = self.store.add_admin(email, password)
        return AdminRow.from_account(admin).__dict__

    def add_admin_manual(self, log: LogFunc) -> dict[str, Any]:
        temp_root = self.store.admin_dir / f"_manual_{uuid.uuid4().hex}"
        profile_dir = temp_root / "browser_profile"
        page = None
        created_admin_email: str | None = None

        try:
            page, session = oauth_login_manual(
                profile_dir=profile_dir,
                log=log,
            )
            email = str(session.get("email") or "").strip()
            if not email:
                raise RuntimeError("OAuth не вернул email, админ не создан")
            if self.store.get_admin(email):
                raise RuntimeError(f"Админ {email} уже существует")

            admin = self.store.add_admin(email, "")
            created_admin_email = email

            manager = SlotManager(store=self.store, admin_email=email, log=log)
            manager.finalize_admin_session(page, session)
            page = None

            target_profile_dir = self.store.get_admin_profile_dir(admin)
            if target_profile_dir.exists():
                shutil.rmtree(target_profile_dir)
            shutil.move(str(profile_dir), str(target_profile_dir))
            log(f"Профиль сохранён: {target_profile_dir}")

            self.sync_codex_files()
            log(f"Админ {email} добавлен через ручной логин")
            log("[предупреждение] Пароль почты не сохранён. Для почты и авто-входа добавьте его позже.")
            return AdminRow.from_account(
                self.store.get_admin(email) or admin,
                has_browser_profile=_has_profile_files(target_profile_dir),
            ).__dict__
        except Exception:
            if page is not None:
                try:
                    close_br(page, log=log)
                except Exception:
                    pass
            if created_admin_email:
                try:
                    self.store.delete_admin(created_admin_email)
                except Exception:
                    pass
            raise
        finally:
            if temp_root.exists():
                shutil.rmtree(temp_root, ignore_errors=True)

    def delete_admin(self, email: str) -> None:
        self.store.delete_admin(email)
        for w in self.store.list_workers():
            if w.admin_email == email:
                w.admin_email = None
                self.store.update_worker(w)
        if self.manager and self.manager.admin_email == email:
            self.manager = None

    def delete_worker(self, email: str) -> None:
        self.store.delete_worker(email)

    def open_admin_browser(self, email: str, log: LogFunc) -> None:
        admin = self.store.get_admin(email)
        if not admin:
            raise RuntimeError("Админ не найден")
        profile_dir = self.store.get_admin_profile_dir(admin)
        if not any(profile_dir.iterdir()):
            raise RuntimeError("Нет browser_profile, сначала перелогиньте админа")
        self._open_profile_browser(
            profile_dir, email, log,
            url="https://chatgpt.com/admin/members?tab=members",
        )

    def open_worker_browser(self, email: str, log: LogFunc) -> None:
        worker = self.store.get_worker(email)
        if not worker:
            raise RuntimeError("Слот не найден")
        profile_dir = self.store.get_worker_profile_dir(worker)
        if not any(profile_dir.iterdir()):
            raise RuntimeError("Нет browser_profile, сначала перелогиньте слот")
        self._open_profile_browser(profile_dir, email, log)

    def _open_profile_browser(
        self, profile_dir: Path, label: str, log: LogFunc, url: str = "https://chatgpt.com/",
    ) -> None:
        _page, context = open_browser(profile_dir, url=url, log=log)
        log(f"Браузер {label} открыт. Закройте окно браузера для возврата.")
        wait_for_browser_close(context, log=log)

    def _replace_manager(self, manager: SlotManager) -> None:
        if self.manager:
            try:
                self.manager.close()
            except Exception:
                pass
        self.manager = manager

    def login_admin(self, email: str, log: LogFunc) -> None:
        manager = SlotManager(store=self.store, admin_email=email, log=log)
        self._replace_manager(manager)
        manager.login_admin()
        self.sync_codex_files()

    def login_admin_manual(self, email: str, log: LogFunc) -> None:
        manager = SlotManager(store=self.store, admin_email=email, log=log)
        self._replace_manager(manager)
        manager.login_admin_manual()
        self.sync_codex_files()

    def run_slots_pipeline(
        self,
        admin_email: str,
        count: int,
        log: LogFunc,
        progress: ProgressFunc | None = None,
    ) -> dict[str, int]:
        manager = SlotManager(store=self.store, admin_email=admin_email, log=log, headless=False)
        self._replace_manager(manager)
        ok = 0
        for i in range(count):
            slot_no = i + 1
            log(f"--- Слот {slot_no}/{count} ---")
            if progress:
                progress(slot_no, count, f"slot {slot_no}/{count}")
            try:
                manager.create_invite_login_one()
                ok += 1
            except Exception as e:
                log(f"Ошибка: {e}")
        manager._close_admin_page()
        log(f"Готово: {ok}/{count} слотов")
        self.sync_codex_files()
        return {"ok": ok, "total": count}

    def relogin_worker_email(self, email: str, log: LogFunc) -> bool:
        worker = self.store.get_worker(email)
        if not worker:
            log(f"Worker {email} не найден")
            return False
        if not worker.openai_password:
            log(f"{email} — нет openai_password")
            return False

        mail = create_provider_for_mailbox(Mailbox(email=worker.email, password=worker.password))
        try:
            mailbox = Mailbox(email=worker.email, password=worker.password)
            profile_dir = self.store.get_worker_profile_dir(worker)

            page, session = oauth_login(
                email=worker.email,
                password=worker.openai_password or worker.password,
                mail_client=mail,
                mailbox=mailbox,
                profile_dir=profile_dir,
                log=log,
                headless=False,
            )

            if session.get("access_token"):
                worker.access_token = session["access_token"]
                if session.get("account_id"):
                    worker.workspace_id = session["account_id"]
                self.store.update_worker(worker)

                worker_dir = self.store.worker_dir / worker.id
                codex_path = save_codex_file(worker_dir, session, email)
                log(f"Codex обновлён: {codex_path.name}")
            else:
                log("Нет access_token — codex не сохранён")
                close_br(page, log=log)
                return False

            close_br(page, log=log)
            log(f"{email} перелогинен")
            self.sync_codex_files()
            return True
        finally:
            mail.close()

    def relogin_all_workers(
        self,
        log: LogFunc,
        progress: ProgressFunc | None = None,
    ) -> dict[str, int]:
        workers = self.store.list_workers()
        eligible = [w.email for w in workers if w.openai_password]
        if not eligible:
            log("Нет слотов с openai_password")
            return {"ok": 0, "total": 0}

        ok = 0
        total = len(eligible)
        for i, email in enumerate(eligible, start=1):
            log(f"--- Перелогин {i}/{total}: {email} ---")
            if progress:
                progress(i, total, email)
            if self.relogin_worker_email(email, log):
                ok += 1
        log(f"Готово: {ok}/{total}")
        self.sync_codex_files()
        return {"ok": ok, "total": total}

