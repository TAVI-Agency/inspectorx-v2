/** Открыть матрицу сравнения стран на карточке товара (Задача 32) */
export default async function steps(page) {
  await page.getByRole('button', { name: 'Сравнить страны' }).click()
  await page.waitForSelector('table', { timeout: 15000 })
  await page.waitForTimeout(500)
}
