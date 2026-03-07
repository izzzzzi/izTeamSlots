import test from "node:test"
import assert from "node:assert/strict"

import { getDashboard, getMenuOptions, getTable } from "../src/menus/mainMenus"
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
