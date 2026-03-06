import { StyledText, bg, bold, fg, stringToStyledText, t } from "@opentui/core"
import type { DashboardData, MenuOption } from "./types"

function truncate(value: string, width: number): string {
  if (width <= 1) return value.slice(0, width)
  if (value.length <= width) return value
  return `${value.slice(0, width - 1)}…`
}

function pad(value: string, width: number): string {
  const v = truncate(value, width)
  if (v.length >= width) return v
  return v + " ".repeat(width - v.length)
}

export function formatTable(
  headers: string[],
  rows: string[][],
  maxWidth = 120,
  emptyMessage = "Нет данных для отображения.",
): StyledText {
  const allRows = [headers, ...rows]
  if (allRows.length === 0) return stringToStyledText("")

  const cols = headers.length
  const widths = new Array(cols).fill(0)
  for (const row of allRows) {
    for (let i = 0; i < cols; i++) {
      const cell = row[i] ?? ""
      widths[i] = Math.max(widths[i], cell.length)
    }
  }

  const minCol = 8
  for (let i = 0; i < cols; i++) widths[i] = Math.max(minCol, Math.min(widths[i], 48))

  const separatorWidth = (cols - 1) * 3
  const total = widths.reduce((a: number, b: number) => a + b, 0) + separatorWidth
  if (total > maxWidth) {
    const overflow = total - maxWidth
    const perColCut = Math.ceil(overflow / cols)
    for (let i = 0; i < cols; i++) widths[i] = Math.max(minCol, widths[i] - perColCut)
  }

  const rowToLine = (row: string[]): string => row.map((v, i) => pad(v ?? "", widths[i])).join(" │ ")
  const headerLine = rowToLine(headers)
  const divider = widths.map((w: number) => "─".repeat(w)).join("─┼─")

  const lines: StyledText[] = [
    t`${bg("#334155")(fg("#f8fafc")(bold(headerLine)))}`,
    t`${fg("#64748b")(divider)}`,
  ]

  if (rows.length === 0) {
    lines.push(t`${fg("#64748b")(truncate(emptyMessage, Math.max(12, maxWidth)))}`)
    return joinStyledLines(lines)
  }

  lines.push(
    ...rows.map((row, i) => {
      const line = rowToLine(row)
      return i % 2 === 0 ? t`${fg("#cbd5e1")(line)}` : t`${bg("#111827")(fg("#cbd5e1")(line))}`
    }),
  )

  return joinStyledLines(lines)
}

export function formatMenu(options: MenuOption[], selected: number, maxWidth = 80, maxVisible = 0): StyledText {
  if (options.length === 0) {
    return t`${fg("#94a3b8")("(пусто)")}`
  }

  const longestLabel = options.reduce((max, option) => Math.max(max, option.label.length), 0)
  const labelWidth = Math.max(18, Math.min(longestLabel + 2, 28))
  const hintWidth = Math.max(20, maxWidth - labelWidth - 8)

  // Determine visible window
  const limit = maxVisible > 0 ? maxVisible : options.length
  let start = 0
  if (options.length > limit) {
    start = Math.max(0, Math.min(selected - Math.floor(limit / 2), options.length - limit))
  }
  const end = Math.min(start + limit, options.length)

  const lines: StyledText[] = []

  if (start > 0) {
    lines.push(t`${fg("#64748b")(`  ▲ ещё ${start}`)}`)
  }

  for (let i = start; i < end; i++) {
    const opt = options[i]
    const num = i < 9 ? `${i + 1}.` : "• "
    const label = pad(opt.label, labelWidth)
    const hint = opt.hint ? `  ${truncate(opt.hint, hintWidth)}` : ""
    const activeBg = opt.destructive ? "#7f1d1d" : "#2563eb"
    const activeFg = opt.destructive ? "#fee2e2" : "#eff6ff"
    const inline = `${label}${hint}`

    if (i === selected) {
      lines.push(t`${bg(activeBg)(fg(activeFg)(bold(` ${num} ${inline} `)))}`)
    } else if (opt.destructive) {
      lines.push(t`${fg("#64748b")(` ${num}`)} ${fg("#f87171")(label)}${fg("#64748b")(hint)}`)
    } else {
      lines.push(t`${fg("#64748b")(` ${num}`)} ${fg("#cbd5e1")(label)}${fg("#64748b")(hint)}`)
    }
  }

  if (end < options.length) {
    lines.push(t`${fg("#64748b")(`  ▼ ещё ${options.length - end}`)}`)
  }

  return joinStyledLines(lines)
}

export function formatDashboard(data: DashboardData, maxWidth = 72): StyledText {
  const lines: StyledText[] = []

  const adminHealth = data.admins_total === 0
    ? "нужен первый админ"
    : `${data.admins_ready}/${data.admins_total} готовы`
  const adminHealthColor = data.admins_ready === data.admins_total ? "#4ade80" : "#fbbf24"

  lines.push(
    t`${fg("#94a3b8")("Админы  ")}${fg("#f8fafc")(bold(pad(String(data.admins_total), 4)))}${fg(adminHealthColor)(truncate(adminHealth, Math.max(16, maxWidth - 22)))}`,
  )

  const detailParts: string[] = []
  if (data.workers_ready > 0) detailParts.push(`${data.workers_ready} готовы`)
  if (data.workers_registered > 0) detailParts.push(`${data.workers_registered} готово`)
  if (data.workers_invited > 0) detailParts.push(`${data.workers_invited} приглашено`)
  if (data.workers_created > 0) detailParts.push(`${data.workers_created} создано`)
  if (data.workers_with_password > 0) detailParts.push(`${data.workers_with_password} с паролем`)

  const detail = detailParts.length > 0 ? detailParts.join(" / ") : ""

  if (detail) {
    lines.push(
      t`${fg("#94a3b8")("Слоты   ")}${fg("#f8fafc")(bold(pad(String(data.workers_total), 4)))}${fg("#94a3b8")(truncate(detail, Math.max(16, maxWidth - 22)))}`,
    )
  } else {
    lines.push(t`${fg("#94a3b8")("Слоты   ")}${fg("#f8fafc")(bold(String(data.workers_total)))}`)
  }

  if (data.admins_total === 0) {
    lines.push(t`${fg("#fca5a5")("Нужно добавить первого администратора.")}`)
  } else if (data.admins_ready < data.admins_total) {
    lines.push(t`${fg("#fbbf24")("Не все админы готовы: проверьте токен и браузерный профиль.")}`)
  } else if (data.workers_total === 0) {
    lines.push(t`${fg("#93c5fd")("Система готова к созданию первых слотов.")}`)
  } else {
    lines.push(t`${fg("#4ade80")("Операционный контур выглядит готовым к работе.")}`)
  }

  return joinStyledLines(lines)
}

export function joinStyledLines(lines: StyledText[]): StyledText {
  const chunks: StyledText["chunks"] = []
  for (let i = 0; i < lines.length; i++) {
    chunks.push(...lines[i].chunks)
    if (i < lines.length - 1) chunks.push(...stringToStyledText("\n").chunks)
  }
  return new StyledText(chunks)
}
