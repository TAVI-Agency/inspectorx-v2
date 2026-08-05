/**
 * Раскрыть на странице сигарет требование НЕ-запрет — у demoDetailFor
 * (мок-подписчик) такая строка получает заполненные шаблоны и инструкцию
 * юриста, но courtCases = null (кейсы правдоподобны только для запретов) —
 * одна карточка показывает и заполненные блоки, и «Данных пока нет»
 * (Задача 35, скриншот). Раскрытие — аккордеон (один элемент за раз),
 * поэтому берём первую подходящую строку, а не пытаемся раскрыть две.
 */
export default async function steps(page) {
  const selector = 'button[aria-expanded]:not([aria-haspopup])'
  await page.waitForSelector(selector, { timeout: 15000 })
  const rows = page.locator(selector)
  const count = await rows.count()
  for (let i = 0; i < count; i++) {
    const text = await rows.nth(i).innerText()
    if (!text.includes('запрет')) {
      await rows.nth(i).click()
      break
    }
  }
  await page.waitForTimeout(600)
}
