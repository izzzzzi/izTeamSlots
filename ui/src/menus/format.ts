import { StyledText, bg, bold, fg, stringToStyledText, t } from "@opentui/core"
import type { DashboardData, MenuOption } from "./types"

export type LayoutDensity = "full" | "compact" | "fallback"

type TableColumnPolicy = {
  minWidth?: number
  priority?: number
  required?: boolean
}

type TableLayout = {
  indices: number[]
  widths: number[]
  fits: boolean
}

export type TableFormatOptions = {
  maxWidth?: number
  density?: LayoutDensity
  emptyMessage?: string
  columns?: TableColumnPolicy[]
  compactColumns?: number[]
}

type ResolvedTableFormatOptions = {
  maxWidth: number
  density: LayoutDensity
  emptyMessage: string
  columns: TableColumnPolicy[]
  compactColumns: number[]
}

export type MenuFormatOptions = {
  maxWidth?: number
  maxVisible?: number
  density?: LayoutDensity
  showIndicators?: boolean
}

export type DashboardFormatOptions = {
  maxWidth?: number
  density?: LayoutDensity
}

function truncate(value: string, width: number): string {
  if (width <= 0) return ""
  if (width === 1) return value.slice(0, 1)
  if (value.length <= width) return value
  return `${value.slice(0, width - 1)}…`
}

function pad(value: string, width: number): string {
  const v = truncate(value, width)
  if (v.length >= width) return v
  return v + " ".repeat(width - v.length)
}

function totalTableWidth(widths: number[]): number {
  if (widths.length === 0) return 0
  return widths.reduce((acc, value) => acc + value, 0) + (widths.length - 1) * 3
}

function buildWidths(
  headers: string[],
  rows: string[][],
  indices: number[],
  policies: TableColumnPolicy[],
  minCol: number,
  maxCol: number,
): number[] {
  return indices.map((columnIndex) => {
    let width = headers[columnIndex]?.length ?? 0
    for (const row of rows) {
      width = Math.max(width, (row[columnIndex] ?? "").length)
    }
    const minWidth = Math.max(4, policies[columnIndex]?.minWidth ?? minCol)
    return Math.max(minWidth, Math.min(width, maxCol))
  })
}

function shrinkWidths(widths: number[], indices: number[], policies: TableColumnPolicy[], maxWidth: number, minCol: number) {
  while (totalTableWidth(widths) > maxWidth) {
    let candidate = -1
    for (let i = 0; i < widths.length; i++) {
      const columnIndex = indices[i]
      const minWidth = Math.max(4, policies[columnIndex]?.minWidth ?? minCol)
      if (widths[i] <= minWidth) continue
      if (candidate === -1 || widths[i] > widths[candidate]) {
        candidate = i
      }
    }

    if (candidate === -1) break
    widths[candidate] -= 1
  }
}

function buildTableLayout(
  headers: string[],
  rows: string[][],
  options: ResolvedTableFormatOptions,
): TableLayout {
  const policies = headers.map((_, index) => options.columns?.[index] ?? {})
  const minCol = options.density === "full" ? 8 : 6
  const maxCol = options.density === "full" ? 48 : 36
  let indices = headers.map((_, index) => index)
  let widths = buildWidths(headers, rows, indices, policies, minCol, maxCol)
  shrinkWidths(widths, indices, policies, options.maxWidth, minCol)

  if (totalTableWidth(widths) > options.maxWidth) {
    const removable = indices
      .filter((index) => !policies[index]?.required)
      .sort((left, right) => (policies[right]?.priority ?? 0) - (policies[left]?.priority ?? 0))

    for (const columnIndex of removable) {
      if (indices.length <= 2) break
      indices = indices.filter((value) => value !== columnIndex)
      widths = buildWidths(headers, rows, indices, policies, minCol, maxCol)
      shrinkWidths(widths, indices, policies, options.maxWidth, minCol)
      if (totalTableWidth(widths) <= options.maxWidth) {
        return { indices, widths, fits: true }
      }
    }
  }

  if (totalTableWidth(widths) > options.maxWidth && options.compactColumns.length > 0) {
    const compactIndices = options.compactColumns
      .filter((index, position, all) => index >= 0 && index < headers.length && all.indexOf(index) === position)
      .slice(0, 2)

    if (compactIndices.length > 0) {
      indices = compactIndices
      widths = buildWidths(headers, rows, indices, policies, minCol, maxCol)
      shrinkWidths(widths, indices, policies, options.maxWidth, minCol)
      if (totalTableWidth(widths) > options.maxWidth && indices.length > 1) {
        indices = [indices[0]]
        widths = buildWidths(headers, rows, indices, policies, minCol, maxCol)
        shrinkWidths(widths, indices, policies, options.maxWidth, minCol)
      }
    }
  }

  return {
    indices,
    widths,
    fits: totalTableWidth(widths) <= options.maxWidth,
  }
}

