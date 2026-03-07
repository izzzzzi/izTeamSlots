# Troubleshooting

## Где смотреть логи

- `~/.izteamslots/logs/app.log`
- `~/.izteamslots/logs/jobs/*.log`

## Частые проблемы

### `EBUSY` при `npm install -g` на Windows

Обычно папка пакета занята процессом `node`, `bun`, `python` или открыта в проводнике / IDE.

Что сделать:
- закрыть `izteamslots`
- завершить `node.exe`, `bun.exe`, `python.exe`
- повторить `npm uninstall -g izteamslots` и `npm install -g izteamslots@latest`

### Backend offline в TUI

Проверьте:
- установлен ли Python 3.11+
- установились ли Python-зависимости
- не сломан ли `~/.izteamslots/.env`
- что `python -m backend` вообще стартует

### Не найден `codex`

При глобальной установке основной путь:

- Windows: `C:\Users\<USER>\.izteamslots\codex`
- macOS / Linux: `~/.izteamslots/codex`

### Web-flow перестал работать

Проект зависит от текущего UI OpenAI / ChatGPT. После изменений на стороне сайта могут ломаться:

- регистрация по invite
- OAuth flow
- выбор workspace
- подтверждение web-session

В этом случае:
- проверьте `logs/jobs/*.log`
- проверьте, на каком URL / экране остановился браузер
- сравните ожидаемый и фактический web-flow

### Проблемы с browser profile

Если профиль заблокирован:
- закройте все окна Chrome
- завершите зависшие процессы браузера
- повторите запуск

На Windows это особенно чувствительно к lock-файлам и stale-процессам.

## Полезные команды

```bash
ruff check backend tests
python -m unittest discover -s tests -p 'test_*.py'
npm --prefix ui run test
npm --prefix ui run typecheck
```
