/**
 * Перекрёстные ссылки товар ↔ услуга — уникальная фишка InspectorX:
 * паспорт товара «лекарство» и паспорт услуги «аптека» знают друг о друге.
 *
 * Пока связка одна и задаётся константами (id детерминированы сидом
 * scripts/generate_services_seed.mjs). Когда связок станет больше —
 * переедет в таблицу БД.
 */
import { PARACETAMOL_PRODUCT_ID } from './mock/fixtures'

/** id услуги «Розничная аптека» (uuid('inspectorx-svc:service:apteka-4773')) */
export const PHARMACY_SERVICE_ID = '47d1ce01-8c19-1ba7-7e5f-8b4681a68a29'

/** Группа 30 ТН ВЭД — фармацевтическая продукция */
const MEDICINE_HS_PREFIXES = ['3003', '3004']

export interface CrossLink {
  /** Куда ведём */
  to: string
  /** Название целевой сущности для подписи */
  targetName: string
}

/** На паспорте товара-лекарства: «Открываете аптеку?» → паспорт услуги */
export function serviceLinkForProduct(hsCode: string): CrossLink | null {
  if (!MEDICINE_HS_PREFIXES.some((p) => hsCode.startsWith(p))) return null
  return { to: `/service/${PHARMACY_SERVICE_ID}`, targetName: 'Розничная аптека' }
}

/** На паспорте аптеки: «Требования к товару: лекарства» → паспорт товара */
export function productLinkForService(serviceId: string): CrossLink | null {
  if (serviceId !== PHARMACY_SERVICE_ID) return null
  return { to: `/product/${PARACETAMOL_PRODUCT_ID}`, targetName: 'Лекарства (на примере парацетамола)' }
}

/**
 * Этапы «раздел в работе»: в этапе есть неопубликованные карточки
 * (draft скрыт RLS-ом, фронт о нём знать не может — фиксируем тут).
 * Аптека: этап «Помещение и запуск» — СЭС-заключение на юрпроверке.
 */
const IN_PROGRESS_STAGES: Record<string, string[]> = {
  [PHARMACY_SERVICE_ID]: ['a1b90d21-5c01-4d10-9a01-000000000002'],
}

export function inProgressStageIds(serviceId: string): Set<string> {
  return new Set(IN_PROGRESS_STAGES[serviceId] ?? [])
}
