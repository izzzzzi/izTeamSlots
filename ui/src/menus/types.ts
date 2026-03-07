export type MenuName =
  | "main"
  | "admins"
  | "slots"
  | "codex_switcher"
  | "settings"
  | "pick_admin"
  | "pick_worker"
  | "pick_codex"
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

export interface CodexAccountRow {
  email: string
  is_active: boolean
  primary_used_percent: number | null
  primary_resets_at: string | null
  secondary_used_percent: number | null
  secondary_resets_at: string | null
  usage_status: string
  token_status: string
  last_checked_at: string | null
  last_error: string | null
  near_limit: boolean
}

export interface CodexSwitcherStatus {
  enabled: boolean
  interval_minutes: number
  last_run_at: string | null
  last_switch_at: string | null
  active_email: string | null
  last_error: string | null
}

export interface AppState {
  admins: AdminRow[]
  workers: WorkerRow[]
  settings?: SettingItem[]
  codex_accounts?: CodexAccountRow[]
  codex_switcher_status?: CodexSwitcherStatus
}

export interface MenuContext {
  parent?: MenuName
  action?: string
  title?: string
  admin_email?: string
  target?: string
  confirm_action?: string
  sync_preview?: {
    admin_email: string
    extra_members: string[]
    extra_invites: string[]
    skipped: string[]
  }
  codex_email?: string
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
