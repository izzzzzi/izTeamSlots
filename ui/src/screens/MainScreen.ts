import { StyledText, bg, bold, createCliRenderer, fg, t } from "@opentui/core"
import * as OpenTUI from "@opentui/core"
import { execFileSync } from "node:child_process"

import { formatDashboard, formatMenu, formatTable, joinStyledLines } from "../menus/format"
import { getDashboard, getHint, getMenuOptions, getTable, parentMenu } from "../menus/mainMenus"
import type { AppState, MenuContext, MenuName, MenuOption } from "../menus/types"
import { StdioRpcClient } from "../transport/stdioClient"

const EMPTY_STATE: AppState = {
  admins: [],
  workers: [],
}

type RpcJobResult = { job_id: string }

type PromptOption = {
  label: string
  value: string
  hint?: string
  destructive?: boolean
}

type PromptState = {
  active: boolean
  mode: "input" | "select"
  question: string
  hidden: boolean
  value: string
  options: PromptOption[]
  selectedIndex: number
  resolve: ((value: string | null) => void) | null
}

type LayoutMode = "full" | "compact" | "fallback"

type LayoutMetrics = {
  mode: LayoutMode
  width: number
  height: number
  summaryHeight: number
  primaryHeight: number
  detailHeight: number
  menuHeight: number
  showDetail: boolean
  summaryWidth: number
  primaryWidth: number
  detailWidth: number
  menuWidth: number
  statusWidth: number
  menuMaxVisible: number
  detailLogLimit: number
  showMenuIndicators: boolean
}

type AnyRenderable = { content?: unknown }

type ScrollableTextRenderable = AnyRenderable & {
  scrollY?: number
  maxScrollY?: number
  selectable?: boolean
  getSelectedText?: () => string
}

function setRenderableText(node: AnyRenderable, value: unknown) {
  node.content = value
}

function copyToSystemClipboard(text: string): boolean {
  const value = text.trim()
  if (!value) return false

  try {
    const platform = process.platform
    if (platform === "darwin") {
      execFileSync("pbcopy", [], { input: value })
    } else if (platform === "win32") {
      execFileSync("powershell", ["-NoProfile", "-Command",
        "Set-Clipboard ([Console]::In.ReadToEnd().TrimEnd())"], { input: value })
    } else {
      execFileSync("xclip", ["-selection", "clipboard"], { input: value })
    }
    return true
  } catch {
    return false
  }
}

function formatShortDate(value: string | null | undefined): string {
  if (!value) return "не было"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date)
}

function timeStamp(): string {
  return new Intl.DateTimeFormat("ru-RU", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date())
}

function boolLabel(value: boolean): string {
  return value ? "есть" : "нет"
}

function statusLabel(value: string | null | undefined): string {
  if (!value) return "неизвестно"
  if (value === "created") return "создан"
  if (value === "invited") return "приглашён"
  if (value === "registered") return "зарегистрирован"
  if (value === "logged_in") return "в работе"
  return value
}

function clampNumber(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value))
}

function truncateText(value: string, width: number): string {
  if (width <= 0) return ""
  if (width === 1) return value.slice(0, 1)
  if (value.length <= width) return value
  return `${value.slice(0, width - 1)}…`
}

function hasFlag(row: unknown, key: string): boolean {
  if (!row || typeof row !== "object") return false
  return Boolean((row as Record<string, unknown>)[key])
}

function getMenuOptionDescription(option: MenuOption | undefined): string {
  const extra = option as MenuOption & { description?: string }
  if (extra?.description) return extra.description
  const optionId = option?.id ?? ""

  if (optionId === "menu_admins") return "Открыть раздел админов."
  if (optionId === "menu_slots") return "Открыть раздел слотов."
  if (optionId === "menu_settings") return "Открыть настройки."
  if (optionId === "menu_exit") return "Закрыть приложение."

  if (optionId === "adm_add") return "Добавить нового админа."
  if (optionId === "adm_relogin") return "Перелогинить админа."
  if (optionId === "adm_open") return "Открыть профиль админа."
  if (optionId === "adm_delete") return "Удалить админа."

  if (optionId === "slots_create") return "Создать новые слоты."
  if (optionId === "slots_relogin") return "Перелогинить слот или все слоты."
  if (optionId === "slots_open") return "Открыть профиль слота."
  if (optionId === "slots_delete") return "Удалить слот."

  if (optionId.startsWith("pick_admin:"))
    return "Выбрать этого админа."
  if (optionId.startsWith("pick_worker:"))
    return "Выбрать этот слот."
  if (optionId.startsWith("setting:"))
    return "Изменить значение настройки."
  if (optionId === "confirm_yes")
    return "Подтвердить удаление."
  if (optionId === "confirm_no")
    return "Отменить и вернуться."

  return "Нажмите Enter для выполнения."
}

export class MainScreen {
  private readonly rpc = new StdioRpcClient()

  private state: AppState = EMPTY_STATE
  private backendOnline = false
  private connectionError = ""
  private menuName: MenuName = "main"
  private menuCtx: MenuContext = {}
  private menuOptions: MenuOption[] = []
  private selectedIndex = 0
  private busy = false
  private busyTitle = ""

  private logs: string[] = []
  private _lastCtrlC = 0

  private prompt: PromptState = {
    active: false,
    mode: "input",
    question: "",
    hidden: false,
    value: "",
    options: [],
    selectedIndex: 0,
    resolve: null,
  }

  private renderer!: Awaited<ReturnType<typeof createCliRenderer>>
  private summaryBox!: OpenTUI.BoxRenderable
  private primaryBox!: OpenTUI.BoxRenderable
  private detailBox!: OpenTUI.BoxRenderable
  private menuBox!: OpenTUI.BoxRenderable
  private statusBox!: OpenTUI.BoxRenderable

  private summaryText!: AnyRenderable
  private primaryText!: AnyRenderable
  private detailText!: ScrollableTextRenderable
  private menuText!: AnyRenderable
  private statusText!: AnyRenderable
  private layout: LayoutMetrics = {
    mode: "full",
    width: 120,
    height: 32,
    summaryHeight: 7,
    primaryHeight: 12,
    detailHeight: 9,
    menuHeight: 6,
    showDetail: true,
    summaryWidth: 114,
    primaryWidth: 114,
    detailWidth: 114,
    menuWidth: 114,
    statusWidth: 118,
    menuMaxVisible: 4,
    detailLogLimit: 8,
    showMenuIndicators: true,
  }
  private needsDetailClamp = false
  private needsDetailScrollEnd = false
  private detailAdjustmentScheduled = false

