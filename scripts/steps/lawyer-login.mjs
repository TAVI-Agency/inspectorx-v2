/**
 * Войти демо-юристом и дождаться дешборда юриста в кабинете.
 * Требует локальный Supabase c засеянным verified-юристом
 * (email/пароль ниже) — см. E2E-протокол в handoff.
 */
export default async function steps(page) {
  const base = new URL(page.url()).origin
  const dashboard = page.locator('text=Кабинет юриста')
  if ((await dashboard.count()) === 0) {
    await page.goto(`${base}/login`)
    await page.fill('input[type="email"]', 'lawyer.demo@inspectorx.uz')
    await page.fill('input[type="password"]', 'Demo1234!')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/cabinet', { timeout: 15000 })
  }
  await page.waitForSelector('text=Верифицированный эксперт', { timeout: 15000 })
  await page.waitForTimeout(800)
}
