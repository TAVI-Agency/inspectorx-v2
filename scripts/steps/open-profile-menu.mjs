/** Открыть меню профиля (десктоп — рейл, мобайл — таб) */
export default async function steps(page) {
  await page.locator('[aria-label="Меню профиля"]:visible').first().click()
  await page.waitForTimeout(500)
}