  async start() {
    this.renderer = await createCliRenderer({ exitOnCtrlC: false })
    this.buildUI()
    this.renderer.on("resize", () => {
      this.rebuildMenuOptions()
      this.clampSelection()
      this.needsDetailClamp = true
      this.render()
    })

    this.rpc.onEvent((evt) => {
      this.backendOnline = true
      if (evt.event === "job.started") {
        this.busy = true
        this.busyTitle = String(evt.data.title ?? "")
        this.pushLog(`Запуск: ${this.busyTitle || "операция"}`)
        if (evt.data.log_path) {
          this.pushLog(`Лог-файл: ${String(evt.data.log_path)}`)
        }
      }
      if (evt.event === "job.log") {
        this.pushLog(String(evt.data.message ?? ""))
      }
      if (evt.event === "job.progress") {
        const current = Number(evt.data.current ?? 0)
        const total = Number(evt.data.total ?? 0)
        const message = String(evt.data.message ?? "")
        this.busyTitle = total > 0 ? `${current}/${total} ${message}`.trim() : message || "Выполняется"
      }
      if (evt.event === "job.done") {
        this.busy = false
        this.busyTitle = ""
        this.pushLog("Операция завершена")
        void this.refreshState()
      }
      if (evt.event === "job.error") {
        this.busy = false
        this.busyTitle = ""
        this.pushLog(`Ошибка: ${String(evt.data.error ?? "unknown")}`)
        if (evt.data.log_path) {
          this.pushLog(`Подробности в файле: ${String(evt.data.log_path)}`)
        }
        void this.refreshState()
      }
      this.render()
    })

    this.renderer.keyInput.on("keypress", (key: any) => {
      void this.onKey(key).catch((error) => {
        this.pushLog(`Ошибка: ${String(error)}`)
        this.render()
      })
    })

    this.renderer.keyInput.on("paste", (event: any) => {
      this.onPaste(event)
    })

    this.rpc.onErrorOutput((line) => {
      this.pushLog(`[backend] ${line}`)
      this.render()
    })

    this.rpc.start()
    await this.refreshState(false)
    if (this.backendOnline) {
      this.pushLog("Интерфейс готов к работе")
    }
    this.render()
  }

  private buildUI() {
    const root = new OpenTUI.BoxRenderable(this.renderer, {
      id: "root",
      width: "100%",
      height: "100%",
      flexDirection: "column",
      justifyContent: "flex-start",
      padding: 0,
      backgroundColor: "#020a2b",
    })

    this.summaryBox = new OpenTUI.BoxRenderable(this.renderer, {
      id: "summary_box",
      title: "izTeamSlots",
      border: true,
      borderColor: "#334155",
      height: 7,
      width: "100%",
      backgroundColor: "#020a2b",
      paddingLeft: 1,
      paddingRight: 1,
      flexShrink: 0,
    })

    this.primaryBox = new OpenTUI.BoxRenderable(this.renderer, {
      id: "primary_box",
      title: "Быстрый старт",
      border: true,
      borderColor: "#334155",
      height: 12,
      width: "100%",
      backgroundColor: "#08111f",
      paddingLeft: 1,
      paddingRight: 1,
    })

    this.detailBox = new OpenTUI.BoxRenderable(this.renderer, {
      id: "detail_box",
      title: "События и контекст",
      border: true,
      borderColor: "#334155",
      height: 9,
      width: "100%",
      backgroundColor: "#020617",
      paddingLeft: 1,
      paddingRight: 1,
    })

    this.menuBox = new OpenTUI.BoxRenderable(this.renderer, {
      id: "menu_box",
      title: "Действия",
      border: true,
      borderColor: "#334155",
      height: 6,
      width: "100%",
      backgroundColor: "#08111f",
      paddingLeft: 1,
      paddingRight: 1,
      flexShrink: 0,
    })

    this.statusBox = new OpenTUI.BoxRenderable(this.renderer, {
      id: "status_box",
      border: false,
      backgroundColor: "#1f2937",
      height: 1,
      width: "100%",
      padding: 0,
    })

    this.summaryText = new OpenTUI.TextRenderable(this.renderer, {
      id: "summary_text",
      content: "",
    })
    this.primaryText = new OpenTUI.TextRenderable(this.renderer, {
      id: "primary_text",
      content: "",
    })
    this.detailText = new OpenTUI.TextRenderable(this.renderer, {
      id: "detail_text",
      content: "",
      selectable: true,
      selectionBg: "#1d4ed8",
      selectionFg: "#eff6ff",
    }) as ScrollableTextRenderable
    this.menuText = new OpenTUI.TextRenderable(this.renderer, {
      id: "menu_text",
      content: "",
    })
    this.statusText = new OpenTUI.TextRenderable(this.renderer, {
      id: "status_text",
      content: "",
    })

    this.summaryBox.add(this.summaryText)
    this.primaryBox.add(this.primaryText)
    this.detailBox.add(this.detailText)
    this.menuBox.add(this.menuText)
    this.statusBox.add(this.statusText)

    root.add(this.summaryBox)
    root.add(this.primaryBox)
    root.add(this.detailBox)
    root.add(this.menuBox)
    root.add(this.statusBox)

    this.renderer.root.add(root)
  }

  private async refreshState(logErrors = true) {
    try {
      const state = (await this.rpc.request<AppState>("state.get")) ?? EMPTY_STATE
      this.state = state
      this.backendOnline = true
      this.connectionError = ""
    } catch (error) {
      this.state = EMPTY_STATE
      this.backendOnline = false
      this.connectionError = String(error)
      if (logErrors) {
        this.pushLog(`Не удалось подключиться к backend: ${this.getShortConnectionError()}`)
      }
    }

    this.rebuildMenuOptions()
    this.render()
  }

  private async loadSettings() {
    try {
      const result = await this.rpc.request<{ items: Array<{ key: string; label: string; masked: string }> }>("settings.get")
      this.state = { ...this.state, settings: result.items }
    } catch (error) {
      this.pushLog(`Ошибка загрузки настроек: ${String(error)}`)
    }
    this.rebuildMenuOptions()
    this.render()
  }

  private rebuildMenuOptions() {
    this.menuOptions = getMenuOptions(this.menuName, this.state)
    this.clampSelection()
  }

  private getTerminalWidth(): number {
    return Math.max(20, this.renderer.terminalWidth || process.stdout.columns || 120)
  }

  private getTerminalHeight(): number {
    return Math.max(8, this.renderer.terminalHeight || process.stdout.rows || 32)
  }

