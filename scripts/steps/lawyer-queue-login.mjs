/**
 * Войти демо-юристом и вернуться на «Очередь проверки».
 * Требует локальный Supabase c засеянным verified-юристом
 * (lawyer.demo@inspectorx.uz / Demo1234!).
 */
import lawyerLogin from './lawyer-login.mjs'

export default async function steps(page, ctx) {
  const base = new URL(page.url()).origin
  await lawyerLogin(page, ctx)
  await page.goto(`${base}/lawyer/queue`)
  await page.waitForSelector('text=Очередь проверки', { timeout: 15000 })
  await page.waitForTimeout(800)
}
