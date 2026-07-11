/** Открыть подсказки поиска на лендинге */
export default async function steps(page) {
  const input = page.getByRole('combobox')
  await input.click()
  await input.fill('моло')
  await page.waitForTimeout(700)
}
