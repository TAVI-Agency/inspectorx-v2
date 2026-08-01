/** Открыть центр уведомлений (десктоп — шапка, мобайл — топ-бар) */
export default async function steps(page) {
  await page.locator('[aria-label^="Уведомления"]:visible').first().click()
  await page.waitForTimeout(500)
}
