/** Табы стран на карточке товара: переключиться на превью-таб «Казахстан» */
export default async function steps(page) {
  await page.waitForSelector('[role="tab"]', { timeout: 15000 })
  await page.getByRole('tab', { name: /Казахстан/ }).click()
  await page.waitForTimeout(600)
}
