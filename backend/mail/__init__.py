"""Pluggable mail provider system with auto-discovery.

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

Custom providers:
    Create a .py file in backend/mail/, subclass MailProvider, set ``name``
    and optionally ``password_prefix``. The provider will be discovered
    automatically — no edits to __init__.py needed.
"""
from __future__ import annotations

import importlib
import os
import pkgutil
from pathlib import Path
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

_REGISTRY: dict[str, type[MailProvider]] | None = None


def _discover_providers() -> dict[str, type[MailProvider]]:
    """Scan this package for MailProvider subclasses and build a registry."""
    registry: dict[str, type[MailProvider]] = {}
    package_dir = Path(__file__).parent

    for module_info in pkgutil.iter_modules([str(package_dir)]):
        if module_info.name.startswith("_") or module_info.name == "base":
            continue
        try:
            module = importlib.import_module(f".{module_info.name}", __package__)
        except Exception:
            continue
        for attr in vars(module).values():
            if (
                isinstance(attr, type)
                and issubclass(attr, MailProvider)
                and attr is not MailProvider
                and attr.name != "base"
            ):
                registry[attr.name] = attr

    return registry


def _get_registry() -> dict[str, type[MailProvider]]:
    global _REGISTRY  # noqa: PLW0603
    if _REGISTRY is None:
        _REGISTRY = _discover_providers()
    return _REGISTRY


def create_provider(name: str | None = None, **kwargs: Any) -> MailProvider:
    """Create a mail provider instance by name.

    Args:
        name: Provider name. Defaults to ``MAIL_PROVIDER`` env var,
              then falls back to ``"trickads"``.
        **kwargs: Passed to provider constructor.
    """
    provider_name = name or os.environ.get("MAIL_PROVIDER", "trickads")
    registry = _get_registry()
    cls = registry.get(provider_name)
    if cls is None:
        available = ", ".join(sorted(registry)) or "(none)"
        raise ValueError(f"Unknown mail provider: {provider_name!r}. Available: {available}")
    return cls(**kwargs)


def create_slot_provider(name: str | None = None, **kwargs: Any) -> MailProvider:
    """Create provider for worker/slot mailboxes.

    Defaults to ``SLOT_MAIL_PROVIDER``, then falls back to ``"boomlify"``.
    """
    provider_name = name or os.environ.get("SLOT_MAIL_PROVIDER", "boomlify")
    return create_provider(provider_name, **kwargs)


def create_provider_for_mailbox(mailbox: Mailbox, **kwargs: Any) -> MailProvider:
    """Pick provider based on stored mailbox credentials.

    Checks ``password_prefix`` of each registered provider first,
    then falls back to the default provider.
    """
    password = mailbox.password.strip()
    registry = _get_registry()

    for cls in registry.values():
        if cls.password_prefix and password.startswith(cls.password_prefix):
            return cls(**kwargs)

    return create_provider(**kwargs)
