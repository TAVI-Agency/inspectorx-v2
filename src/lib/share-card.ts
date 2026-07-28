/**
 * Share-карточка эксперта: 1200×630 PNG для Telegram/соцсетей.
 * Рисуем прямо на canvas — без DOM-скриншотов и новых зависимостей.
 * Тема фиксированная (тёмный кокпит): картинка не зависит от темы интерфейса.
 */
import { ru } from '@/i18n/ru'

export interface ShareCardData {
  name: string
  credentials?: string
  reviewed: number
  helpful: number
  rank?: { place: number; total: number }
}

export const SHARE_CARD_W = 1200
export const SHARE_CARD_H = 630

// Палитра тёмного кокпита (src/index.css .dark)
const INK = '#12110f'
const CARD = '#1c1a17'
const FG = '#e8e2da'
const MUTED = '#a8a49c'
const PRIMARY = '#e05a3a'
const POSITIVE = '#5dcaa5'
const BRASS = '#d8ab54'
const BORDER = '#2c2924'

const DISPLAY = "'Unbounded Variable', 'Golos Text Variable', system-ui, sans-serif"
const SANS = "'Inter Variable', 'Segoe UI', system-ui, sans-serif"
const MONO = "'JetBrains Mono Variable', ui-monospace, monospace"

function roundedRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}

/** Перенос строки по ширине; максимум 2 строки, дальше — многоточие */
function wrapText(
  ctx: CanvasRenderingContext2D,
  text: string,
  maxWidth: number,
  maxLines: number,
): string[] {
  const words = text.split(/\s+/)
  const lines: string[] = []
  let line = ''
  for (const word of words) {
    const probe = line ? `${line} ${word}` : word
    if (ctx.measureText(probe).width <= maxWidth || !line) {
      line = probe
    } else {
      lines.push(line)
      line = word
      if (lines.length === maxLines) break
    }
  }
  if (lines.length < maxLines && line) lines.push(line)
  if (lines.length === maxLines && line && lines[maxLines - 1] !== line) {
    let last = lines[maxLines - 1]
    while (last && ctx.measureText(`${last}…`).width > maxWidth) {
      last = last.slice(0, -1)
    }
    lines[maxLines - 1] = `${last}…`
  }
  return lines
}