  private computeLayoutMetrics(visibleMenuCount: number): LayoutMetrics {
    const width = this.getTerminalWidth()
    const height = this.getTerminalHeight()
    const mode: LayoutMode = width >= 120 && height >= 32
      ? "full"
      : width >= 80 && height >= 22
        ? "compact"
        : "fallback"

    if (mode === "fallback") {
      const summaryHeight = height >= 16 ? 5 : 4
      const statusHeight = 1
      const bodyHeight = Math.max(4, height - summaryHeight - statusHeight)
      const primaryFloor = bodyHeight >= 8 ? 4 : 2
      const maxMenuHeight = Math.max(2, bodyHeight - primaryFloor)
      const menuFloor = Math.min(maxMenuHeight, bodyHeight >= 8 ? 4 : 2)
      let menuHeight = clampNumber(Math.max(2, visibleMenuCount) + 2, menuFloor, maxMenuHeight)
      let primaryHeight = bodyHeight - menuHeight

      if (primaryHeight < primaryFloor && menuHeight > 2) {
        menuHeight = Math.max(2, menuHeight - (primaryFloor - primaryHeight))
        primaryHeight = bodyHeight - menuHeight
      }

      const contentWidth = Math.max(18, width - 6)

      return {
        mode,
        width,
        height,
        summaryHeight,
        primaryHeight,
        detailHeight: 0,
        menuHeight,
        showDetail: false,
        summaryWidth: contentWidth,
        primaryWidth: contentWidth,
        detailWidth: contentWidth,
        menuWidth: contentWidth,
        statusWidth: Math.max(18, width - 2),
        menuMaxVisible: Math.max(1, menuHeight - 2),
        detailLogLimit: 4,
        showMenuIndicators: false,
      }
    }

    const summaryHeight = mode === "full" ? 7 : 6
    const showDetail = true
    const detailMinHeight = mode === "full" ? 6 : 4
    const detailMaxHeight = mode === "full" ? 12 : 8
    const primaryMinHeight = mode === "full" ? 8 : 6
    const menuMinVisible = mode === "full" ? 4 : 3
    const menuMaxVisible = mode === "full" ? 8 : 6
    const statusHeight = 1
    const bodyHeight = Math.max(6, height - summaryHeight - statusHeight)
    const menuFloor = menuMinVisible + 2
    const menuDesiredHeight = clampNumber(Math.max(menuMinVisible, visibleMenuCount) + 2, menuFloor, menuMaxVisible + 2)
    const maxMenuHeight = Math.max(menuFloor, bodyHeight - primaryMinHeight - detailMinHeight)
    const menuHeight = clampNumber(menuDesiredHeight, menuFloor, maxMenuHeight)
    const baseBody = primaryMinHeight + detailMinHeight + menuHeight
    const extra = Math.max(0, bodyHeight - baseBody)
    const detailExtra = Math.min(detailMaxHeight - detailMinHeight, extra)
    const detailHeight = detailMinHeight + detailExtra
    const primaryHeight = primaryMinHeight + (extra - detailExtra)

    const contentWidth = Math.max(18, width - 6)

    return {
      mode,
      width,
      height,
      summaryHeight,
      primaryHeight,
      detailHeight,
      menuHeight,
      showDetail,
      summaryWidth: contentWidth,
      primaryWidth: contentWidth,
      detailWidth: contentWidth,
      menuWidth: contentWidth,
      statusWidth: Math.max(18, width - 2),
      menuMaxVisible: Math.max(2, menuHeight - 2),
      detailLogLimit: mode === "full" ? 8 : 5,
      showMenuIndicators: true,
    }
  }

  private applyLayout(metrics: LayoutMetrics) {
    this.summaryBox.height = metrics.summaryHeight
    this.primaryBox.height = metrics.primaryHeight
    this.detailBox.visible = metrics.showDetail
    if (metrics.showDetail) {
      this.detailBox.height = metrics.detailHeight
    }
    this.menuBox.height = metrics.menuHeight
    this.statusBox.height = 1
  }

  private clampSelection() {
    this.selectedIndex = this.clampIndex(this.selectedIndex, this.menuOptions.length)
    if (this.prompt.mode === "select") {
      this.prompt.selectedIndex = this.clampIndex(this.prompt.selectedIndex, this.prompt.options.length)
    }
  }

  private clampIndex(index: number, total: number): number {
    if (total <= 0) return 0
    return clampNumber(index, 0, total - 1)
  }

  private isDetailPinnedToBottom(): boolean {
    const maxScroll = typeof this.detailText.maxScrollY === "number" ? this.detailText.maxScrollY : 0
    const current = typeof this.detailText.scrollY === "number" ? this.detailText.scrollY : 0
    return maxScroll <= 0 || current >= maxScroll - 1
  }

  private clampDetailScroll() {
    const maxScroll = typeof this.detailText.maxScrollY === "number" ? this.detailText.maxScrollY : 0
    const current = typeof this.detailText.scrollY === "number" ? this.detailText.scrollY : 0
    this.detailText.scrollY = clampNumber(current, 0, Math.max(0, maxScroll))
  }

  private scheduleDetailAdjustment() {
    if (!this.layout.showDetail) {
      this.needsDetailClamp = false
      this.needsDetailScrollEnd = false
      return
    }
    if (this.detailAdjustmentScheduled) return

    this.detailAdjustmentScheduled = true
    void this.renderer.idle().then(() => {
      this.detailAdjustmentScheduled = false
      if (!this.layout.showDetail) {
        this.needsDetailClamp = false
        this.needsDetailScrollEnd = false
        return
      }

      const shouldScrollToEnd = this.needsDetailScrollEnd
      const shouldClamp = this.needsDetailClamp
      this.needsDetailScrollEnd = false
      this.needsDetailClamp = false

      const before = typeof this.detailText.scrollY === "number" ? this.detailText.scrollY : 0
      if (shouldScrollToEnd) {
        this.scrollDetailToEnd()
      } else if (shouldClamp) {
        this.clampDetailScroll()
      }

      const after = typeof this.detailText.scrollY === "number" ? this.detailText.scrollY : 0
      if (after !== before) {
        this.renderer.requestRender()
      }

      if (this.needsDetailClamp || this.needsDetailScrollEnd) {
        this.scheduleDetailAdjustment()
      }
    })
  }

  private getStatusHint(metrics: LayoutMetrics): string {
    if (metrics.mode === "full") {
      return getHint(this.menuName, this.menuCtx)
    }
    if (this.menuName === "main") {
      return "↑↓/1-4 • Enter • r • q"
    }
    if (this.menuName === "confirm") {
      return "Enter • Esc"
    }
    return "↑↓/1-9 • Enter • Esc • r"
  }

