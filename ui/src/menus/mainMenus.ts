import type { AppState, CodexAccountRow, DashboardData, MenuContext, MenuName, MenuOption, WorkerRow } from "./types"

export function getMenuOptions(menuName: MenuName, state: AppState): MenuOption[] {
  if (menuName === "main") {
    return [
      { id: "menu_admins", label: "Админы", hint: "Добавить, войти, открыть, удалить", description: "Перейти к действиям с администраторами." },
      { id: "menu_slots", label: "Слоты", hint: "Создать, перелогинить, открыть, удалить", description: "Перейти к действиям со слотами." },
      { id: "menu_codex_switcher", label: "Свитч аккаунтов", hint: "Usage, токены, auth.json", description: "Проверить usage, активный auth.json и переключить Codex-аккаунт." },
      { id: "menu_settings", label: "Настройки", hint: "Почта, ключи, провайдер", description: "Изменить рабочие настройки." },
      { id: "menu_exit", label: "Выход", hint: "Закрыть TUI", description: "Завершить работу приложения." },
    ]
  }

  if (menuName === "admins") {
    return [
      { id: "adm_add", label: "Добавить админа", hint: "Новый админ", description: "Добавить админа и выбрать способ входа." },
      { id: "adm_relogin", label: "Перелогинить", hint: "Обновить доступ", description: "Перелогинить выбранного админа." },
      { id: "adm_sync_ws", label: "Синхронизировать WS", hint: "Удалить лишних", description: "Сверить workspace с локальными слотами и удалить лишние записи." },
      { id: "adm_open", label: "Открыть браузер", hint: "Открыть профиль", description: "Открыть браузерный профиль админа." },
      { id: "adm_delete", label: "Удалить", hint: "Удалить данные", description: "Удалить админа и его локальные файлы.", destructive: true },
    ]
  }

  if (menuName === "slots") {
    return [
      { id: "slots_create", label: "Создать слоты", hint: "Новые слоты", description: "Запустить создание слотов под выбранным админом." },
      { id: "slots_relogin", label: "Перелогинить", hint: "Обновить доступ", description: "Перелогинить один слот или все сразу." },
      { id: "slots_open", label: "Открыть браузер", hint: "Открыть профиль", description: "Открыть браузерный профиль слота." },
      { id: "slots_delete", label: "Удалить слот", hint: "Удалить данные", description: "Удалить слот и его локальные файлы.", destructive: true },
    ]
  }

  if (menuName === "codex_switcher") {
    const enabled = state.codex_switcher_status?.enabled ? "вкл" : "выкл"
    return [
      { id: "codex_refresh", label: "Обновить usage", hint: "Проверить сейчас", description: "Обновить usage и статус токенов по всем codex-аккаунтам." },
      { id: "codex_switch", label: "Переключить аккаунт", hint: "Выбрать вручную", description: "Выбрать аккаунт и записать его в активный Codex auth.json." },
      { id: "codex_pick_first", label: "Первый готовый", hint: "Автовыбор", description: "Выбрать первый аккаунт без near-limit и сделать его активным." },
      { id: "codex_settings", label: "Настройки автосвитча", hint: enabled, description: "Открыть настройки тумблера и интервала шедулера." },
    ]
  }

  if (menuName === "pick_admin") {
    return state.admins.map((a) => ({
      id: `pick_admin:${a.email}`,
      label: a.email,
      hint: a.has_access_token ? "Готов" : "Нужно войти",
      description: `Выбрать админа ${a.email}.`,
    }))
  }

  if (menuName === "pick_worker") {
    return state.workers.map((w) => ({
      id: `pick_worker:${w.email}`,
      label: w.email,
      hint: humanizeWorkerStatus(w.status),
      description: `Выбрать слот ${w.email}.`,
    }))
  }

  if (menuName === "pick_codex") {
    return (state.codex_accounts ?? []).map((account) => ({
      id: `pick_codex:${account.email}`,
      label: account.email,
      hint: humanizeCodexHint(account),
      description: `Сделать активным Codex-аккаунт ${account.email}.`,
    }))
  }

  if (menuName === "settings") {
    return [
      ...(state.settings ?? []).map((s: { key: string; label: string; masked: string }) => ({
        id: `setting:${s.key}`,
        label: s.label,
        hint: s.masked || "не задан",
        description: `Изменить значение: ${s.label}.`,
      })),
    ]
  }

  if (menuName === "confirm") {
    return [
      { id: "confirm_yes", label: "Да, удалить", hint: "Подтвердить", description: "Подтвердить удаление.", destructive: true },
      { id: "confirm_no", label: "Отмена", hint: "Назад", description: "Отменить действие и вернуться." },
    ]
  }

  return []
}

