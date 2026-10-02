/**
 * Цена тарифа «Ранний доступ».
 * ВНИМАНИЕ: цена не утверждена (открытый вопрос №1 в docs/SESSION_SUMMARY) —
 * поменять здесь, когда решите с дядей.
 */
export const PRICE = {
  amount: 490_000,
  currency: 'сум',
  formatted: '490 000 сум',
} as const

/**
 * Реквизиты компании для страницы «Контакты» и юридических документов.
 * ВНИМАНИЕ: legalName/inn/address пустые до утверждения — заполнить здесь,
 * когда решите с юристом.
 */
export const COMPANY = {
  legalName: '',
  inn: '',
  address: '',
  email: 'hello@inspectorx.uz',
  telegram: '@inspectorx_uz',
} as const

export const companyRequisitesFilled = () =>
  Boolean(COMPANY.legalName && COMPANY.inn && COMPANY.address)
