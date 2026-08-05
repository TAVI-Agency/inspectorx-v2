/** Настройки: переключиться на вкладку «Уведомления» (там живёт календарь) */
export default async function steps(page) {
  await page.getByRole('button', { name: 'Уведомления', exact: true }).click()
  await page.waitForTimeout(300)
}
