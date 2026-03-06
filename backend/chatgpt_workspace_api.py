from __future__ import annotations

import json
import time
from typing import Any

from .openai_web_auth import Page


class ChatGPTAPIError(Exception):
    def __init__(self, status: int, message: str) -> None:
        self.status = status
        self.message = message
        super().__init__(f"[{status}] {message}")


class ChatGPTWorkspaceAPI:
    """Обёртка над ChatGPT backend-api — запросы выполняются через браузер (page.evaluate)."""

    def __init__(self, page: Page, account_id: str, access_token: str) -> None:
        self.page = page
        self.account_id = account_id
        self.access_token = access_token

    def _request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
    ) -> Any:
        """Выполнить fetch() внутри браузера — куки и Cloudflare токены подхватываются автоматически."""
        url = f"https://chatgpt.com{path}"
        js_body = json.dumps(body) if body else "null"

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                result = self.page.evaluate(
                    """async ([url, method, body, token, accountId]) => {
                        const opts = {
                            method: method,
                            headers: {
                                "Content-Type": "application/json",
                                "Authorization": "Bearer " + token,
                                "chatgpt-account-id": accountId,
                            },
                        };
                        if (body && method !== 'GET' && method !== 'HEAD') opts.body = body;
                        const resp = await fetch(url, opts);
                        const text = await resp.text();
                        return {status: resp.status, body: text};
                    }""",
                    [url, method, js_body, self.access_token, self.account_id],
                )
            except Exception as e:
                if attempt < max_attempts:
                    time.sleep(2 ** attempt)
                    continue
                raise ChatGPTAPIError(0, f"Browser error: {e}") from e

            status = result["status"]
            raw_body = result["body"]

            if status in (429, 500, 502, 503, 504):
                if attempt < max_attempts:
                    time.sleep(2 ** attempt)
                    continue
                short = raw_body[:200] if len(raw_body) > 200 else raw_body
                raise ChatGPTAPIError(status, short)

            if status >= 400:
                short = raw_body[:200] if len(raw_body) > 200 else raw_body
                if status == 403:
                    short = "Cloudflare/доступ запрещён — токен протух, перелогинитесь"
                raise ChatGPTAPIError(status, short)

            return json.loads(raw_body) if raw_body else {}

        raise ChatGPTAPIError(0, "Max retries exceeded")

    def send_invites(self, emails: list[str]) -> dict:
        """Отправить инвайты в workspace."""
        return self._request(
            "POST",
            f"/backend-api/accounts/{self.account_id}/invites",
            body={
                "email_addresses": emails,
                "role": "standard-user",
                "resend_emails": True,
            },
        )

    def get_pending_invites(self) -> list[dict]:
        """Получить список ожидающих инвайтов."""
        data = self._request(
            "GET",
            f"/backend-api/accounts/{self.account_id}/invites?offset=0&limit=100",
        )
        return data.get("invites", [])

    def get_members(self) -> list[dict]:
        """Получить список участников workspace."""
        data = self._request(
            "GET",
            f"/backend-api/accounts/{self.account_id}/users?offset=0&limit=100",
        )
        return data.get("items", data.get("users", []))

    def delete_member(self, user_id: str) -> dict:
        """Удалить участника из workspace по user_id."""
        return self._request(
            "DELETE",
            f"/backend-api/accounts/{self.account_id}/users/{user_id}",
        )

    def delete_invite(self, email: str) -> dict:
        """Удалить инвайт."""
        return self._request(
            "DELETE",
            f"/backend-api/accounts/{self.account_id}/invites",
            body={"email_address": email},
        )
