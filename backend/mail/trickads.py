"""Mail provider: trickadsagencyltd.com temporary email service."""
from __future__ import annotations

import json
import re
from typing import Any

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

BASE_URL = "https://www.trickadsagencyltd.com"

HEADERS = {
    "accept": "*/*",
    "cache-control": "no-cache",
    "pragma": "no-cache",
    "origin": BASE_URL,
    "referer": f"{BASE_URL}/tepmail",
    "user-agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/142.0.0.0 Safari/537.36"
    ),
}


def _extract_html_comment(text: str) -> str:
    m = re.search(r"<!--\s*([\s\S]*?)\s*-->", text)
    if not m:
        return ""
    return m.group(1).strip().splitlines()[0][:300]


def _extract_error_summary(text: str) -> str:
    candidate = _extract_html_comment(text)
    if candidate:
        return candidate
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            for key in ("message", "error", "detail"):
                value = payload.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()[:300]
    except Exception:
        pass
    return text.strip().replace("\n", " ")[:300]


class TrickAdsProvider(MailProvider):
    """Temporary email via trickadsagencyltd.com/tepmail."""

    name = "trickads"

    def __init__(self, session: requests.Session | None = None) -> None:
        self._external = session is not None
        self._session = session or requests.Session()
        self._session.headers.update(HEADERS)

    def _request(
        self,
        endpoint: str,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            resp = self._session.post(f"{BASE_URL}{endpoint}", json=json_body)
            if resp.status_code != 200:
                body = resp.text or ""
                summary = _extract_error_summary(body)
                if resp.status_code == 401:
                    raise MailAuthError(f"[{resp.status_code}] {summary}")
                if resp.status_code >= 500:
                    raise MailServiceUnavailable(f"[{resp.status_code}] {summary}")
                raise MailError(f"[{resp.status_code}] {summary}")
            data: dict[str, Any] = resp.json()
        except requests.RequestException as e:
            raise MailServiceUnavailable(f"Connection error: {e}") from e

        if data.get("status") != "success":
            msg = data.get("message", "")
            code = data.get("code", 0)
            if code == 401 or "password" in msg.lower() or "unauthorized" in str(data.get("status", "")).lower():
                raise MailAuthError(f"API: {data}")
            raise MailError(f"API: {data}")
        return data

    def generate(self) -> Mailbox:
        data = self._request("/tepmail/generate")
        return Mailbox(email=data["email"], password=data["password"])

    def inbox(self, mailbox: Mailbox) -> Inbox:
        data = self._request(
            "/tepmail/inbox",
            json_body={"email": mailbox.email, "password": mailbox.password},
        )
        return Inbox(
            email=data["email"],
            messages=[
                Mail(
                    id=m["id"],
                    sender=m.get("from", ""),
                    subject=m.get("subject", ""),
                    body=m.get("body", ""),
                    date=m.get("date", ""),
                )
                for m in data.get("messages", [])
            ],
        )

    def close(self) -> None:
        if not self._external:
            self._session.close()