  private setStatus(metrics: LayoutMetrics) {
    if (this.prompt.active) {
      if (this.prompt.mode === "select") {
        const option = this.prompt.options[this.prompt.selectedIndex]
        const label = option ? option.label : "нет вариантов"
        const hint = option?.hint && metrics.mode === "full" ? ` • ${option.hint}` : ""
        const content = truncateText(` ${this.prompt.question}: ${label}${hint} `, metrics.statusWidth)
        setRenderableText(
          this.statusText,
          t`${bg("#111827")(fg("#e5e7eb")(bold(content)))}`,
        )
        return
      }
      const typed = this.prompt.hidden ? "*".repeat(this.prompt.value.length) : this.prompt.value
      const value = typed || "_"
      const content = truncateText(` ${this.prompt.question}: ${value} `, metrics.statusWidth)
      setRenderableText(
        this.statusText,
        t`${bg("#111827")(fg("#e5e7eb")(bold(content)))}`,
      )
      return
    }

    const hint = this.getStatusHint(metrics)
    const hintText = truncateText(` ${hint} `, metrics.mode === "full" ? Math.max(18, metrics.statusWidth - 34) : Math.max(14, metrics.statusWidth - 24))
    const backendSeg = this.backendOnline
      ? bg("#14532d")(fg("#dcfce7")(metrics.mode === "fallback" ? " backend ok " : " backend: online "))
      : bg("#7f1d1d")(fg("#fee2e2")(metrics.mode === "fallback" ? " backend off " : " backend: offline "))
    const hintSeg = bg("#334155")(fg("#e2e8f0")(hintText))

    if (this.busy) {
      const title = truncateText(this.busyTitle || "Выполняется...", metrics.mode === "fallback" ? 18 : 28)
      const busySeg = bg("#7c2d12")(fg("#ffedd5")(bold(` ● ${title} `)))
      setRenderableText(this.statusText, t`${busySeg}${hintSeg}${backendSeg}`)
    } else {
      const readySeg = bg("#1e293b")(fg("#e2e8f0")(" ○ Готово "))
      setRenderableText(this.statusText, t`${hintSeg}${readySeg}${backendSeg}`)
    }
  }

  private pushLog(message: string) {
    const shouldStickToBottom = this.isDetailPinnedToBottom()
    this.logs.push(`[${timeStamp()}] ${message}`)
    if (shouldStickToBottom) {
      this.needsDetailScrollEnd = true
    } else {
      this.needsDetailClamp = true
    }
  }

  private scrollDetailToEnd() {
    if (typeof this.detailText.maxScrollY === "number") {
      this.detailText.scrollY = Math.max(0, this.detailText.maxScrollY)
    }
  }

  private render() {
    this.rebuildMenuOptions()
    this.clampSelection()
    const table = getTable(this.menuName, this.state, this.menuCtx)
    const promptMenuOptions: MenuOption[] = this.prompt.mode === "select"
      ? this.prompt.options.map((option) => ({
        id: option.value,
        label: option.label,
        hint: option.hint,
        destructive: option.destructive,
      }))
      : []
    const visibleMenuOptions = this.prompt.active && this.prompt.mode === "select"
      ? promptMenuOptions
      : this.menuOptions
    const visibleMenuIndex = this.prompt.active && this.prompt.mode === "select"
      ? this.prompt.selectedIndex
      : this.selectedIndex
    const metrics = this.computeLayoutMetrics(visibleMenuOptions.length)
    this.layout = metrics
    this.applyLayout(metrics)

    this.summaryBox.title = this.menuName === "main" ? "izTeamSlots" : `Раздел: ${this.getScreenTitle()}`
    this.primaryBox.title = metrics.mode === "fallback"
      ? "Сжатый режим"
      : this.menuName === "main" ? "Быстрый старт" : this.getPrimaryTitle()
    this.detailBox.title = this.prompt.active && this.prompt.mode === "select"
      ? "Выбор"
      : this.menuName === "main" ? "События и подсказки" : "Контекст"
    this.menuBox.title = this.prompt.active && this.prompt.mode === "select" ? "Варианты" : "Действия"

    setRenderableText(this.summaryText, this.buildSummaryPanel(metrics))

    if (metrics.mode === "fallback") {
      setRenderableText(this.primaryText, this.buildFallbackPanel(metrics))
    } else if (this.menuName === "main") {
      setRenderableText(this.primaryText, this.buildMainPanel(metrics))
    } else if (table.rows.length > 0) {
      setRenderableText(
        this.primaryText,
        formatTable(table.headers, table.rows, this.getTableFormatOptions(metrics)),
      )
    } else {
      setRenderableText(this.primaryText, this.buildEmptyStatePanel(metrics))
    }

    setRenderableText(this.detailText, metrics.showDetail ? this.buildDetailPanel(metrics) : t``)
    setRenderableText(
      this.menuText,
      formatMenu(visibleMenuOptions, visibleMenuIndex, {
        maxWidth: metrics.menuWidth,
        maxVisible: metrics.menuMaxVisible,
        density: metrics.mode,
        showIndicators: metrics.showMenuIndicators,
      }),
    )
    this.setStatus(metrics)
    this.renderer.requestRender()
    if (this.needsDetailClamp || this.needsDetailScrollEnd) {
      this.scheduleDetailAdjustment()
    }
  }

  private move(delta: number) {
    if (this.menuOptions.length === 0) return
    const last = this.menuOptions.length - 1
    if (delta > 0) {
      this.selectedIndex = this.selectedIndex >= last ? 0 : this.selectedIndex + 1
    } else {
      this.selectedIndex = this.selectedIndex <= 0 ? last : this.selectedIndex - 1
    }
    this.render()
  }

  private getScreenTitle(): string {
    if (this.menuName === "admins") return "Админы"
    if (this.menuName === "slots") return "Слоты"
    if (this.menuName === "pick_admin") return "Выбор админа"
    if (this.menuName === "pick_worker") return "Выбор слота"
    if (this.menuName === "confirm") return "Подтверждение"
    return "Обзор"
  }

  private getPrimaryTitle(): string {
    if (this.menuCtx.title) return this.menuCtx.title
    return this.getScreenTitle()
  }

  private getTableFormatOptions(metrics: LayoutMetrics) {
    const density: "full" | "compact" = metrics.mode === "full" ? "full" : "compact"
    const base = {
      maxWidth: metrics.primaryWidth,
      density,
      emptyMessage: "Нет данных для отображения.",
    }

    if (this.menuName === "admins" || this.menuName === "pick_admin") {
      return {
        ...base,
        columns: [
          { required: true, minWidth: 18 },
          { required: true, minWidth: 8, priority: 1 },
          { minWidth: 7, priority: 2 },
          { minWidth: 6, priority: 3 },
          { minWidth: 10, priority: 4 },
        ],
        compactColumns: [0, 1],
      }
    }

    if (this.menuName === "slots" || this.menuName === "pick_worker") {
      return {
        ...base,
        columns: [
          { required: true, minWidth: 18 },
          { required: true, minWidth: 8, priority: 1 },
          { minWidth: 8, priority: 2 },
          { minWidth: 10, priority: 3 },
          { minWidth: 6, priority: 4 },
        ],
        compactColumns: [0, 1],
      }
    }

    return base
  }

