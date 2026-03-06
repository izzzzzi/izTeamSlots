"""IMAP mail provider.

Connects to any IMAP server to read mail. Useful when you have
your own domain or existing email accounts.

Configuration (env vars or constructor kwargs):
    IMAP_HOST       - IMAP server hostname (required)
    IMAP_PORT       - port (default: 993 for SSL, 143 for plain)
    IMAP_SSL        - "1" for SSL, "0" for STARTTLS/plain (default: "1")
    IMAP_FOLDER     - mailbox folder to read (default: "INBOX")
    IMAP_MAX_MESSAGES - max messages to fetch (default: 50, newest first)

Usage::

    provider = create_provider("imap", host="imap.example.com")
    inbox = provider.inbox(Mailbox(email="user@example.com", password="pass"))
"""
from __future__ import annotations

import email as email_lib
import imaplib
import os
import re
from email.header import decode_header as _decode_header
from typing import Any

from .base import (
    Inbox,
    Mail,
    MailAuthError,
    MailError,
    MailProvider,
    MailServiceUnavailable,
    Mailbox,
)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MULTI_SPACE_RE = re.compile(r"[ \t]+")
_MULTI_NL_RE = re.compile(r"\n{3,}")


def _html_to_text(html: str) -> str:
    """Rough HTML → plain text."""
    text = html.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    text = text.replace("</p>", "\n\n").replace("</div>", "\n")
    text = _HTML_TAG_RE.sub("", text)
    text = _MULTI_SPACE_RE.sub(" ", text)
    text = _MULTI_NL_RE.sub("\n\n", text)
    return text.strip()


def _decode_header_value(raw: str | None) -> str:
    if not raw:
        return ""
    parts = _decode_header(raw)
    decoded: list[str] = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return "".join(decoded)


def _extract_body(msg: email_lib.message.Message) -> str:  # type: ignore[type-arg]
    """Extract text body from an email message, preferring plain text."""
    if not msg.is_multipart():
        payload = msg.get_payload(decode=True)
        if not payload:
            return ""
        text = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
        if msg.get_content_type() == "text/html":
            return _html_to_text(text)
        return text

    plain_parts: list[str] = []
    html_parts: list[str] = []

    for part in msg.walk():
        ct = part.get_content_type()
        if ct == "multipart/alternative" or ct.startswith("multipart/"):
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        charset = part.get_content_charset() or "utf-8"
        text = payload.decode(charset, errors="replace")
        if ct == "text/plain":
            plain_parts.append(text)
        elif ct == "text/html":
            html_parts.append(text)

    if plain_parts:
        return "\n".join(plain_parts)
    if html_parts:
        return _html_to_text("\n".join(html_parts))
    return ""


class IMAPProvider(MailProvider):
    """IMAP mail provider — reads mail from any IMAP server."""

    name = "imap"

    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        use_ssl: bool | None = None,
        folder: str | None = None,
        max_messages: int | None = None,
        timeout: int = 30,
        **_kwargs: Any,
    ) -> None:
        self.host = host or os.environ.get("IMAP_HOST", "")
        if not self.host:
            raise MailError("IMAP_HOST is required (env var or host= kwarg)")

        ssl_env = os.environ.get("IMAP_SSL", "1")
        self.use_ssl = use_ssl if use_ssl is not None else (ssl_env == "1")

        default_port = 993 if self.use_ssl else 143
        self.port = port or int(os.environ.get("IMAP_PORT", str(default_port)))

        self.folder = folder or os.environ.get("IMAP_FOLDER", "INBOX")
        self.max_messages = max_messages or int(os.environ.get("IMAP_MAX_MESSAGES", "50"))
        self.timeout = timeout

    def _connect(self, mailbox: Mailbox) -> imaplib.IMAP4_SSL | imaplib.IMAP4:
        """Open an IMAP connection and authenticate."""
        try:
            if self.use_ssl:
                conn = imaplib.IMAP4_SSL(self.host, self.port, timeout=self.timeout)
            else:
                conn = imaplib.IMAP4(self.host, self.port, timeout=self.timeout)
        except (OSError, imaplib.IMAP4.error) as e:
            raise MailServiceUnavailable(f"Cannot connect to {self.host}:{self.port}: {e}") from e

        try:
            conn.login(mailbox.email, mailbox.password)
        except imaplib.IMAP4.error as e:
            err_msg = str(e)
            conn.logout()
            raise MailAuthError(f"IMAP login failed for {mailbox.email}: {err_msg}") from e

        return conn

    def generate(self) -> Mailbox:
        """IMAP cannot create mailboxes automatically.

        If you need auto-generation, consider subclassing and
        providing a pool of pre-created accounts.
        """
        raise NotImplementedError(
            "IMAP provider does not support generate(). "
            "Create mailboxes externally and use Mailbox(email=..., password=...)."
        )

    def inbox(self, mailbox: Mailbox) -> Inbox:
        """Fetch messages from IMAP server."""
        conn = self._connect(mailbox)
        messages: list[Mail] = []

        try:
            status, _ = conn.select(self.folder, readonly=True)
            if status != "OK":
                raise MailError(f"Cannot select folder {self.folder!r}")

            _, msg_nums_raw = conn.search(None, "ALL")
            all_nums = msg_nums_raw[0].split() if msg_nums_raw[0] else []

            # Newest first, limited
            fetch_nums = all_nums[-self.max_messages:]
            fetch_nums.reverse()

            if not fetch_nums:
                return Inbox(email=mailbox.email, messages=[])

            # Batch fetch for efficiency
            num_range = ",".join(n.decode() for n in fetch_nums)
            _, fetch_data = conn.fetch(num_range, "(RFC822)")

            for item in fetch_data:
                if not isinstance(item, tuple) or len(item) < 2:
                    continue

                raw_bytes = item[1]
                if not isinstance(raw_bytes, bytes):
                    continue

                msg = email_lib.message_from_bytes(raw_bytes)

                msg_id = msg.get("Message-ID", "")
                if not msg_id:
                    # Use IMAP sequence number from the fetch response
                    header = item[0]
                    if isinstance(header, bytes):
                        seq_match = re.match(rb"(\d+)", header)
                        msg_id = seq_match.group(1).decode() if seq_match else ""

                messages.append(Mail(
                    id=msg_id,
                    sender=_decode_header_value(msg.get("From", "")),
                    subject=_decode_header_value(msg.get("Subject", "")),
                    body=_extract_body(msg),
                    date=msg.get("Date", ""),
                ))

        except (MailError, MailAuthError):
            raise
        except imaplib.IMAP4.error as e:
            raise MailError(f"IMAP error: {e}") from e
        except Exception as e:
            raise MailError(f"Failed to read mail: {e}") from e
        finally:
            try:
                conn.logout()
            except Exception:
                pass

        return Inbox(email=mailbox.email, messages=messages)
