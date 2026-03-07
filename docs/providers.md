# Почтовые провайдеры

Система почты в `izTeamSlots` построена на плагинах: есть базовый контракт `MailProvider` и набор конкретных реализаций.

## Встроенные провайдеры

| Провайдер | Модуль | Описание | Env-переменные |
|-----------|--------|----------|----------------|
| `boomlify` | `backend/mail/boomlify.py` | Boomlify Temp Mail API, по умолчанию для слотов | `BOOMLIFY_API_KEY`, `BOOMLIFY_DOMAIN`, `BOOMLIFY_TIME` |
| `trickads` | `backend/mail/trickads.py` | Временная почта для админов по умолчанию | — |
| `imap` | `backend/mail/imap.py` | Любой IMAP-сервер | `IMAP_HOST`, `IMAP_PORT`, `IMAP_SSL`, `IMAP_FOLDER` |

## Как выбирается провайдер

- `create_provider(name)` — создаёт провайдер по имени или через `MAIL_PROVIDER`
- `create_slot_provider(name)` — создаёт провайдер для слотов через `SLOT_MAIL_PROVIDER`
- `create_provider_for_mailbox(mailbox)` — пытается определить провайдер по данным `Mailbox`

## Контракт `MailProvider`

Наследуйте `MailProvider` из `backend/mail/base.py` и реализуйте два метода:

```python
from backend.mail.base import MailProvider, Mailbox, Inbox

class MyProvider(MailProvider):
    name = "my_provider"

    def generate(self) -> Mailbox:
        ...

    def inbox(self, mailbox: Mailbox) -> Inbox:
        ...
```

Ожидания:
- `generate()` создаёт новый ящик и возвращает `Mailbox(email, password)`
- `inbox()` возвращает `Inbox` с письмами для этого ящика

## Как добавить свой провайдер

1. Создайте новый модуль в `backend/mail/`.
2. Реализуйте класс-провайдер на базе `MailProvider`.
3. Зарегистрируйте его в `backend/mail/__init__.py`.
4. Укажите его имя в `MAIL_PROVIDER` или `SLOT_MAIL_PROVIDER`.

## Когда нужен свой провайдер

- нужен другой temp-mail API
- нужен корпоративный IMAP
- нужно разделить провайдеры для админов и слотов
- нужно контролировать домены / TTL / rate limits