  private buildSummaryPanel(metrics: LayoutMetrics): StyledText {
    if (metrics.mode === "fallback") {
      if (metrics.summaryHeight <= 4) {
        return joinStyledLines([
          t`${fg("#f8fafc")(bold("izTeamSlots"))}`,
          this.backendOnline
            ? t`${fg("#94a3b8")(truncateText(`Размер ${metrics.width}x${metrics.height} • минимум 80x22`, metrics.summaryWidth))}`
            : t`${fg("#fca5a5")(truncateText(this.getShortConnectionError(), metrics.summaryWidth))}`,
        ])
      }

      return joinStyledLines([
        t`${fg("#f8fafc")(bold("izTeamSlots"))}`,
        t`${fg("#94a3b8")(truncateText(`Размер ${metrics.width}x${metrics.height} • минимум 80x22`, metrics.summaryWidth))}`,
        this.backendOnline
          ? formatDashboard(getDashboard(this.state), { maxWidth: metrics.summaryWidth, density: "fallback" })
          : t`${fg("#fca5a5")(truncateText(this.getShortConnectionError(), metrics.summaryWidth))}`,
      ])
    }

    const lines: StyledText[] = [
      t`${fg("#f8fafc")(bold(`izTeamSlots • ${this.getScreenTitle()}`))}`,
    ]

    if (metrics.mode === "full") {
      lines.push(t`${fg("#64748b")(truncateText("Локальный центр управления слотами", metrics.summaryWidth))}`)
    }

    if (this.backendOnline) {
      lines.push(t`${fg("#4ade80")(truncateText("Подключение активно", metrics.summaryWidth))}`)
    } else {
      lines.push(t`${fg("#fca5a5")(truncateText(`Offline: ${this.getShortConnectionError()}`, metrics.summaryWidth))}`)
    }

    lines.push(formatDashboard(getDashboard(this.state), {
      maxWidth: metrics.summaryWidth,
      density: metrics.mode,
    }))

    return joinStyledLines(lines)
  }

  private buildMainPanel(metrics: LayoutMetrics): StyledText {
    if (!this.backendOnline) {
      return this.buildRecoveryPanel(metrics)
    }

    const adminsReady = this.state.admins.filter((admin) => hasFlag(admin, "has_access_token")).length
    const workersReady = this.state.workers.filter((worker) => hasFlag(worker, "has_access_token")).length
    const stepLimit = metrics.mode === "full" ? 4 : 3
    const lines: StyledText[] = [
      t`${fg("#f8fafc")(bold("Что делать дальше"))}`,
    ]

    for (const step of this.getRecommendedSteps().slice(0, stepLimit)) {
      lines.push(t`${fg("#94a3b8")("•")} ${fg("#e2e8f0")(truncateText(step, metrics.primaryWidth))}`)
    }

    lines.push(t`${fg("#475569")(" ")}`)
    lines.push(
      t`${fg("#94a3b8")("Готовность")} ${fg("#e2e8f0")(truncateText(`${adminsReady}/${this.state.admins.length || 0} админов, ${workersReady}/${this.state.workers.length || 0} слотов`, metrics.primaryWidth - 12))}`,
    )

    const hint = metrics.mode === "full"
      ? "Стрелки и цифры работают и в меню, и в режимах выбора. Enter подтверждает, r обновляет состояние."
      : "Меню снизу остаётся активным во время ресайза. Enter подтверждает, Esc возвращает назад."
    lines.push(
      t`${fg("#94a3b8")("Подсказка")} ${fg("#cbd5e1")(truncateText(hint, metrics.primaryWidth - 10))}`,
    )

    return joinStyledLines(lines)
  }

  private buildFallbackPanel(metrics: LayoutMetrics): StyledText {
    const lines: StyledText[] = [
      t`${fg("#f8fafc")(bold("Окно слишком маленькое"))}`,
      t`${fg("#94a3b8")(truncateText(`Текущий размер: ${metrics.width}x${metrics.height}. Рекомендуемый минимум: 80x22.`, metrics.primaryWidth))}`,
    ]

    if (this.busy) {
      lines.push(t`${fg("#fdba74")(truncateText(`Идёт задача: ${this.busyTitle || "операция"}`, metrics.primaryWidth))}`)
    } else if (this.backendOnline) {
      lines.push(t`${fg("#4ade80")("Backend активен. Меню снизу остаётся рабочим.")}`)
    } else {
      lines.push(t`${fg("#fca5a5")(truncateText(`Backend offline: ${this.getShortConnectionError()}`, metrics.primaryWidth))}`)
    }

    if (this.prompt.active && this.prompt.mode === "input") {
      const rawValue = this.prompt.hidden ? "*".repeat(this.prompt.value.length) : this.prompt.value || "_"
      lines.push(t`${fg("#93c5fd")(truncateText(`${this.prompt.question}: ${rawValue}`, metrics.primaryWidth))}`)
    } else if (this.prompt.active && this.prompt.mode === "select") {
      const option = this.prompt.options[this.prompt.selectedIndex]
      const label = option ? option.label : "нет вариантов"
      lines.push(t`${fg("#93c5fd")(truncateText(`${this.prompt.question}: ${label}`, metrics.primaryWidth))}`)
      if (option?.hint) {
        lines.push(t`${fg("#64748b")(truncateText(option.hint, metrics.primaryWidth))}`)
      }
    } else {
      lines.push(t`${fg("#cbd5e1")(truncateText(`Раздел: ${this.getScreenTitle()}. Для полной таблицы увеличьте окно.`, metrics.primaryWidth))}`)
    }

    if (metrics.primaryHeight > 6) {
      lines.push(t`${fg("#64748b")(truncateText(`Клавиши: ${this.getStatusHint(metrics)}`, metrics.primaryWidth))}`)
    }

    return joinStyledLines(lines)
  }

  private buildRecoveryPanel(metrics: LayoutMetrics): StyledText {
    const lines: StyledText[] = [
      t`${fg("#f8fafc")(bold("Backend недоступен"))}`,
      t`${fg("#fca5a5")(truncateText(this.getShortConnectionError(), metrics.primaryWidth))}`,
      t`${fg("#94a3b8")("Проверьте окружение и повторите обновление клавишей r.")}`,
    ]

    const error = this.connectionError.toLowerCase()
    if (error.includes("no module named 'requests'")) {
      lines.push(t`${fg("#93c5fd")(truncateText("Подсказка: установите Python-пакет requests.", metrics.primaryWidth))}`)
    } else if (error.includes("no module named 'seleniumbase'")) {
      lines.push(t`${fg("#93c5fd")(truncateText("Подсказка: установите seleniumbase.", metrics.primaryWidth))}`)
    } else {
      lines.push(t`${fg("#93c5fd")(truncateText("Подсказка: проверьте python-зависимости и запуск backend модуля.", metrics.primaryWidth))}`)
    }

    return joinStyledLines(lines)
  }

