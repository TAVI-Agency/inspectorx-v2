/**
 * Живая проверка залогиненных сценариев на локальном стеке:
 * 1) /settings: смена телефона → «Сохранено» → значение переживает перезагрузку;
 * 2) /questions: отправка вопроса → карточка со статусом «принят».
 * Требует dev-сервер (localhost:5173) + локальный Supabase с lawyer.demo.
 */
import { chromium } from 'playwright'

const BASE = process.env.SHOT_BASE ?? 'http://localhost:5173'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const errors = []
page.on('console', (m) => m.type() === 'error' && errors.push(m.text()))
page.on('pageerror', (e) => errors.push('PAGEERROR ' + e.message))

// Логин
await page.goto(BASE + '/login', { waitUntil: 'networkidle' })
await page.fill('input[type="email"]', 'lawyer.demo@inspectorx.uz')
await page.fill('input[type="password"]', 'Demo1234!')
await page.click('button[type="submit"]')
await page.waitForURL('**/products', { timeout: 15000 })
console.log('OK: логин, редирект на /products')

// Настройки: телефон
const newPhone = '+998 90 000 77 55'
await page.goto(BASE + '/settings', { waitUntil: 'networkidle' })
const phoneInput = page.locator('input[placeholder="+998 … или @username"]')
await phoneInput.fill(newPhone)
await page.getByRole('button', { name: 'Сохранить' }).click()
await page.waitForSelector('text=Сохранено', { timeout: 10000 })
console.log('OK: настройки — «Сохранено» показано')
await page.reload({ waitUntil: 'networkidle' })
await page.waitForTimeout(1500)
const persisted = await phoneInput.inputValue()
console.log(
  persisted === newPhone
    ? 'OK: телефон пережил перезагрузку — сохранён в profiles'
    : `FAIL: после перезагрузки телефон «${persisted}», ожидали «${newPhone}»`,
)
await page.screenshot({ path: 'shots/live-settings-saved.png' })

// Вопросы: отправка
const qText = 'E2E-проверка: нужен ли сертификат на пробную партию? (можно удалить)'
await page.goto(BASE + '/questions', { waitUntil: 'networkidle' })
await page.fill('textarea', qText)
await page.getByRole('button', { name: 'Спросить' }).click()
await page.waitForSelector('text=Вопрос принят', { timeout: 10000 })
await page.waitForSelector(`text=${qText}`, { timeout: 10000 })
console.log('OK: вопрос отправлен и появился в истории')
const chip = await page.locator('text=принят').first().isVisible()
console.log(chip ? 'OK: статус «принят» виден' : 'FAIL: нет чипа статуса')
await page.screenshot({ path: 'shots/live-question-sent.png' })

await browser.close()
if (errors.length) {
  console.log('CONSOLE ERRORS:')
  errors.forEach((e) => console.log(' ', e))
  process.exitCode = 2
} else {
  console.log('OK: no console errors')
}
