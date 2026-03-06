from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Callable

from .account_store import AccountStore, AdminAccount, WorkerAccount
from .chatgpt_workspace_api import ChatGPTWorkspaceAPI
from .mail import Mailbox, MailProvider, create_provider, create_slot_provider
from .openai_web_auth import (
    Page,
    browser_register,
    close_browser,
    ensure_chatgpt_web_session,
    get_workspaces,
    make_openai_password,
    oauth_login,
    oauth_login_manual,
    open_browser,
    poll_for_invite,
    save_codex_file,
    select_workspace,
)


class SlotManager:
    """Оркестратор: создание почт -> инвайты -> логин слотов."""

    def __init__(
        self,
        store: AccountStore,
        admin_email: str,
        log: Callable[[str], Any] | None = None,
        headless: bool = False,
    ) -> None:
        self.store = store
        self.admin_email = admin_email
        self._admin: AdminAccount | None = store.get_admin(admin_email)
        self._slot_mail: MailProvider | None = None
        self._admin_mail: MailProvider | None = None
        self._mailboxes: dict[str, Mailbox] = {}
        self._log = log or print
        self._admin_page: Page | None = None
        self._headless = headless

    @property
    def access_token(self) -> str | None:
        return self._admin.access_token if self._admin else None

    @property
    def workspace_id(self) -> str | None:
        return self._admin.workspace_id if self._admin else None

    @property
    def account_id(self) -> str | None:
        return self._admin.account_id if self._admin else None

    def _get_slot_mail(self) -> MailProvider:
        if self._slot_mail is None:
            self._slot_mail = create_slot_provider()
        return self._slot_mail

    def _get_admin_mail(self) -> MailProvider:
        if self._admin_mail is None:
            self._admin_mail = create_provider()
        return self._admin_mail

    def _get_workers(self) -> list[WorkerAccount]:
        return [w for w in self.store.list_workers() if w.admin_email == self.admin_email]

    def _ensure_admin_page(self) -> Page:
        """Открыть браузер админа если ещё не открыт. Возвращает page."""
        if self._admin_page is not None:
            try:
                _ = self._admin_page.url
                return self._admin_page
            except Exception:
                self._admin_page = None

        if not self._admin:
            raise RuntimeError(f"Админ {self.admin_email} не найден")

        profile_dir = self.store.get_admin_profile_dir(self._admin)
        self._log("Открываю браузер админа для API...")
        page, _context = open_browser(profile_dir, log=self._log, headless=self._headless)
        self._admin_page = page
        return page

    def _close_admin_page(self) -> None:
        """Закрыть браузер админа."""
        if self._admin_page:
            try:
                close_browser(self._admin_page, log=self._log)
            except Exception:
                pass
            self._admin_page = None

    def _get_api(self, page: Page) -> ChatGPTWorkspaceAPI:
        """Создать ChatGPTWorkspaceAPI с привязкой к странице браузера."""
        if not self.account_id or not self.access_token:
            raise RuntimeError("account_id/access_token не установлены — сначала login_admin()")
        return ChatGPTWorkspaceAPI(page, self.account_id, self.access_token)

    def _finalize_admin_login(
        self,
        page: Page,
        session: dict[str, Any],
        *,
        manual_web_flow: bool = False,
    ) -> None:
        if not self._admin:
            raise RuntimeError(f"Админ {self.admin_email} не найден в AccountStore")

        self._admin.access_token = session["access_token"]
        if session.get("account_id"):
            self._admin.account_id = session["account_id"]
            self._admin.workspace_id = session["account_id"]

        # Проверяем workspaces на chatgpt.com
        if "/workspace" in page.url:
            workspaces = get_workspaces(page, log=self._log)
            if workspaces:
                self._admin.workspaces = workspaces
                self._log(
                    "Доступные workspace: "
                    + ", ".join(f"{ws.get('name', '?')} [{ws.get('workspace_id', '?')}]" for ws in workspaces)
                )

                if manual_web_flow:
                    self._log("Ручной режим: workspace не выбираю автоматически.")
                else:
                    available_ids = {str(ws["workspace_id"]) for ws in workspaces if ws.get("workspace_id")}
                    target_workspace_id = self._admin.workspace_id if self._admin.workspace_id in available_ids else None
                    if self._admin.workspace_id and not target_workspace_id:
                        self._log(
                            f"[предупреждение] Workspace из OAuth ({self._admin.workspace_id}) не найден среди кнопок на странице"
                        )

                    if not target_workspace_id:
                        for ws in workspaces:
                            name = str(ws.get("name", ""))
                            workspace_id = str(ws.get("workspace_id", ""))
                            if workspace_id and "Личная" not in name and "Personal" not in name:
                                target_workspace_id = workspace_id
                                break

                    if not target_workspace_id and workspaces:
                        target_workspace_id = str(workspaces[0]["workspace_id"])

                    self._admin.workspace_id = target_workspace_id
                    if target_workspace_id:
                        select_workspace(page, target_workspace_id, log=self._log)
                        self._admin.account_id = target_workspace_id
                        if not ensure_chatgpt_web_session(page, self._log, timeout_seconds=45, open_home=True):
                            raise RuntimeError(
                                "Не удалось подтвердить web-сессию chatgpt.com после выбора workspace"
                            )

        close_browser(page, log=self._log)
        self._admin.last_login = datetime.now(timezone.utc).isoformat()
        self.store.update_admin(self._admin)

        # Сохраняем codex-файл
        try:
            admin_dir = self.store.admin_dir / self._admin.id
            codex_path = save_codex_file(admin_dir, session, self._admin.email)
            self._log(f"Codex-файл: {codex_path.name}")
        except RuntimeError as e:
            self._log(f"[предупреждение] {e}")
        self._log("Админ авторизован!")

    def finalize_admin_session(self, page: Page, session: dict[str, Any]) -> None:
        self._finalize_admin_login(page, session, manual_web_flow=True)

    def login_admin(self) -> None:
        raise RuntimeError("Авто-вход админа временно отключён. Используйте ручной вход через браузер.")

    def login_admin_manual(self) -> None:
        """Ручной логин админа в браузере с последующим автоматическим сохранением токенов."""
        if not self._admin:
            raise RuntimeError(f"Админ {self.admin_email} не найден в AccountStore")

        profile_dir = self.store.get_admin_profile_dir(self._admin)
        self._log("Ручной логин админа...")
        page, session = oauth_login_manual(
            profile_dir=profile_dir,
            expected_email=self._admin.email,
            log=self._log,
        )
        if session.get("email") and session["email"] != self._admin.email:
            self._log(f"[предупреждение] Вошли как {session['email']}, а не как {self._admin.email}")
        self._finalize_admin_login(page, session, manual_web_flow=True)

    def create_slots(self, count: int) -> list[WorkerAccount]:
        """Создать N временных почт."""
        mail = self._get_slot_mail()
        new_workers = []
        for i in range(count):
            self._log(f"Создаю почту {i+1}/{count}...")
            mailbox = mail.generate()
            worker = self.store.add_worker(mailbox.email, mailbox.password, self.admin_email)
            self._mailboxes[mailbox.email] = mailbox
            new_workers.append(worker)
            self._log(f"  {mailbox.email}")

        self._log(f"Создано {count} почтовых ящиков")
        return new_workers

    def send_invites(self, emails: list[str] | None = None) -> dict:
        """Отправить инвайты через браузер админа."""
        workers = self._get_workers()
        target_emails = emails or [w.email for w in workers if w.status == "created"]
        if not target_emails:
            self._log("Нет email-ов для инвайтов")
            return {}

        page = self._ensure_admin_page()
        api = self._get_api(page)

        self._log(f"Отправляю инвайты: {len(target_emails)} шт...")
        result = api.send_invites(target_emails)

        for w in workers:
            if w.email in target_emails:
                w.status = "invited"
                self.store.update_worker(w)

        self._log("Инвайты отправлены!")
        return result

    def create_invite_login_one(self) -> WorkerAccount:
        """Создать 1 почту → инвайт → регистрация → логин."""
        mail = self._get_slot_mail()

        # 1. Создать почту
        self._log("Создаю почту...")
        mailbox = mail.generate()
        worker = self.store.add_worker(mailbox.email, mailbox.password, self.admin_email)
        self._mailboxes[mailbox.email] = mailbox
        self._log(f"  {mailbox.email}")

        # Запоминаем письма ДО инвайта
        existing_ids: set[str] = set()
        try:
            inbox = mail.inbox(mailbox)
            existing_ids = {msg.id for msg in inbox.messages}
        except Exception:
            self._log("Не удалось прочитать inbox, продолжаю")

        # 2. Отправить инвайт через браузер админа
        page = self._ensure_admin_page()
        api = self._get_api(page)

        self._log(f"Отправляю инвайт {mailbox.email}...")
        api.send_invites([mailbox.email])
        worker.status = "invited"
        self.store.update_worker(worker)
        self._log("Инвайт отправлен")

        try:
            # 3. Ждём письмо с инвайт-ссылкой
            self._log("Ожидаю письмо с инвайтом...")
            invite_url = poll_for_invite(
                mail, mailbox, existing_ids, log=self._log,
            )

            # 4. Регистрация по инвайт-ссылке
            openai_pwd = make_openai_password(mailbox.password)
            worker.openai_password = openai_pwd
            self.store.update_worker(worker)

            self.register_slot(worker, invite_url)
        except Exception as e:
            self._log(f"Ошибка: {e}")
            self._cleanup_failed_worker(worker, api)
            raise
        return worker

    def _cleanup_failed_worker(self, worker: WorkerAccount, api: ChatGPTWorkspaceAPI) -> None:
        """Удалить worker из workspace и локальных данных если регистрация не удалась."""
        self._log(f"Очистка: удаляю {worker.email}...")
        try:
            members = api.get_members()
            for m in members:
                if m.get("email") == worker.email:
                    api.delete_member(m["id"])
                    self._log(f"Удалён из workspace: {worker.email}")
                    break
            else:
                try:
                    api.delete_invite(worker.email)
                    self._log(f"Инвайт удалён: {worker.email}")
                except Exception:
                    pass
        except Exception as ex:
            self._log(f"Не удалось очистить workspace: {ex}")
        try:
            self.store.delete_worker(worker.email)
            self._log(f"Локальная запись удалена: {worker.email}")
        except Exception as ex:
            self._log(f"Не удалось удалить локально: {ex}")

    def get_pending_invites(self) -> list[dict]:
        page = self._ensure_admin_page()
        api = self._get_api(page)
        return api.get_pending_invites()

    def get_members(self) -> list[dict]:
        page = self._ensure_admin_page()
        api = self._get_api(page)
        return api.get_members()

    def register_slot(self, worker: WorkerAccount, invite_url: str) -> None:
        """Зарегистрировать приглашённый аккаунт через инвайт-ссылку."""
        mailbox = self._mailboxes.get(worker.email)
        if not mailbox:
            mailbox = Mailbox(email=worker.email, password=worker.password)
            self._mailboxes[worker.email] = mailbox

        profile_dir = self.store.get_worker_profile_dir(worker)
        mail = self._get_slot_mail()
        openai_pwd = worker.openai_password or make_openai_password(worker.password)

        self._log(f"Регистрация слота: {worker.email}")
        page = browser_register(
            invite_url=invite_url,
            email=worker.email,
            openai_password=openai_pwd,
            mail_client=mail,
            mailbox=mailbox,
            profile_dir=profile_dir,
            log=self._log,
            headless=self._headless,
        )

        # Закрываем браузер регистрации
        close_browser(page, log=self._log)
        time.sleep(2)

        worker.status = "registered"
        if not worker.openai_password:
            worker.openai_password = openai_pwd
        worker.workspace_id = self.workspace_id
        self.store.update_worker(worker)

        # Полный OAuth логин (как при перелогине) — получаем все токены
        self._log(f"OAuth логин {worker.email}...")
        page2: Page | None = None
        oauth_ok = False
        try:
            page2, session = oauth_login(
                email=worker.email,
                password=openai_pwd,
                mail_client=mail,
                mailbox=mailbox,
                profile_dir=profile_dir,
                log=self._log,
                headless=self._headless,
            )
            if session and session.get("access_token"):
                worker.access_token = session["access_token"]
                if session.get("account_id"):
                    worker.workspace_id = session["account_id"]
                self.store.update_worker(worker)

                worker_dir = self.store.worker_dir / worker.id
                codex_path = save_codex_file(worker_dir, session, worker.email)
                self._log(f"Codex-файл: {codex_path.name}")
                oauth_ok = True
            else:
                self._log(f"OAuth: нет access_token для {worker.email}")
        except Exception as e:
            self._log(f"OAuth логин не удался: {e}")
        finally:
            if page2:
                close_browser(page2, log=self._log)

        if oauth_ok:
            self._log(f"Слот {worker.email} готов")
        else:
            self._log(f"Слот {worker.email} зарегистрирован, но OAuth не завершён — нужен перелогин")

    def get_status(self) -> dict:
        workers = self._get_workers()
        created = sum(1 for w in workers if w.status == "created")
        invited = sum(1 for w in workers if w.status == "invited")
        registered = sum(1 for w in workers if w.status == "registered")
        return {
            "total": len(workers),
            "created": created,
            "invited": invited,
            "registered": registered,
            "admin_logged_in": self.access_token is not None,
            "workspace_id": self.workspace_id,
        }

    def close(self) -> None:
        self._close_admin_page()
        if self._slot_mail:
            self._slot_mail.close()
        if self._admin_mail:
            self._admin_mail.close()