  private getRecommendedSteps(): string[] {
    if (this.state.admins.length === 0) {
      return [
        "Откройте «Настройки» и укажите API-ключ временной почты.",
        "Добавьте первого админа через раздел «Админы».",
        "После добавления выполните логин, чтобы сохранить токен и профиль браузера.",
        "Затем создайте слоты через раздел «Слоты».",
      ]
    }

    const adminsWithoutLogin = this.state.admins.filter((admin) => !hasFlag(admin, "has_access_token")).length
    if (adminsWithoutLogin > 0) {
      return [
        "Перелогиньте хотя бы одного админа.",
        "Убедитесь, что у него есть токен и рабочий браузерный профиль.",
        "После этого можно запускать создание слотов.",
      ]
    }

    if (this.state.workers.length === 0) {
      return [
        "Откройте раздел «Слоты».",
        "Запустите создание слотов под нужным админом.",
        "После завершения проверьте состояние слотов в таблице.",
      ]
    }

    const workersWithoutPassword = this.state.workers.filter((worker) => !worker.has_openai_password).length
    if (workersWithoutPassword > 0) {
      return [
        "Часть слотов ещё не готова к перелогину.",
        "Проверьте, что для нужных слотов сохранён OpenAI-пароль.",
        "Используйте перелогин, чтобы восстановить доступ к проблемным слотам.",
      ]
    }

    return [
      "Система выглядит рабочей.",
      "Для обслуживания используйте перелогин и проверку через браузер.",
      "Последние события и ошибки всегда видны в нижней панели.",
    ]
  }

  private buildDetailPanel(metrics: LayoutMetrics): StyledText {
    if (!this.backendOnline) {
      return this.buildRecoveryPanel(metrics)
    }

    if (this.prompt.active && this.prompt.mode === "select") {
      const option = this.prompt.options[this.prompt.selectedIndex]
      const lines: StyledText[] = [
        t`${fg("#f8fafc")(bold(this.prompt.question))}`,
      ]
      if (option) {
        lines.push(t`${fg("#93c5fd")("•")} ${fg("#e2e8f0")(truncateText(option.label, metrics.detailWidth - 4))}`)
        if (option.hint) {
          lines.push(t`${fg("#94a3b8")(truncateText(option.hint, metrics.detailWidth))}`)
        }
      }
      lines.push(t`${fg("#64748b")(metrics.mode === "full" ? "Enter выбрать • Esc отмена • Стрелки перемещают курсор" : "Enter выбрать • Esc отмена")}`)
      return joinStyledLines(lines)
    }

    const lines: StyledText[] = []
    const selected = this.menuOptions[this.selectedIndex]
    const extra = selected as MenuOption & { badge?: string }

    if (selected) {
      const badge = extra?.badge ? ` • ${extra.badge}` : ""
      lines.push(t`${fg("#f8fafc")(bold(truncateText(`${selected.label}${badge}`, metrics.detailWidth)))}`)
      lines.push(t`${fg("#94a3b8")(truncateText(getMenuOptionDescription(selected), metrics.detailWidth))}`)
    }

    const noteLimit = metrics.mode === "full" ? 3 : 1
    for (const note of this.getContextNotes().slice(0, noteLimit)) {
      lines.push(t`${fg("#93c5fd")("•")} ${fg("#cbd5e1")(truncateText(note, metrics.detailWidth - 4))}`)
    }

    const recentLogs = this.logs.slice(-metrics.detailLogLimit)
    if (recentLogs.length > 0) {
      lines.push(t`${fg("#475569")(" ")}`)
      lines.push(t`${fg("#f8fafc")(bold("Последние события"))}`)
      for (const log of recentLogs) {
        lines.push(t`${fg("#94a3b8")(truncateText(log, metrics.detailWidth))}`)
      }
    } else {
      lines.push(t`${fg("#64748b")("Событий пока нет.")}`)
    }

    return joinStyledLines(lines)
  }

  private buildEmptyStatePanel(metrics: LayoutMetrics): StyledText {
    const lines: StyledText[] = [t`${fg("#f8fafc")(bold("Пока пусто"))}`]

    if (this.menuName === "admins") {
      lines.push(t`${fg("#cbd5e1")(truncateText("Сначала добавьте первого админа, затем выполните логин.", metrics.primaryWidth))}`)
    } else if (this.menuName === "slots") {
      lines.push(t`${fg("#cbd5e1")(truncateText("Слоты появятся после запуска пайплайна от выбранного админа.", metrics.primaryWidth))}`)
    } else if (this.menuName === "pick_admin" || this.menuName === "pick_worker") {
      lines.push(t`${fg("#cbd5e1")(truncateText("Нет доступных элементов для выбора. Вернитесь назад и подготовьте данные.", metrics.primaryWidth))}`)
    } else {
      lines.push(t`${fg("#cbd5e1")(truncateText("Добавьте данные или вернитесь на главный экран.", metrics.primaryWidth))}`)
    }

    return joinStyledLines(lines)
  }

  private getContextNotes(): string[] {
    if (this.menuName === "admins") {
      const ready = this.state.admins.filter((admin) => hasFlag(admin, "has_access_token")).length
      return [
        `Всего админов: ${this.state.admins.length}. Готовы к работе: ${ready}.`,
        "Для создания слотов нужен админ с токеном и рабочим браузерным профилем.",
      ]
    }

    if (this.menuName === "slots") {
      const withPassword = this.state.workers.filter((worker) => worker.has_openai_password).length
      return [
        `Всего слотов: ${this.state.workers.length}. С OpenAI-паролем: ${withPassword}.`,
        "Массовый перелогин работает только для слотов с сохранённым паролем.",
      ]
    }

    if (this.menuName === "pick_admin") {
      const option = this.menuOptions[this.selectedIndex]
      const email = option?.id.split(":", 2)[1]
      const admin = this.state.admins.find((item) => item.email === email)
      if (!admin) return ["Админ не найден в текущем состоянии."]

      return [
        `${admin.email}`,
        `Токен: ${boolLabel(admin.has_access_token)} • Профиль: ${boolLabel(hasFlag(admin, "has_browser_profile"))}`,
        `Последний логин: ${formatShortDate(admin.last_login)}`,
      ]
    }

    if (this.menuName === "pick_worker") {
      const option = this.menuOptions[this.selectedIndex]
      const email = option?.id.split(":", 2)[1]
      const worker = this.state.workers.find((item) => item.email === email)
      if (!worker) return ["Слот не найден в текущем состоянии."]

      return [
        `${worker.email}`,
        `Статус: ${statusLabel(worker.status)} • Профиль: ${boolLabel(hasFlag(worker, "has_browser_profile"))}`,
        `Админ: ${worker.admin_email ?? "не назначен"} • OpenAI-пароль: ${boolLabel(worker.has_openai_password)}`,
      ]
    }

    if (this.menuName === "confirm") {
      return [
        `Действие: ${this.menuCtx.confirm_action ?? "подтверждение"}`,
        `Объект: ${this.menuCtx.target ?? "не выбран"}`,
      ]
    }

    return []
  }

  private getShortConnectionError(): string {
    const message = this.connectionError || "ошибка подключения"
    if (message.includes("RPC process exited before response")) {
      return "backend завершился во время запуска или не смог ответить"
    }
    if (message.includes("RPC spawn error")) {
      return "не удалось запустить backend-процесс"
    }
    return message.length > 120 ? `${message.slice(0, 119)}…` : message
  }

