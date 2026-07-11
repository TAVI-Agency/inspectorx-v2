/** Раскрыть первую строку требования на странице товара */
export default async function steps(page) {
  await page.waitForSelector('[aria-expanded]', { timeout: 15000 })
  const rows = page.locator('button[aria-expanded]')
  await rows.first().click()
  await page.waitForTimeout(900)
}
