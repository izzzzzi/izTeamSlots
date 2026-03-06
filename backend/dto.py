from __future__ import annotations

from dataclasses import asdict, dataclass

from .account_store import AdminAccount, WorkerAccount


@dataclass
class AdminRow:
    email: str
    has_access_token: bool
    has_browser_profile: bool
    workspace_id: str | None
    workspace_count: int
    created_at: str | None
    last_login: str | None
    status_label: str

    @classmethod
    def from_account(
        cls,
        account: AdminAccount,
        *,
        has_browser_profile: bool = False,
    ) -> "AdminRow":
        has_access_token = bool(account.access_token)
        workspace_count = len(account.workspaces or [])
        if has_access_token and has_browser_profile:
            status_label = "Готов"
        elif has_access_token:
            status_label = "Есть токен"
        elif has_browser_profile:
            status_label = "Нужен вход"
        else:
            status_label = "Не настроен"

        return cls(
            email=account.email,
            has_access_token=has_access_token,
            has_browser_profile=has_browser_profile,
            workspace_id=account.workspace_id,
            workspace_count=workspace_count,
            created_at=account.created_at,
            last_login=account.last_login,
            status_label=status_label,
        )


@dataclass
class WorkerRow:
    email: str
    status: str
    has_access_token: bool
    has_browser_profile: bool
    workspace_id: str | None
    admin_email: str | None
    has_openai_password: bool
    created_at: str | None
    status_label: str

    @classmethod
    def from_account(
        cls,
        account: WorkerAccount,
        *,
        has_browser_profile: bool = False,
    ) -> "WorkerRow":
        has_access_token = bool(account.access_token)
        if has_access_token and has_browser_profile:
            status_label = "Готов"
        elif account.status == "registered":
            status_label = "Зарегистрирован"
        elif account.status == "invited":
            status_label = "Инвайт отправлен"
        elif account.status == "created":
            status_label = "Создан"
        else:
            status_label = account.status

        return cls(
            email=account.email,
            status=account.status,
            has_access_token=has_access_token,
            has_browser_profile=has_browser_profile,
            workspace_id=account.workspace_id,
            admin_email=account.admin_email,
            has_openai_password=bool(account.openai_password),
            created_at=account.created_at,
            status_label=status_label,
        )


@dataclass
class MailAccountRow:
    kind: str
    email: str


@dataclass
class AppStateDTO:
    admins: list[AdminRow]
    workers: list[WorkerRow]
    accounts: list[MailAccountRow]

    def to_dict(self) -> dict:
        return asdict(self)
