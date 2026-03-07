# Участие в разработке izTeamSlots

Спасибо за интерес к проекту! Это руководство поможет начать.

## Подготовка окружения

1. Форкните [izzzzzi/izTeamSlots](https://github.com/izzzzzi/izTeamSlots)
2. Клонируйте форк:
   ```bash
   git clone https://github.com/<your-username>/izTeamSlots.git
   cd izTeamSlots
   ```
3. Установите зависимости:
   ```bash
   npm install
   ```
   Скрипт автоматически поставит Python 3.11+, [uv](https://docs.astral.sh/uv/), [Bun](https://bun.sh) и все зависимости.

4. Создайте `.env` и добавьте ключи:
   ```bash
   cp .env.example .env
   ```

5. Создайте ветку:
   ```bash
   git checkout -b feat/my-feature
   ```

## Структура проекта

```text
izTeamSlots/
├── backend/           # Python — бизнес-логика, браузерная автоматизация
│   ├── mail/          # Почтовые провайдеры (плагины)
│   ├── openai_web_auth.py
│   ├── slot_orchestrator.py
│   └── ui_facade.py
├── ui/                # TypeScript — терминальный интерфейс (OpenTUI)
│   └── src/
├── bin/               # CLI entrypoint (npm bin)
├── scripts/           # Setup-скрипты
└── .github/workflows/ # CI/CD
```

## Проверки и тесты

Перед коммитом убедитесь что код проходит проверки:

```bash
# Python — lint + unit tests
ruff check backend tests
python -m unittest discover -s tests -p 'test_*.py'

# TypeScript — typecheck + unit tests
npm --prefix ui run typecheck
npm --prefix ui run test
```

CI автоматически запускает эти проверки на каждый PR.

## Требование по тестам

- Любая новая функциональность или заметное изменение логики должно сопровождаться тестами.
- Минимум: покрывайте тот слой, который можно проверить локально без браузерного e2e.
- Для Python-логики добавляйте `unittest`-тесты в `tests/`.
- Для чистой TypeScript-логики добавляйте тесты в `ui/tests/`.
- Если изменение нельзя адекватно покрыть unit-тестом, это нужно явно отметить в описании PR.
- PR без тестов для новой логики может быть отклонён.

## Conventional Commits

Проект использует [Conventional Commits](https://www.conventionalcommits.org/):

| Префикс | Назначение |
|---------|-----------|
| `feat:` | Новая функциональность |
| `fix:` | Исправление бага |
| `docs:` | Только документация |
| `chore:` | CI, скрипты, зависимости |
| `refactor:` | Рефакторинг без изменения поведения |

Примеры:
```
feat: add IMAP mail provider
fix: handle Oops error page during OAuth
chore: update seleniumbase to 4.33
```

Версия бампается автоматически:
- `feat:` — minor (1.x.0)
- `fix:` / `chore:` — patch (1.0.x)
- `feat!:` / `BREAKING CHANGE` — major (x.0.0)

## Как внести вклад

### Баг-репорты

Откройте issue с:
- Шаги для воспроизведения
- Ожидаемое vs фактическое поведение
- Версия Python, ОС, лог ошибки

### Новая функциональность

Откройте issue с описанием:
- Какую проблему решает
- Предлагаемое решение
- К какому модулю относится

### Pull Requests

1. Один PR — одно логическое изменение.
2. Следуйте Conventional Commits.
3. Добавьте или обновите тесты, если меняется логика приложения.
4. Убедитесь что lint, unit tests и typecheck проходят локально.
5. Обновите документацию если изменение затрагивает пользовательское поведение.

### Новый почтовый провайдер

Наследуйте `MailProvider` из `backend/mail/base.py`:

```python
from backend.mail.base import MailProvider, Mailbox, Inbox

class MyProvider(MailProvider):
    name = "my_provider"

    def generate(self) -> Mailbox:
        ...

    def inbox(self, mailbox: Mailbox) -> Inbox:
        ...
```

Зарегистрируйте в `backend/mail/__init__.py` в фабричных функциях.

## Важно

- **Никогда** не коммитьте `.env`, `accounts/`, `codex/` — они в `.gitignore`.
- Токены и профили хранятся только локально.