export function formatTable(headers: string[], rows: string[][], options: TableFormatOptions = {}): StyledText {
  if (headers.length === 0) return stringToStyledText("")

  const resolved = {
    maxWidth: options.maxWidth ?? 120,
    density: options.density ?? "full",
    emptyMessage: options.emptyMessage ?? "Нет данных для отображения.",
    columns: options.columns ?? [],
    compactColumns: options.compactColumns ?? [],
  }

  const layout = buildTableLayout(headers, rows, resolved)
  const headersToRender = layout.indices.map((index) => headers[index])
  const rowsToRender = rows.map((row) => layout.indices.map((index) => row[index] ?? ""))
  const rowToLine = (row: string[]): string => row.map((value, index) => pad(value ?? "", layout.widths[index])).join(" │ ")
  const headerLine = rowToLine(headersToRender)
  const divider = layout.widths.map((width) => "─".repeat(width)).join("─┼─")
  const lines: StyledText[] = [
    t`${bg("#334155")(fg("#f8fafc")(bold(headerLine)))}`,
    t`${fg("#64748b")(divider)}`,
  ]

  if (rowsToRender.length === 0) {
    lines.push(t`${fg("#64748b")(truncate(resolved.emptyMessage, Math.max(12, resolved.maxWidth)))}`)
  } else {
    lines.push(
      ...rowsToRender.map((row, index) => {
        const line = rowToLine(row)
        return index % 2 === 0 ? t`${fg("#cbd5e1")(line)}` : t`${bg("#111827")(fg("#cbd5e1")(line))}`
      }),
    )
  }

  if (!layout.fits && layout.indices.length === 1) {
    lines.push(t`${fg("#fbbf24")(truncate("Увеличьте окно для полной таблицы.", Math.max(12, resolved.maxWidth)))}`)
  }

  return joinStyledLines(lines)
}

export function formatMenu(options: MenuOption[], selected: number, config: MenuFormatOptions = {}): StyledText {
  if (options.length === 0) {
    return t`${fg("#94a3b8")("(пусто)")}`
  }

  const density = config.density ?? "full"
  const maxWidth = config.maxWidth ?? 80
  const showIndicators = config.showIndicators ?? density !== "fallback"
  const labelFloor = density === "full" ? 18 : density === "compact" ? 14 : 12
  const labelCeiling = density === "full" ? 28 : density === "compact" ? 22 : 18
  const longestLabel = options.reduce((max, option) => Math.max(max, option.label.length), 0)
  const labelWidth = Math.max(labelFloor, Math.min(longestLabel + 2, labelCeiling, Math.max(labelFloor, maxWidth - 8)))
  const rawHintWidth = maxWidth - labelWidth - 8
  const hintWidth = density === "fallback" || rawHintWidth < 10
    ? 0
    : density === "compact"
      ? Math.max(12, rawHintWidth)
      : Math.max(20, rawHintWidth)

  const limit = config.maxVisible && config.maxVisible > 0 ? config.maxVisible : options.length
  let start = 0
  if (options.length > limit) {
    start = Math.max(0, Math.min(selected - Math.floor(limit / 2), options.length - limit))
  }
  const end = Math.min(start + limit, options.length)
  const lines: StyledText[] = []

  if (showIndicators && start > 0) {
    lines.push(t`${fg("#64748b")(`  ▲ ещё ${start}`)}`)
  }

  for (let index = start; index < end; index++) {
    const option = options[index]
    const num = index < 9 ? `${index + 1}.` : "• "
    const label = pad(option.label, labelWidth)
    const hint = option.hint && hintWidth > 0 ? `  ${truncate(option.hint, hintWidth)}` : ""
    const activeBg = option.destructive ? "#7f1d1d" : "#2563eb"
    const activeFg = option.destructive ? "#fee2e2" : "#eff6ff"
    const inline = `${label}${hint}`

    if (index === selected) {
      lines.push(t`${bg(activeBg)(fg(activeFg)(bold(` ${num} ${inline} `)))}`)
    } else if (option.destructive) {
      lines.push(t`${fg("#64748b")(` ${num}`)} ${fg("#f87171")(label)}${fg("#64748b")(hint)}`)
    } else {
      lines.push(t`${fg("#64748b")(` ${num}`)} ${fg("#cbd5e1")(label)}${fg("#64748b")(hint)}`)
    }
  }

  if (showIndicators && end < options.length) {
    lines.push(t`${fg("#64748b")(`  ▼ ещё ${options.length - end}`)}`)
  }

  return joinStyledLines(lines)
}

export function formatDashboard(data: DashboardData, options: DashboardFormatOptions = {}): StyledText {
  const density = options.density ?? "full"
  const maxWidth = options.maxWidth ?? 72

  const adminReady = data.admins_total === 0 ? "нужен первый" : `${data.admins_ready}/${data.admins_total} готовы`
  const workerDetail = data.workers_total === 0
    ? "можно создавать первые"
    : `${data.workers_ready}/${data.workers_total} готовы`
  const passwordDetail = data.workers_with_password > 0 ? ` • ${data.workers_with_password} с паролем` : ""

  if (density === "fallback") {
    return t`${fg("#94a3b8")("A ")}${fg("#f8fafc")(bold(`${data.admins_ready}/${data.admins_total}`))}${fg("#64748b")(" • ")}${fg("#94a3b8")("S ")}${fg("#f8fafc")(bold(`${data.workers_ready}/${data.workers_total}`))}`
  }

  const adminColor = data.admins_total > 0 && data.admins_ready === data.admins_total ? "#4ade80" : "#fbbf24"
  const workerColor = data.workers_total > 0 && data.workers_ready === data.workers_total ? "#4ade80" : "#93c5fd"
  const adminLine = `Админы ${data.admins_total} • ${adminReady}`
  const workerLine = `Слоты ${data.workers_total} • ${workerDetail}${density === "full" ? passwordDetail : ""}`

  return joinStyledLines([
    t`${fg(adminColor)(truncate(adminLine, Math.max(18, maxWidth)))}`,
    t`${fg(workerColor)(truncate(workerLine, Math.max(18, maxWidth)))}`,
  ])
}

export function joinStyledLines(lines: StyledText[]): StyledText {
  const chunks: StyledText["chunks"] = []
  for (let i = 0; i < lines.length; i++) {
    chunks.push(...lines[i].chunks)
    if (i < lines.length - 1) chunks.push(...stringToStyledText("\n").chunks)
  }
  return new StyledText(chunks)
}
