/**
 * Войти демо-юристом и дождаться страницы «Мои заключения».
 * Требует локальный Supabase c засеянным verified-юристом
 * (email/пароль ниже) — см. E2E-протокол в handoff.
 */
export default async function steps(page) {
  const base = new URL(page.url()).origin
  const badge = page.locator('text=Верифицированный эксперт')
  if ((await badge.count()) === 0) {
    await page.goto(`${base}/login`)
    await page.fill('input[type="email"]', 'lawyer.demo@inspectorx.uz')
    await page.fill('input[type="password"]', 'Demo1234!')
    await page.click('button[type="submit"]')
    await page.waitForURL('**/products', { timeout: 15000 })
    await page.goto(`${base}/lawyer/reviews`)
  }
  await page.waitForSelector('text=Верифицированный эксперт', { timeout: 15000 })
  await page.waitForTimeout(800)
}