export function getDashboard(state: AppState): DashboardData {
  const admins_total = state.admins.length
  const admins_ready = state.admins.filter((a) => a.has_access_token && a.has_browser_profile).length
  const admins_with_token = state.admins.filter((a) => a.has_access_token).length
  const admins_with_profile = state.admins.filter((a) => a.has_browser_profile).length
  const workers_total = state.workers.length
  const workers_ready = state.workers.filter((w) => w.has_access_token && w.has_browser_profile).length
  const workers_registered = state.workers.filter((w) => w.status === "registered").length
  const workers_invited = state.workers.filter((w) => w.status === "invited").length
  const workers_created = state.workers.filter((w) => w.status === "created").length
  const workers_with_password = state.workers.filter((w) => w.has_openai_password).length

  return {
    admins_total,
    admins_ready,
    admins_with_token,
    admins_with_profile,
    workers_total,
    workers_ready,
    workers_registered,
    workers_invited,
    workers_created,
    workers_with_password,
  }
}

function humanizeWorkerStatus(status: string): string {
  if (status === "registered") return "Готов"
  if (status === "invited") return "Приглашён"
  if (status === "created") return "Создан"
  return status
}

export function getTable(menuName: MenuName, state: AppState, ctx: MenuContext): { headers: string[]; rows: string[][] } {
  if (menuName === "admins" || menuName === "pick_admin") {
    return {
      headers: ["Email", "Статус", "Профиль", "WS", "Последний вход"],
      rows: state.admins.map((a) => [
        a.email,
        a.status_label,
        a.has_browser_profile ? "Есть" : "Нет",
        String(a.workspace_count),
        a.last_login ?? "-",
      ]),
    }
  }

  if (menuName === "slots" || menuName === "pick_worker") {
    let workers: WorkerRow[] = state.workers
    if (ctx.admin_email) {
      workers = workers.filter((w) => w.admin_email === ctx.admin_email)
    }
    return {
      headers: ["Email", "Состояние", "Доступ", "Админ", "Пароль"],
      rows: workers.map((w) => [
        w.email,
        w.status_label,
        w.has_browser_profile ? "Профиль" : w.has_access_token ? "Токен" : "Нужно войти",
        w.admin_email ?? "-",
        w.has_openai_password ? "Есть" : "Нет",
      ]),
    }
  }

  if (menuName === "codex_switcher" || menuName === "pick_codex") {
    return {
      headers: ["Email", "Активен", "Primary", "Reset", "Token", "Usage"],
      rows: (state.codex_accounts ?? []).map((account) => [
        account.email,
        account.is_active ? "Да" : "Нет",
        formatPercent(account.primary_used_percent),
        account.primary_resets_at ? formatShortDate(account.primary_resets_at) : "-",
        humanizeTokenStatus(account.token_status),
        humanizeUsageStatus(account.usage_status, account.near_limit),
      ]),
    }
  }

  if (menuName === "confirm") {
    return {
      headers: ["Действие", "Объект"],
      rows: [[ctx.confirm_action ?? "", ctx.target ?? ""]],
    }
  }

  return {
    headers: ["Info"],
    rows: [["izTeamSlots"]],
  }
}

export function getHint(menuName: MenuName, _ctx: MenuContext): string {
  if (menuName === "main") return "↑↓ или 1-5: выбор  Enter: открыть  r: обновить  q: выход"
  if (menuName === "confirm") return "Enter: подтвердить  Esc: отмена"
  return "↑↓ или 1-9: выбор  Enter: действие  Esc: назад  r: обновить  y: копировать лог"
}

export function parentMenu(menuName: MenuName, ctx: MenuContext): MenuName {
  if (ctx.parent) return ctx.parent
  const map: Record<MenuName, MenuName> = {
    main: "main",
    admins: "main",
    slots: "main",
    codex_switcher: "main",
    settings: "main",
    pick_admin: "admins",
    pick_worker: "slots",
    pick_codex: "codex_switcher",
    confirm: "main",
  }
  return map[menuName]
}

function humanizeCodexHint(account: CodexAccountRow): string {
  if (account.is_active) return "Активен"
  if (account.near_limit) return "Near limit"
  if (account.token_status === "invalid") return "Токен сломан"
  if (account.usage_status === "error") return "Ошибка usage"
  if (account.usage_status === "ok") return "Готов"
  return "Не проверен"
}

function humanizeTokenStatus(status: string): string {
  if (status === "fresh") return "Свежий"
  if (status === "refreshed") return "Обновлён"
  if (status === "expiring") return "Истекает"
  if (status === "invalid") return "Ошибка"
  return status || "-"
}

function humanizeUsageStatus(status: string, nearLimit: boolean): string {
  if (status === "ok" && nearLimit) return "Near limit"
  if (status === "ok") return "OK"
  if (status === "error") return "Ошибка"
  if (status === "idle") return "Не проверен"
  return status || "-"
}

function formatPercent(value: number | null): string {
  if (typeof value !== "number") return "-"
  return `${Math.round(value)}%`
}

function formatShortDate(value: string): string {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date)
}
