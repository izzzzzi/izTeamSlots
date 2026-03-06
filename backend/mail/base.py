from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


class MailError(Exception):
    """Base exception for all mail provider errors."""


class MailAuthError(MailError):
    """Authentication failed (wrong password, expired token, etc.)."""


class MailServiceUnavailable(MailError):
    """Mail service is temporarily unavailable."""


@dataclass(frozen=True, slots=True)
class Mailbox:
    """Credentials for a single mailbox."""
    email: str
    password: str


@dataclass(frozen=True, slots=True)
class Mail:
    """A single email message."""
    id: str
    sender: str
    subject: str
    body: str
    date: str


@dataclass(frozen=True, slots=True)
class Inbox:
    """Inbox contents for a mailbox."""
    email: str
    messages: list[Mail]


class MailProvider(ABC):
    """Abstract base class for mail providers.

    To create a custom provider, subclass this and implement
    ``generate()`` and ``inbox()``.

    Minimal example::

        from backend.mail.base import MailProvider, Mailbox, Inbox

        class MyProvider(MailProvider):
            name = "my_provider"

            def generate(self) -> Mailbox:
                # create a new disposable mailbox
                ...

            def inbox(self, mailbox: Mailbox) -> Inbox:
                # fetch messages for the mailbox
                ...
    """

    name: str = "base"

    @abstractmethod
    def generate(self) -> Mailbox:
        """Create a new disposable mailbox.

        Returns a ``Mailbox`` with email and password (or token)
        that can later be passed to ``inbox()``.
        """

    @abstractmethod
    def inbox(self, mailbox: Mailbox) -> Inbox:
        """Fetch current messages for a mailbox."""

    def close(self) -> None:
        """Release resources (HTTP sessions, connections, etc.)."""

    def __enter__(self) -> MailProvider:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