  private async goBack() {
    if (this.busy || this.prompt.active) return
    if (this.menuName === "main") return
    this.menuName = parentMenu(this.menuName, this.menuCtx)
    this.menuCtx = {}
    this.selectedIndex = 0
    await this.refreshState()
  }

  private async promptInput(question: string, hidden = false): Promise<string | null> {
    this.prompt.active = true
    this.prompt.mode = "input"
    this.prompt.question = question
    this.prompt.hidden = hidden
    this.prompt.value = ""
    this.prompt.options = []
    this.prompt.selectedIndex = 0
    this.render()

    return await new Promise((resolve) => {
      this.prompt.resolve = resolve
    })
  }

  private async promptSelect(question: string, options: PromptOption[]): Promise<string | null> {
    if (options.length === 0) return null
    this.prompt.active = true
    this.prompt.mode = "select"
    this.prompt.question = question
    this.prompt.hidden = false
    this.prompt.value = ""
    this.prompt.options = options
    this.prompt.selectedIndex = 0
    this.render()

    return await new Promise((resolve) => {
      this.prompt.resolve = resolve
    })
  }

  private finishPrompt(value: string | null) {
    const resolve = this.prompt.resolve
    this.prompt.active = false
    this.prompt.mode = "input"
    this.prompt.question = ""
    this.prompt.hidden = false
    this.prompt.value = ""
    this.prompt.options = []
    this.prompt.selectedIndex = 0
    this.prompt.resolve = null
    resolve?.(value)
    this.render()
  }

  private async promptLoginMode(): Promise<"auto" | "manual" | null> {
    const value = await this.promptSelect("Режим входа", [
      { value: "auto", label: "Авто", hint: "Логин по данным из TUI." },
      { value: "manual", label: "Вручную", hint: "Логин вручную в браузере." },
    ])
    if (value === "auto" || value === "manual") return value
    return null
  }

  private async startAdminLogin(email: string, mode: "auto" | "manual") {
    const method = mode === "manual" ? "job.login_admin_manual" : "job.login_admin"
    await this.startJob(method, { email })
  }

  private async promptSlotReloginScope(): Promise<"one" | "all" | null> {
    const value = await this.promptSelect("Перелогин слотов", [
      { value: "one", label: "Один слот", hint: "Перелогинить один слот." },
      { value: "all", label: "Все слоты", hint: "Перелогинить все готовые слоты." },
    ])
    if (value === "one" || value === "all") return value
    return null
  }

  private async submitOption(optionId: string) {
    if (this.menuName === "main") {
      if (optionId === "menu_admins") this.menuName = "admins"
      else if (optionId === "menu_slots") this.menuName = "slots"
      else if (optionId === "menu_settings") {
        this.menuName = "settings"
        this.menuCtx = {}
        this.selectedIndex = 0
        await this.loadSettings()
        return
      }
      else if (optionId === "menu_exit") { await this.exit(); return }
      this.menuCtx = {}
      this.selectedIndex = 0
      await this.refreshState()
      return
    }

    if (this.menuName === "admins") {
      if (optionId === "adm_add") {
        const loginMode = await this.promptLoginMode()
        if (!loginMode) return
        if (loginMode === "manual") {
          await this.startJob("job.add_admin_manual")
          return
        }

        const email = await this.promptInput("Email админа")
        if (!email) return
        const password = await this.promptInput("Пароль почты", true)
        if (!password) return
        try {
          await this.rpc.request("admin.add", { email, password })
        } catch (error) {
          this.pushLog(`Ошибка: ${String(error)}`)
          this.render()
          return
        }
        await this.startAdminLogin(email, loginMode)
        return
      }
      if (optionId === "adm_relogin") {
        this.goToPicker("pick_admin", "admins", "relogin_admin", "Выберите админа")
        return
      }
      if (optionId === "adm_open") {
        this.goToPicker("pick_admin", "admins", "open_admin", "Открыть браузер админа")
        return
      }
      if (optionId === "adm_delete") {
        this.goToPicker("pick_admin", "admins", "delete_admin", "Удалить админа")
        return
      }
    }

    if (this.menuName === "slots") {
      if (optionId === "slots_create") {
        this.goToPicker("pick_admin", "slots", "slots_create", "Выберите админа для слотов")
        return
      }
      if (optionId === "slots_relogin") {
        const scope = await this.promptSlotReloginScope()
        if (!scope) return
        if (scope === "all") {
          await this.startJob("job.relogin_all_workers")
          return
        }
        this.goToPicker("pick_worker", "slots", "relogin_worker", "Выберите слот")
        return
      }
      if (optionId === "slots_open") {
        this.goToPicker("pick_worker", "slots", "open_worker", "Открыть браузер слота")
        return
      }
      if (optionId === "slots_delete") {
        this.goToPicker("pick_worker", "slots", "delete_worker", "Удалить слот")
        return
      }
    }

    if (this.menuName === "settings" && optionId.startsWith("setting:")) {
      const key = optionId.split(":", 2)[1]
      const current = this.state.settings?.find(s => s.key === key)
      const newValue = await this.promptInput(`${current?.label ?? key}`, key.includes("KEY"))
      if (newValue === null) return
      try {
        await this.rpc.request("settings.set", { key, value: newValue })
        this.pushLog(`Настройка ${key} обновлена`)
      } catch (error) {
        this.pushLog(`Ошибка: ${String(error)}`)
      }
      await this.loadSettings()
      this.render()
      return
    }

    if (this.menuName === "pick_admin" && optionId.startsWith("pick_admin:")) {
      const email = optionId.split(":", 2)[1]
      const action = this.menuCtx.action
      const parent = (this.menuCtx.parent ?? "main") as MenuName

      if (action === "relogin_admin") {
        const loginMode = await this.promptLoginMode()
        if (!loginMode) return
        this.menuName = parent
        this.menuCtx = {}
        await this.startAdminLogin(email, loginMode)
        return
      }
      if (action === "open_admin") {
        this.menuName = parent
        this.menuCtx = {}
        await this.startJob("job.open_admin_browser", { email })
        return
      }
      if (action === "delete_admin") {
        this.goToConfirm(parent, "delete_admin", "Удаление админа", email)
        return
      }
      if (action === "slots_create") {
        const countRaw = await this.promptInput(`Количество слотов для ${email}`)
        if (!countRaw) return
        const count = Number(countRaw)
        if (!Number.isInteger(count) || count <= 0) {
          this.pushLog("Некорректное число")
          this.render()
          return
        }
        this.menuName = parent
        this.menuCtx = {}
        await this.startJob("job.run_slots", { admin_email: email, count })
        return
      }
    }

    if (this.menuName === "pick_worker" && optionId.startsWith("pick_worker:")) {
      const email = optionId.split(":", 2)[1]
      const action = this.menuCtx.action
      const parent = (this.menuCtx.parent ?? "slots") as MenuName

      if (action === "relogin_worker") {
        this.menuName = parent
        this.menuCtx = {}
        await this.startJob("job.relogin_worker", { email })
        return
      }
      if (action === "open_worker") {
        this.menuName = parent
        this.menuCtx = {}
        await this.startJob("job.open_worker_browser", { email })
        return
      }
      if (action === "delete_worker") {
        this.goToConfirm(parent, "delete_worker", "Удаление слота", email)
        return
      }
    }

    if (this.menuName === "confirm") {
      const action = this.menuCtx.action
      const target = this.menuCtx.target
      const parent = (this.menuCtx.parent ?? "main") as MenuName

      if (optionId === "confirm_no") {
        this.menuName = parent
        this.menuCtx = {}
        await this.refreshState()
        return
      }

      if (optionId === "confirm_yes" && target) {
        try {
          if (action === "delete_admin") {
            await this.rpc.request("admin.delete", { email: target })
            this.pushLog(`Удалён админ: ${target}`)
          }
          if (action === "delete_worker") {
            await this.rpc.request("worker.delete", { email: target })
            this.pushLog(`Удалён слот: ${target}`)
          }
        } catch (error) {
          this.pushLog(`Ошибка: ${String(error)}`)
        }
        this.menuName = parent
        this.menuCtx = {}
        await this.refreshState()
      }
    }
  }

