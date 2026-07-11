/**
 * Скриншоты для цикла качества:
 *   node scripts/shot.mjs <path> <name> [steps.mjs]
 * Пишет shots/<name>-{light,dark}-{1440,375}.png (полная высота)
 * и выводит консольные ошибки страницы в stdout.
 * steps.mjs (опционально) экспортирует default: async (page, ctx) => {} —
 * выполняется после загрузки, до снимка. ctx = { theme, width }.
 */
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'
import { pathToFileURL } from 'node:url'

const BASE = process.env.SHOT_BASE ?? 'http://localhost:5173'
const [route = '/', name = 'shot', stepsFile] = process.argv.slice(2)

const steps = stepsFile
  ? (await import(pathToFileURL(stepsFile).href)).default
  : null

mkdirSync('shots', { recursive: true })

const browser = await chromium.launch()
const errors = []

for (const theme of ['light', 'dark']) {
  for (const width of [1440, 375]) {
    const page = await browser.newPage({
      viewport: { width, height: width === 375 ? 720 : 900 },
      deviceScaleFactor: 1,
    })
    page.on('console', (msg) => {
      if (msg.type() === 'error')
        errors.push(`[${theme}/${width}] ${msg.text()}`)
    })
    page.on('pageerror', (err) =>
      errors.push(`[${theme}/${width}] PAGEERROR ${err.message}`),
    )
    await page.addInitScript((t) => localStorage.setItem('ix-theme', t), theme)
    await page.goto(`${BASE}${route}`, { waitUntil: 'networkidle' })
    if (steps) await steps(page, { theme, width })
    // Прокрутить страницу, чтобы сработали scroll-fade появления
    await page.evaluate(async () => {
      const step = window.innerHeight / 2
      for (let y = 0; y <= document.body.scrollHeight; y += step) {
        window.scrollTo(0, y)
        await new Promise((r) => setTimeout(r, 60))
      }
      window.scrollTo(0, 0)
    })
    await page.waitForTimeout(700)
    await page.screenshot({
      path: `shots/${name}-${theme}-${width}.png`,
      fullPage: true,
    })
    // Горизонтальный скролл на мобильном — дефект
    if (width === 375) {
      const overflow = await page.evaluate(
        () =>
          document.documentElement.scrollWidth >
          document.documentElement.clientWidth,
      )
      if (overflow) errors.push(`[${theme}/${width}] HORIZONTAL OVERFLOW`)
    }
    await page.close()
  }
}

await browser.close()

if (errors.length) {
  console.log('CONSOLE ERRORS:')
  for (const e of errors) console.log('  ' + e)
  process.exitCode = 2
} else {
  console.log('OK: no console errors')
}
