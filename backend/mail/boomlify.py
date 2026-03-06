"""Mail provider: Boomlify Temp Mail API."""
from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlencode

import requests

from .base import (
    Inbox,
    Mail,
    MailAuthError,
    Mailbox,
    MailError,
    MailProvider,
    MailServiceUnavailable,
)

DEFAULT_BASE_URL = "https://v1.boomlify.com"
DEFAULT_TIME = "permanent"


def _unwrap_payload(data: Any) -> Any:
    if isinstance(data, dict):
        for key in ("data", "result", "email", "message", "messages"):
            value = data.get(key)
            if value is not None:
                return value
    return data


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _pick_first_str(obj: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


class BoomlifyProvider(MailProvider):
    """Temporary email via Boomlify API."""

    name = "boomlify"
    password_prefix = "boomlify:"

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        mailbox_time: str | None = None,
        domain: str | None = None,
        session: requests.Session | None = None,
        **_kwargs: Any,
    ) -> None:
        self.api_key = api_key or os.environ.get("BOOMLIFY_API_KEY", "").strip()
        if not self.api_key:
            raise MailAuthError("BOOMLIFY_API_KEY is required for Boomlify mail provider")

        self.base_url = (base_url or os.environ.get("BOOMLIFY_BASE_URL", DEFAULT_BASE_URL)).rstrip("/")
        self.mailbox_time = mailbox_time or os.environ.get("BOOMLIFY_TIME", DEFAULT_TIME)
        self.domain = domain or os.environ.get("BOOMLIFY_DOMAIN", "").strip()
        self._external = session is not None
        self._session = session or requests.Session()
        self._session.headers.update({
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "izTeamSlots/1.0",
        })

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        json_body: dict[str, Any] | None = None,
        query: dict[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}{endpoint}"
        if query:
            clean_query = {k: v for k, v in query.items() if v is not None and v != ""}
            if clean_query:
                url = f"{url}?{urlencode(clean_query)}"

        try:
            resp = self._session.request(method, url, json=json_body, timeout=30)
        except requests.RequestException as e:
            raise MailServiceUnavailable(f"Connection error: {e}") from e

        try:
            data = resp.json()
        except ValueError:
            data = {"error": resp.text.strip()[:500]}

        if resp.status_code in (401, 403):
            raise MailAuthError(f"[{resp.status_code}] {data}")
        if resp.status_code in (429, 500, 502, 503, 504):
            raise MailServiceUnavailable(f"[{resp.status_code}] {data}")
        if resp.status_code >= 400:
            raise MailError(f"[{resp.status_code}] {data}")
        return data

    def _extract_mailbox_id(self, mailbox: Mailbox) -> str:
        password = mailbox.password.strip()
        if password.startswith(self.password_prefix):
            return password[len(self.password_prefix) :].strip()
        if password:
            return password
        raise MailError(
            f"Mailbox {mailbox.email} does not contain Boomlify mailbox id. "
            "Expected Mailbox.password to store the Boomlify email id."
        )

    def generate(self) -> Mailbox:
        payload: dict[str, Any] = {"time": self.mailbox_time}
        if self.domain:
            payload["domain"] = self.domain

        raw = self._request("POST", "/api/v1/emails/create", json_body=payload)
        email_data = _as_dict(_unwrap_payload(raw))
        email = _pick_first_str(email_data, ("email", "address"))
        email_id = _pick_first_str(email_data, ("id", "email_id", "uuid"))

        if not email or not email_id:
            raise MailError(f"Unexpected Boomlify create response: {raw}")

        return Mailbox(email=email, password=f"{self.password_prefix}{email_id}")

    def inbox(self, mailbox: Mailbox) -> Inbox:
        email_id = self._extract_mailbox_id(mailbox)
        raw = self._request(
            "GET",
            f"/api/v1/emails/{email_id}/messages",
            query={"limit": 100, "offset": 0},
        )

        messages_raw: list[Any] = []
        if isinstance(raw, dict):
            messages_raw = _as_list(raw.get("messages")) or _as_list(raw.get("items"))
        if not messages_raw:
            payload = _unwrap_payload(raw)
            messages_raw = _as_list(payload)

        messages: list[Mail] = []
        for item in messages_raw:
            msg = _as_dict(item)
            sender_value = msg.get("from")
            sender = _pick_first_str(msg, ("from_email", "from_name"))
            if not sender:
                if isinstance(sender_value, dict):
                    sender = _pick_first_str(sender_value, ("email", "address", "name"))
                elif isinstance(sender_value, str):
                    sender = sender_value.strip()

            body = _pick_first_str(msg, ("body_html", "html", "body_text", "body", "text", "content"))
            messages.append(
                Mail(
                    id=_pick_first_str(msg, ("id", "message_id", "uuid")) or body[:32],
                    sender=sender,
                    subject=_pick_first_str(msg, ("subject", "title")),
                    body=body,
                    date=_pick_first_str(msg, ("date", "created_at", "received_at", "timestamp")),
                )
            )

        return Inbox(email=mailbox.email, messages=messages)

    def close(self) -> None:
        if not self._external:
            self._session.close()