  private goToPicker(picker: MenuName, parent: MenuName, action: string, title: string) {
    this.menuName = picker
    this.menuCtx = { parent, action, title }
    this.selectedIndex = 0
    this.render()
  }

  private goToConfirm(parent: MenuName, action: string, confirmAction: string, target: string) {
    this.menuName = "confirm"
    this.menuCtx = {
      parent,
      action,
      confirm_action: confirmAction,
      title: `${confirmAction}: ${target}`,
      target,
    }
    this.selectedIndex = 1
    this.render()
  }

  private async startJob(method: string, params: Record<string, unknown> = {}) {
    if (this.busy) return
    this.busy = true
    try {
      const result = await this.rpc.request<RpcJobResult>(method, params)
      this.backendOnline = true
      this.pushLog(`Задача ${result.job_id.slice(0, 8)} поставлена в очередь`)
    } catch (error) {
      this.busy = false
      this.pushLog(`Ошибка: ${String(error)}`)
    }
    this.render()
  }

  private onPaste(event: any) {
    if (!this.prompt.active) return
    if (this.prompt.mode !== "input") return
    const text = String(event?.text ?? "")
    if (!text) return
    const normalized = text.replace(/\r\n?/g, "\n").split("\n")[0]
    this.prompt.value += normalized
    this.render()
  }

  private copySelectedLogToClipboard() {
    const selected = this.renderer.getSelection()?.getSelectedText()?.trim() ?? ""
    const fallback = this.detailText.getSelectedText?.().trim() ?? ""
    const text = selected || fallback
    if (!text) return
    const copiedViaOsc52 = this.renderer.copyToClipboardOSC52(text)
    const copied = copiedViaOsc52 || copyToSystemClipboard(text)
    this.pushLog(copied ? "Скопировано в буфер обмена" : "Копирование не поддерживается")
    this.render()
  }

  private async onKey(key: any) {
    if (this.prompt.active) {
      if (this.prompt.mode === "select") {
        if (key.name === "return") {
          const option = this.prompt.options[this.prompt.selectedIndex]
          this.finishPrompt(option?.value ?? null)
          return
        }
        if (key.name === "escape") {
          this.finishPrompt(null)
          return
        }
        if (key.name === "up" || key.name === "k") {
          const total = this.prompt.options.length
          if (total > 0) {
            this.prompt.selectedIndex = this.prompt.selectedIndex <= 0 ? total - 1 : this.prompt.selectedIndex - 1
            this.render()
          }
          return
        }
        if (key.name === "down" || key.name === "j") {
          const total = this.prompt.options.length
          if (total > 0) {
            this.prompt.selectedIndex = this.prompt.selectedIndex >= total - 1 ? 0 : this.prompt.selectedIndex + 1
            this.render()
          }
          return
        }
        if (key.sequence >= "1" && key.sequence <= "9" && !key.ctrl && !key.meta) {
          const index = Number(key.sequence) - 1
          if (index < this.prompt.options.length) {
            this.prompt.selectedIndex = index
            this.render()
          }
          return
        }
        return
      }

      if (key.name === "return") {
        const value = this.prompt.value.trim()
        this.finishPrompt(value ? value : null)
        return
      }
      if (key.name === "escape") {
        this.finishPrompt(null)
        return
      }
      if (key.name === "backspace") {
        this.prompt.value = this.prompt.value.slice(0, -1)
        this.render()
        return
      }
      if (typeof key.sequence === "string" && key.sequence.length === 1 && !key.ctrl && !key.meta) {
        this.prompt.value += key.sequence
        this.render()
      }
      return
    }

    if (key.name === "y" && !key.ctrl && !key.meta) {
      this.copySelectedLogToClipboard()
      return
    }
    if ((key.ctrl || key.meta) && key.name === "c") {
      if (this.busy) {
        const now = Date.now()
        if (now - this._lastCtrlC < 1500) {
          this.pushLog("Аварийный выход...")
          this.renderer.destroy()
          process.exit(1)
        }
        this._lastCtrlC = now
        this.pushLog("Нажмите Ctrl+C ещё раз для аварийного выхода")
        this.render()
        return
      }
      this.copySelectedLogToClipboard()
      return
    }

    if (this.busy) {
      if (key.name === "q") {
        this.pushLog("Дождитесь завершения задачи перед выходом (Ctrl+C×2 — аварийный выход)")
        this.render()
      }
      return
    }

    if (key.name === "r" && !key.ctrl && !key.meta) {
      await this.refreshState()
      return
    }

    if (key.sequence >= "1" && key.sequence <= "9" && !key.ctrl && !key.meta) {
      const index = Number(key.sequence) - 1
      if (index < this.menuOptions.length) {
        this.selectedIndex = index
        await this.submitOption(this.menuOptions[index].id)
      }
      return
    }

    if (key.name === "up" || key.name === "k") {
      this.move(-1)
      return
    }
    if (key.name === "down" || key.name === "j") {
      this.move(1)
      return
    }
    if (key.name === "escape") {
      await this.goBack()
      return
    }
    if (key.name === "return") {
      const selected = this.menuOptions[this.selectedIndex]
      if (selected) await this.submitOption(selected.id)
      return
    }
    if (key.name === "q") {
      await this.exit()
    }
  }

  private async exit() {
    try {
      await this.rpc.shutdown()
    } catch {
      // no-op
    }
    this.renderer.destroy()
    process.exit(0)
  }
}
