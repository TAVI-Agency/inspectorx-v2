/**
 * Настройки под реальным залогиненным НЕ-подписчиком → вкладка
 * «Уведомления», где живёт пейволл-CTA календаря дедлайнов.
 * Юзер — одноразовый тестовый аккаунт локального Supabase (создан service
 * role, profiles.is_subscribed = false по умолчанию, см. task-37).
 */
export default async function steps(page) {
  const base = new URL(page.url()).origin
  await page.goto(`${base}/login`)
  await page.fill('input[type="email"]', 'ix.calendar.screenshot@example.com')
  await page.fill('input[type="password"]', 'Screenshot1234!')
  await page.click('button[type="submit"]')
  await page.waitForURL('**/products', { timeout: 15000 })
  await page.goto(`${base}/settings`)
  await page.getByRole('button', { name: 'Уведомления', exact: true }).click()
  await page.waitForTimeout(500)
}
