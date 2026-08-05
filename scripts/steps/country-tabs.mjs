/**
 * Табы стран на карточке товара: переключиться на превью-таб «Казахстан».
 * Сразу после клика (до общего waitForTimeout ниже) снимаем переходный кадр —
 * на нём должен быть виден индикатор «Загружаем требования…», а не список
 * прежней страны без пометки (placeholderData на время фетча).
 */
export default async function steps(page, ctx) {
  await page.waitForSelector('[role="tab"]', { timeout: 15000 })
  await page.getByRole('tab', { name: /Казахстан/ }).click()
  await page.screenshot({
    path: `shots/country-tabs-transition-${ctx.theme}-${ctx.width}.png`,
    fullPage: true,
  })
  await page.waitForTimeout(600)
}
