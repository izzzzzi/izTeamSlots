import type { AppState, DashboardData, MenuContext, MenuName, MenuOption, WorkerRow } from "./types"

export function getMenuOptions(menuName: MenuName, state: AppState): MenuOption[] {
  if (menuName === "main") {
    return [
      { id: "menu_admins", label: "Админы", hint: "Доступы, токены, браузерные профили" },
      { id: "menu_slots", label: "Слоты", hint: "Создание, перелогин и обслуживание" },
      { id: "menu_mail", label: "Почта", hint: "Ящики и входящие письма" },
      { id: "menu_exit", label: "Выход", hint: "Закрыть приложение" },
    ]
  }

  if (menuName === "admins") {
    return [
      { id: "adm_add", label: "Добавить админа", hint: "Создать профиль и выбрать режим входа" },
      { id: "adm_relogin", label: "Перелогинить", hint: "Выбрать админа и режим: авто или вручную" },
      { id: "adm_open", label: "Открыть браузер", hint: "Запустить профиль для ручной проверки" },
      { id: "adm_delete", label: "Удалить", hint: "Удалить админа и связанные данные", destructive: true },
    ]
  }

  if (menuName === "slots") {
    return [
      { id: "slots_create", label: "Создать слоты", hint: "Запустить пайплайн регистрации через админа" },
      { id: "slots_relogin", label: "Перелогинить", hint: "Выбрать: один слот или все сразу" },
      { id: "slots_open", label: "Открыть браузер", hint: "Проверить конкретный слот вручную" },
      { id: "slots_delete", label: "Удалить слот", hint: "Очистить аккаунт и локальные данные", destructive: true },
    ]
  }

  if (menuName === "mail") {
    return [
      ...state.accounts.map((a, i) => ({
        id: `mail_pick:${i}`,
        label: `${a.email}`,
        hint: a.kind === "admin" ? "Почта администратора" : "Почта слота",
      })),
    ]
  }

  if (menuName === "pick_admin") {
    return state.admins.map((a) => ({
      id: `pick_admin:${a.email}`,
      label: a.email,
      hint: a.has_access_token ? "Токен готов" : "Нужен повторный вход",
    }))
  }

  if (menuName === "pick_worker") {
    return state.workers.map((w) => ({
      id: `pick_worker:${w.email}`,
      label: w.email,
      hint: `Статус: ${humanizeWorkerStatus(w.status)}`,
    }))
  }

  if (menuName === "pick_account") {
    return state.accounts.map((a, i) => ({
      id: `pick_account:${i}`,
      label: a.email,
      hint: a.kind === "admin" ? "Админский ящик" : "Почта слота",
    }))
  }

  if (menuName === "confirm") {
    return [
      { id: "confirm_yes", label: "Да, удалить", hint: "Подтвердить необратимое действие", destructive: true },
      { id: "confirm_no", label: "Отмена", hint: "Вернуться без изменений" },
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

export function getScreenTitle(menuName: MenuName, ctx: MenuContext): string {
  if (menuName === "main") return "Обзор системы"
  if (menuName === "admins") return "Администраторы"
  if (menuName === "slots") return "Слоты"
  if (menuName === "mail") return "Почтовые ящики"
  if (menuName === "pick_admin") return ctx.title ?? "Выбор администратора"
  if (menuName === "pick_worker") return ctx.title ?? "Выбор слота"
  if (menuName === "pick_account") return ctx.title ?? "Выбор аккаунта"
  if (menuName === "confirm") return ctx.title ?? "Подтверждение"
  return "izTeamSlots"
}

export function getScreenDescription(menuName: MenuName, state: AppState, ctx: MenuContext): string {
  if (menuName === "main") {
    return "Операционный центр для админов, слотов и временной почты."
  }

  if (menuName === "admins") {
    return state.admins.length === 0
      ? "Добавьте первого администратора, чтобы открыть доступ к созданию слотов."
      : "Управляйте доступами, токенами и ручным открытием браузерных профилей."
  }

  if (menuName === "slots") {
    return state.workers.length === 0
      ? "Пока нет слотов. Запустите создание через выбранного администратора."
      : "Следите за состоянием слотов и быстро восстанавливайте проблемные аккаунты."
  }

  if (menuName === "mail") {
    return state.accounts.length === 0
      ? "Почтовые ящики появятся после создания админов и слотов."
      : "Выберите аккаунт слева, чтобы забрать входящие письма."
  }

  if (menuName === "pick_admin") return ctx.title ?? "Выберите администратора для следующего действия."
  if (menuName === "pick_worker") return ctx.title ?? "Выберите слот для следующего действия."
  if (menuName === "pick_account") return ctx.title ?? "Выберите аккаунт."
  if (menuName === "confirm") return "Проверьте объект удаления и подтвердите действие."

  return "Операционный экран."
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

  if (menuName === "mail" || menuName === "pick_account") {
    return {
      headers: ["Тип", "Email"],
      rows: state.accounts.map((a) => [a.kind, a.email]),
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
  if (menuName === "main") return "↑↓ или 1-4: выбор  Enter: открыть  r: обновить  q: выход"
  if (menuName === "confirm") return "Enter: подтвердить  Esc: отмена"
  return "↑↓ или 1-9: выбор  Enter: действие  Esc: назад  r: обновить  y: копировать лог"
}

export function parentMenu(menuName: MenuName, ctx: MenuContext): MenuName {
  if (ctx.parent) return ctx.parent
  const map: Record<MenuName, MenuName> = {
    main: "main",
    admins: "main",
    slots: "main",
    mail: "main",
    pick_admin: "admins",
    pick_worker: "slots",
    pick_account: "mail",
    confirm: "main",
  }
  return map[menuName]
}
