import test from "node:test"
import assert from "node:assert/strict"

import { getDashboard, getHint, getMenuOptions, getTable, parentMenu } from "../src/menus/mainMenus"
import type { AppState } from "../src/menus/types"

const state: AppState = {
  admins: [
    {
      email: "admin@example.com",
      has_access_token: true,
      has_browser_profile: true,
      workspace_id: "ws-1",
      workspace_count: 2,
      created_at: "2026-03-07T00:00:00Z",
      last_login: "2026-03-07T01:00:00Z",
      status_label: "Готов",
    },
  ],
  workers: [
    {
      email: "slot1@example.com",
      status: "registered",
      has_access_token: true,
      has_browser_profile: true,
      workspace_id: "ws-1",
      admin_email: "admin@example.com",
      has_openai_password: true,
      created_at: "2026-03-07T00:00:00Z",
      status_label: "Готов",
    },
    {
      email: "slot2@example.com",
      status: "invited",
      has_access_token: false,
      has_browser_profile: false,
      workspace_id: "ws-1",
      admin_email: "other@example.com",
      has_openai_password: false,
      created_at: "2026-03-07T00:00:00Z",
      status_label: "Инвайт отправлен",
    },
  ],
  codex_accounts: [
    {
      email: "codex1@example.com",
      is_active: true,
      primary_used_percent: 42,
      primary_resets_at: "2026-03-07T03:00:00Z",
      secondary_used_percent: 12,
      secondary_resets_at: "2026-03-09T03:00:00Z",
      usage_status: "ok",
      token_status: "fresh",
      last_checked_at: "2026-03-07T01:30:00Z",
      last_error: null,
      near_limit: false,
    },
  ],
  codex_switcher_status: {
    enabled: true,
    interval_minutes: 15,
    last_run_at: "2026-03-07T01:30:00Z",
    last_switch_at: "2026-03-07T01:00:00Z",
    active_email: "codex1@example.com",
    last_error: null,
  },
}

test("admin menu exposes workspace sync action", () => {
  const options = getMenuOptions("admins", state)
  const syncOption = options.find((option) => option.id === "adm_sync_ws")

  assert.ok(syncOption)
  assert.equal(syncOption?.label, "Синхронизировать WS")
})

test("dashboard counts ready and invited entities", () => {
  const dashboard = getDashboard(state)

  assert.equal(dashboard.admins_total, 1)
  assert.equal(dashboard.admins_ready, 1)
  assert.equal(dashboard.workers_total, 2)
  assert.equal(dashboard.workers_ready, 1)
  assert.equal(dashboard.workers_invited, 1)
  assert.equal(dashboard.workers_with_password, 1)
})

test("worker table respects admin filter", () => {
  const table = getTable("slots", state, { admin_email: "admin@example.com" })

  assert.deepEqual(table.headers, ["Email", "Состояние", "Доступ", "Админ", "Пароль"])
  assert.equal(table.rows.length, 1)
  assert.equal(table.rows[0][0], "slot1@example.com")
})

test("main menu exposes codex switcher section", () => {
  const options = getMenuOptions("main", state)
  const section = options.find((option) => option.id === "menu_codex_switcher")

  assert.ok(section)
  assert.equal(section?.label, "Свитч аккаунтов")
})

test("codex switcher table renders usage columns", () => {
  const table = getTable("codex_switcher", state, {})

  assert.deepEqual(table.headers, ["Email", "Активен", "Primary", "Reset", "Token", "Usage"])
  assert.equal(table.rows[0][0], "codex1@example.com")
  assert.equal(table.rows[0][1], "Да")
  assert.equal(table.rows[0][2], "42%")
})

test("codex switcher menu has all action options", () => {
  const options = getMenuOptions("codex_switcher", state)
  const ids = options.map((o) => o.id)

  assert.ok(ids.includes("codex_refresh"))
  assert.ok(ids.includes("codex_switch"))
  assert.ok(ids.includes("codex_pick_first"))
  assert.ok(ids.includes("codex_settings"))
})

test("codex switcher menu shows enabled status in settings hint", () => {
  const options = getMenuOptions("codex_switcher", state)
  const settings = options.find((o) => o.id === "codex_settings")

  assert.ok(settings)
  assert.equal(settings?.hint, "вкл")

  const disabledState: AppState = {
    ...state,
    codex_switcher_status: { ...state.codex_switcher_status!, enabled: false },
  }
  const disabledOptions = getMenuOptions("codex_switcher", disabledState)
  const disabledSettings = disabledOptions.find((o) => o.id === "codex_settings")
  assert.equal(disabledSettings?.hint, "выкл")
})

test("pick_codex menu lists codex accounts", () => {
  const options = getMenuOptions("pick_codex", state)

  assert.equal(options.length, 1)
  assert.equal(options[0].id, "pick_codex:codex1@example.com")
  assert.equal(options[0].label, "codex1@example.com")
  assert.equal(options[0].hint, "Активен")
})

test("pick_codex shows correct hints for different account states", () => {
  const multiState: AppState = {
    ...state,
    codex_accounts: [
      { ...state.codex_accounts![0], is_active: false, near_limit: true },
      {
        email: "codex2@example.com",
        is_active: false,
        primary_used_percent: 10,
        primary_resets_at: null,
        secondary_used_percent: null,
        secondary_resets_at: null,
        usage_status: "ok",
        token_status: "fresh",
        last_checked_at: null,
        last_error: null,
        near_limit: false,
      },
      {
        email: "codex3@example.com",
        is_active: false,
        primary_used_percent: null,
        primary_resets_at: null,
        secondary_used_percent: null,
        secondary_resets_at: null,
        usage_status: "idle",
        token_status: "invalid",
        last_checked_at: null,
        last_error: "token broken",
        near_limit: false,
      },
    ],
  }
  const options = getMenuOptions("pick_codex", multiState)

  assert.equal(options[0].hint, "Near limit")
  assert.equal(options[1].hint, "Готов")
  assert.equal(options[2].hint, "Токен сломан")
})

test("codex switcher table renders near-limit and error states", () => {
  const extState: AppState = {
    ...state,
    codex_accounts: [
      {
        email: "limited@example.com",
        is_active: true,
        primary_used_percent: 95,
        primary_resets_at: "2026-03-07T05:00:00Z",
        secondary_used_percent: null,
        secondary_resets_at: null,
        usage_status: "ok",
        token_status: "expiring",
        last_checked_at: null,
        last_error: null,
        near_limit: true,
      },
      {
        email: "errored@example.com",
        is_active: false,
        primary_used_percent: null,
        primary_resets_at: null,
        secondary_used_percent: null,
        secondary_resets_at: null,
        usage_status: "error",
        token_status: "invalid",
        last_checked_at: null,
        last_error: "fail",
        near_limit: false,
      },
    ],
  }
  const table = getTable("codex_switcher", extState, {})

  assert.equal(table.rows[0][2], "95%")
  assert.equal(table.rows[0][4], "Истекает")
  assert.equal(table.rows[0][5], "Near limit")
  assert.equal(table.rows[1][2], "-")
  assert.equal(table.rows[1][4], "Ошибка")
  assert.equal(table.rows[1][5], "Ошибка")
})

test("parentMenu returns correct parents for codex menus", () => {
  assert.equal(parentMenu("codex_switcher", {}), "main")
  assert.equal(parentMenu("pick_codex", {}), "codex_switcher")
})
