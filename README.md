<div align="center">

# izTeamSlots

**Локальный менеджер ChatGPT Team слотов: админы, инвайты, регистрация, перелогин и Codex-сессии**

[![CI](https://github.com/izzzzzi/izTeamSlots/actions/workflows/ci.yml/badge.svg)](https://github.com/izzzzzi/izTeamSlots/actions/workflows/ci.yml)
[![Release](https://github.com/izzzzzi/izTeamSlots/actions/workflows/release.yml/badge.svg)](https://github.com/izzzzzi/izTeamSlots/actions/workflows/release.yml)
[![npm version](https://img.shields.io/npm/v/izteamslots.svg?style=flat&colorA=18181B&colorB=28CF8D)](https://www.npmjs.com/package/izteamslots)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg?style=flat&colorA=18181B&colorB=28CF8D)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11+-blue?style=flat&colorA=18181B&colorB=3776AB)](https://python.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-5.x-blue?style=flat&colorA=18181B&colorB=3178C6)](https://www.typescriptlang.org/)
[![Bun](https://img.shields.io/badge/Bun-runtime-orange?style=flat&colorA=18181B&colorB=FBF0DF)](https://bun.sh/)

<br />

<img src="img/demo.gif" alt="izTeamSlots demo" width="600" />

</div>

## Quick Start

```bash
npm install -g izteamslots@latest
izteamslots
```

Дальше:
1. Откройте `Настройки` и задайте почтовый провайдер / API-ключ.
2. Добавьте админа через ручной вход в браузере.
3. Запустите создание слотов.

## Что умеет

- Добавление и ручной перелогин админов.
- Создание слотов: `почта -> инвайт -> регистрация -> OAuth`.
- Перелогин одного слота или всех сразу.
- Сохранение `codex-<email>-Team.json`.
- Логи, локальные browser profiles и doctor-проверка.
- Синхронизация workspace с локальными слотами.
- Свитч Codex-аккаунтов: мониторинг usage, авто-ротация auth.json при достижении лимита.

## Ограничения

- Вход админа сейчас поддерживается только в ручном режиме.
- Проект зависит от текущего web UI OpenAI / ChatGPT.
- Браузерная автоматизация может ломаться после изменений на стороне сайта.
- Токены, профили браузера и `codex` хранятся локально.
- Основные платформы: macOS и Windows.

## Где лежат данные

При глобальной установке данные сохраняются в `~/.izteamslots`.

- `accounts/` — аккаунты и browser profiles
- `codex/` — сохранённые codex-файлы
- `logs/` — app/job logs
- `.env` — локальные настройки

Примеры:
- Windows: `C:\Users\<USER>\.izteamslots`
- macOS / Linux: `~/.izteamslots`

Если вы обновляете старую версию, `codex`-файлы могут временно лежать ещё и внутри директории пакета. В актуальной версии основным путём считается именно `~/.izteamslots`.

## Настройка

Настройки можно задать через меню `Настройки` внутри приложения или вручную через `~/.izteamslots/.env`.

```bash
# Linux / macOS
mkdir -p ~/.izteamslots
echo "BOOMLIFY_API_KEY=your_api_key" > ~/.izteamslots/.env

# Windows (PowerShell)
mkdir "$env:USERPROFILE\.izteamslots" -Force
echo "BOOMLIFY_API_KEY=your_api_key" > "$env:USERPROFILE\.izteamslots\.env"
```

| Переменная | По умолчанию | Описание |
|-----------|:------------:|----------|
| `BOOMLIFY_API_KEY` | — | API-ключ Boomlify |
| `BOOMLIFY_DOMAIN` | авто | Домен временных почт |
| `BOOMLIFY_TIME` | `permanent` | Время жизни ящика |
| `SLOT_MAIL_PROVIDER` | `boomlify` | Провайдер почты для слотов |
| `MAIL_PROVIDER` | `trickads` | Провайдер почты для админов |
| `CODEX_SWITCHER_ENABLED` | `false` | Включить автосвитч Codex-аккаунтов |
| `CODEX_SWITCHER_INTERVAL_MINUTES` | `15` | Интервал фоновой проверки usage (минуты) |

## Свитч Codex-аккаунтов

Встроенный механизм ротации Codex-аккаунтов. Все codex-файлы из пула (`<DATA_ROOT>/codex`) отображаются в разделе **Свитч аккаунтов** главного меню.

Что доступно:
- **Таблица аккаунтов** — active-статус, primary usage %, reset time, состояние токена.
- **Ручное обновление** — запросить usage по всем аккаунтам.
- **Ручное переключение** — выбрать аккаунт и записать его в `auth.json`.
- **Первый готовый** — автоматически выбрать первый аккаунт без near-limit.
- **Автосвитч** — фоновый шедулер проверяет usage и переключает `auth.json`, если `primary_used_percent >= 90%`. Включается через настройку `CODEX_SWITCHER_ENABLED`.
- **Авто-рефреш токенов** — если access token истекает, обновляется через OAuth.

Путь к `auth.json` определяется через `CODEX_HOME` или `~/.codex/auth.json`.

## Почтовые провайдеры

- В проект уже встроены `boomlify`, `trickads` и `imap`.
- Можно добавлять собственные почтовые провайдеры.
- Для этого нужно реализовать `MailProvider` и зарегистрировать его в backend.

Подробности: [docs/providers.md](./docs/providers.md)

## Документация

- [docs/providers.md](./docs/providers.md) — встроенные и кастомные почтовые провайдеры
- [docs/architecture.md](./docs/architecture.md) — структура проекта, архитектура и пайплайн слотов
- [docs/troubleshooting.md](./docs/troubleshooting.md) — частые проблемы и способы диагностики
- [CONTRIBUTING.md](./CONTRIBUTING.md) — вклад в проект, проверки и тесты
