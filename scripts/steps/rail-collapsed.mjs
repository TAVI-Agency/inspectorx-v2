/** Свернуть рейл перед снимком (только десктоп: на 375 рейла нет) */
export default async function steps(page, { width }) {
  if (width < 1024) return
  await page.click('[aria-label="Свернуть меню"]')
  await page.waitForTimeout(400)
}
