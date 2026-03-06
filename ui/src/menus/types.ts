export type MenuName =
  | "main"
  | "admins"
  | "slots"
  | "settings"
  | "pick_admin"
  | "pick_worker"
  | "confirm"

export interface MenuOption {
  id: string
  label: string
  hint?: string
  description?: string
  badge?: string
  destructive?: boolean
  disabled?: boolean
}

export interface AdminRow {
  email: string
  has_access_token: boolean
  has_browser_profile: boolean
  workspace_id: string | null
  workspace_count: number
  created_at: string | null
  last_login: string | null
  status_label: string
}

export interface WorkerRow {
  email: string
  status: string
  has_access_token: boolean
  has_browser_profile: boolean
  workspace_id: string | null
  admin_email: string | null
  has_openai_password: boolean
  created_at: string | null
  status_label: string
}

export interface SettingItem {
  key: string
  label: string
  masked: string
}

export interface AppState {
  admins: AdminRow[]
  workers: WorkerRow[]
  settings?: SettingItem[]
}

export interface MenuContext {
  parent?: MenuName
  action?: string
  title?: string
  admin_email?: string
  target?: string
  confirm_action?: string
}

export interface DashboardData {
  admins_total: number
  admins_ready: number
  admins_with_token: number
  admins_with_profile: number
  workers_total: number
  workers_ready: number
  workers_registered: number
  workers_invited: number
  workers_created: number
  workers_with_password: number
}