export async function drawShareCard(
  canvas: HTMLCanvasElement,
  data: ShareCardData,
): Promise<void> {
  const t = ru.cabinet.lawyer.share
  canvas.width = SHARE_CARD_W
  canvas.height = SHARE_CARD_H
  const ctx = canvas.getContext('2d')
  if (!ctx) return

  // Шрифты должны быть загружены до отрисовки, иначе canvas возьмёт запасной
  await Promise.all([
    document.fonts.load(`600 64px ${DISPLAY}`),
    document.fonts.load(`500 30px ${SANS}`),
    document.fonts.load(`500 22px ${MONO}`),
  ]).catch(() => {})

  // Фон: чернильный + тёплое свечение от бренда
  ctx.fillStyle = INK
  ctx.fillRect(0, 0, SHARE_CARD_W, SHARE_CARD_H)
  const glow = ctx.createRadialGradient(180, -80, 0, 180, -80, 900)
  glow.addColorStop(0, 'rgba(224, 90, 58, 0.16)')
  glow.addColorStop(1, 'rgba(224, 90, 58, 0)')
  ctx.fillStyle = glow
  ctx.fillRect(0, 0, SHARE_CARD_W, SHARE_CARD_H)

  // Нить маршрута со станциями — фирменная метафора кокпита
  const threadX = 76
  const grad = ctx.createLinearGradient(0, 90, 0, 560)
  grad.addColorStop(0, 'rgba(224, 90, 58, 0.55)')
  grad.addColorStop(1, 'rgba(224, 90, 58, 0)')
  ctx.strokeStyle = grad
  ctx.lineWidth = 2
  ctx.beginPath()
  ctx.moveTo(threadX, 96)
  ctx.lineTo(threadX, 556)
  ctx.stroke()
  for (const [y, filled] of [
    [150, true],
    [300, true],
    [450, false],
  ] as const) {
    ctx.beginPath()
    ctx.arc(threadX, y, 7, 0, Math.PI * 2)
    ctx.fillStyle = filled ? PRIMARY : INK
    ctx.fill()
    ctx.strokeStyle = PRIMARY
    ctx.lineWidth = 2
    ctx.stroke()
  }

  // Рамка карточки
  roundedRect(ctx, 24, 24, SHARE_CARD_W - 48, SHARE_CARD_H - 48, 20)
  ctx.strokeStyle = BORDER
  ctx.lineWidth = 2
  ctx.stroke()

  const left = 140

  // Шапка: словомарка + печать эксперта справа
  ctx.textBaseline = 'alphabetic'
  ctx.fillStyle = FG
  ctx.font = `500 34px ${DISPLAY}`
  ctx.fillText('InspectorX', left, 110)
  ctx.fillStyle = MUTED
  ctx.font = `400 19px ${SANS}`
  ctx.fillText(t.imgTagline, left + 214, 110)

  // Латунная печать: двойное кольцо + галочка (мотив CSeal)
  const sealX = 1076
  const sealY = 96
  ctx.strokeStyle = BRASS
  ctx.lineWidth = 2.5
  ctx.beginPath()
  ctx.arc(sealX, sealY, 34, 0, Math.PI * 2)
  ctx.stroke()
  ctx.setLineDash([5, 5])
  ctx.beginPath()
  ctx.arc(sealX, sealY, 26, 0, Math.PI * 2)
  ctx.stroke()
  ctx.setLineDash([])
  ctx.lineWidth = 4
  ctx.lineCap = 'round'
  ctx.beginPath()
  ctx.moveTo(sealX - 11, sealY + 1)
  ctx.lineTo(sealX - 3, sealY + 9)
  ctx.lineTo(sealX + 12, sealY - 8)
  ctx.stroke()
  ctx.lineCap = 'butt'

  // Реквизит эксперта
  ctx.fillStyle = BRASS
  ctx.font = `500 20px ${MONO}`
  ctx.fillText(t.imgVerified.toUpperCase(), left, 196)

  // Имя и регалии
  ctx.fillStyle = FG
  ctx.font = `600 58px ${DISPLAY}`
  const nameLines = wrapText(ctx, data.name, 940, 1)
  ctx.fillText(nameLines[0] ?? data.name, left, 268)
  if (data.credentials) {
    ctx.fillStyle = MUTED
    ctx.font = `400 26px ${SANS}`
    const credLines = wrapText(ctx, data.credentials, 940, 2)
    credLines.forEach((line, i) => ctx.fillText(line, left, 312 + i * 36))
  }

  // Статистика: две панели с большими числами
  const panelY = 396
  const panelH = 128
  const panels: { value: string; label: string; color: string; x: number; w: number }[] = [
    {
      value: String(data.reviewed),
      label: t.imgReviewed,
      color: PRIMARY,
      x: left,
      w: 440,
    },
    {
      value: String(data.helpful),
      label: t.imgHelpful,
      color: POSITIVE,
      x: left + 464,
      w: 440,
    },
  ]
  for (const p of panels) {
    roundedRect(ctx, p.x, panelY, p.w, panelH, 14)
    ctx.fillStyle = CARD
    ctx.fill()
    ctx.strokeStyle = BORDER
    ctx.lineWidth = 1.5
    ctx.stroke()
    ctx.fillStyle = p.color
    ctx.font = `600 64px ${DISPLAY}`
    ctx.fillText(p.value, p.x + 28, panelY + 82)
    const valueW = ctx.measureText(p.value).width
    ctx.fillStyle = MUTED
    ctx.font = `400 21px ${SANS}`
    const labelLines = wrapText(ctx, p.label, p.w - valueW - 72, 2)
    labelLines.forEach((line, i) =>
      ctx.fillText(line, p.x + 28 + valueW + 20, panelY + 60 + i * 27),
    )
  }

  // Строка рейтинга
  if (data.rank) {
    ctx.fillStyle = BRASS
    ctx.font = `500 22px ${MONO}`
    ctx.fillText(t.imgRank(data.rank.place, data.rank.total), left, 570)
  }

  // Домен справа внизу
  ctx.fillStyle = PRIMARY
  ctx.font = `500 24px ${MONO}`
  const domainW = ctx.measureText(t.imgDomain).width
  ctx.fillText(t.imgDomain, SHARE_CARD_W - 64 - domainW, 570)
}

/** PNG-файл из canvas — для кнопки «Скачать» */
export function downloadCanvasPng(canvas: HTMLCanvasElement, filename: string): void {
  canvas.toBlob((blob) => {
    if (!blob) return
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }, 'image/png')
}
