"""Pluggable mail provider system.

Usage::

    from backend.mail import create_provider, Mailbox

    provider = create_provider()          # generic/default: "trickads"
    mailbox = provider.generate()         # create disposable mailbox
    inbox = provider.inbox(mailbox)       # fetch messages
    provider.close()

    slot_provider = create_slot_provider()  # slots default: "boomlify"

Select provider via env var or name::

    MAIL_PROVIDER=imap IMAP_HOST=imap.example.com python app.py

    provider = create_provider("imap", host="imap.example.com")

Available providers:
    trickads - trickadsagencyltd.com temp mail (generic/default)
    boomlify - Boomlify temp mail API (slots default)
    imap     - any IMAP server (env: IMAP_HOST, IMAP_PORT, IMAP_SSL)

Custom providers:
    Subclass ``MailProvider`` from ``backend.mail.base`` and implement
    ``generate()`` and ``inbox()``.
"""
from __future__ import annotations

import os
from typing import Any

from .base import Inbox, Mail, MailAuthError, Mailbox, MailError, MailProvider, MailServiceUnavailable

__all__ = [
    "Inbox",
    "Mail",
    "MailAuthError",
    "MailError",
    "MailProvider",
    "MailServiceUnavailable",
    "Mailbox",
    "create_provider",
    "create_provider_for_mailbox",
    "create_slot_provider",
]

_BUILTIN_PROVIDERS = ("boomlify", "trickads", "imap")


def create_provider(name: str | None = None, **kwargs: Any) -> MailProvider:
    """Create a mail provider instance by name.

    Args:
        name: Provider name. Defaults to ``MAIL_PROVIDER`` env var,
              then falls back to ``"trickads"``.
        **kwargs: Passed to provider constructor.
    """
    provider_name = name or os.environ.get("MAIL_PROVIDER", "trickads")

    if provider_name == "boomlify":
        from .boomlify import BoomlifyProvider
        return BoomlifyProvider(**kwargs)

    if provider_name == "trickads":
        from .trickads import TrickAdsProvider
        return TrickAdsProvider(**kwargs)

    if provider_name == "imap":
        from .imap import IMAPProvider
        return IMAPProvider(**kwargs)

    raise ValueError(
        f"Unknown mail provider: {provider_name!r}. "
        f"Available: {', '.join(_BUILTIN_PROVIDERS)}"
    )


def create_slot_provider(name: str | None = None, **kwargs: Any) -> MailProvider:
    """Create provider for worker/slot mailboxes.

    Defaults to ``SLOT_MAIL_PROVIDER``, then falls back to ``"boomlify"``.
    """
    provider_name = name or os.environ.get("SLOT_MAIL_PROVIDER", "boomlify")
    return create_provider(provider_name, **kwargs)


def create_provider_for_mailbox(mailbox: Mailbox, **kwargs: Any) -> MailProvider:
    """Pick provider based on stored mailbox credentials.

    Boomlify mailboxes store their email id inside ``Mailbox.password`` as
    ``boomlify:<uuid>``. Everything else falls back to the generic provider.
    """
    password = mailbox.password.strip()
    if password.startswith("boomlify:"):
        return create_provider("boomlify", **kwargs)
    return create_provider(**kwargs)
