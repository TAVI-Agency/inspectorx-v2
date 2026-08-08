/**
 * Войти модератором и открыть «Модерация заключений».
 * Требует локальный Supabase с пользователем, у которого стоит
 * `profiles.is_moderator = true` (сид — в отчёте moderation-report.md).
 */
export default async function steps(page) {
  const base = new URL(page.url()).origin
  await page.goto(`${base}/login`)
  await page.fill('input[type="email"]', 'moderator@demo.local')
  await page.fill('input[type="password"]', 'wave1-Passw0rd')
  await page.click('button[type="submit"]')
  await page.waitForURL('**/products', { timeout: 15000 })
  await page.goto(`${base}/moderation`)
  await page.waitForSelector('text=Заключения на модерации', { timeout: 15000 })
  await page.waitForTimeout(1000)
}
