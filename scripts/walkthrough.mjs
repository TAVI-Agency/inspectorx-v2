/**
 * Сквозной путь: лендинг → поиск → товар → карточка → пейволл → тариф → заявка.
 * Скриншоты каждого шага в shots/walk-*.png, консольные ошибки — в stdout.
 */
import { chromium } from 'playwright'
import { mkdirSync } from 'node:fs'

const BASE = process.env.SHOT_BASE ?? 'http://localhost:5173'
mkdirSync('shots', { recursive: true })

const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const errors = []
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
page.on('pageerror', (e) => errors.push('PAGEERROR ' + e.message))

async function shot(name) {
  await page.waitForTimeout(350)
  await page.screenshot({ path: `shots/walk-${name}.png` })
  console.log('step ok:', name)
}

// 1. Лендинг → поиск
await page.goto(BASE + '/', { waitUntil: 'networkidle' })
const input = page.getByRole('combobox')
await input.click()
await input.fill('iqos')
await page.waitForSelector('[role="option"]', { timeout: 10000 })
await shot('1-search')

// 2. Выбор товара → страница товара
await page.locator('[role="option"] button').first().click()
await page.waitForSelector('h1', { timeout: 15000 })
await page.waitForSelector('button[aria-expanded]', { timeout: 15000 })
await shot('2-product')

// 3. Раскрытие карточки → пейволл
await page.locator('button[aria-expanded]').first().click()
await page.waitForTimeout(800)
await shot('3-card-paywall')

// 4. CTA «Открыть доступ» → тариф
await page.getByRole('link', { name: 'Открыть доступ' }).first().click()
await page.waitForURL('**/pricing')
await shot('4-pricing')

// 5. Заявка
await page.locator('#req-name').fill('ТЕСТ витрины (можно удалить)')
await page.locator('#req-contact').fill('@inspectorx_walkthrough_test')
await page.locator('#req-company').fill('E2E-тест сессии стройки')
await page.getByRole('button', { name: 'Отправить заявку' }).click()
await page.waitForSelector('text=Заявка принята', { timeout: 10000 }).catch(() => {})
await page.waitForTimeout(600)
await shot('5-thanks')

const thanks = await page.textContent('body')
console.log(
  thanks.includes('Спасибо') ? 'FORM OK: заявка отправлена' : 'FORM FAIL: нет экрана «Спасибо»',
)

await browser.close()
if (errors.length) {
  console.log('CONSOLE ERRORS:')
  errors.forEach((e) => console.log(' ', e))
  process.exitCode = 2
} else {
  console.log('OK: no console errors on full path')
}
