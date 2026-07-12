/**
 * Перекрёстные ссылки товар ↔ услуга — уникальная фишка InspectorX:
 * паспорт товара «лекарство» и паспорт услуги «аптека» знают друг о друге.
 *
 * Связки задаются константами (id детерминированы сидом
 * scripts/generate_services_seed.mjs). Когда связок станет больше —
 * переедет в таблицу БД.
 */
import { PARACETAMOL_PRODUCT_ID } from './mock/fixtures'
import { ru } from '@/i18n/ru'

/** id услуги «Розничная аптека» (uuid('inspectorx-svc:service:apteka-4773')) */
export const PHARMACY_SERVICE_ID = '47d1ce01-8c19-1ba7-7e5f-8b4681a68a29'
/** id услуги «Кафе» (uuid('inspectorx-svc:service:cafe-5610')) */
export const CAFE_SERVICE_ID = '87e23679-7f63-5ca9-eaa8-d7e940940361'

/** Группа 30 ТН ВЭД — фармацевтическая продукция */
const MEDICINE_HS_PREFIXES = ['3003', '3004']
/** Группа 22 ТН ВЭД — напитки: вода, пиво, вино и др. (их продаёт кафе) */
const BEVERAGE_HS_PREFIXES = ['22']

export interface CrossLink {
  /** Куда ведём */
  to: string
  /** Название целевой сущности для подписи */
  targetName: string
  /** Заголовок и подпись карточки-ссылки — у каждой связки свой сюжет */
  title: string
  text: string
}

/** На паспорте товара: «Открываете аптеку/кафе?» → паспорт услуги */
export function serviceLinkForProduct(hsCode: string): CrossLink | null {
  if (MEDICINE_HS_PREFIXES.some((p) => hsCode.startsWith(p)))
    return {
      to: `/service/${PHARMACY_SERVICE_ID}`,
      targetName: 'Розничная аптека',
      title: ru.service.crossToServiceTitle,
      text: ru.service.crossToServiceText,
    }
  if (BEVERAGE_HS_PREFIXES.some((p) => hsCode.startsWith(p)))
    return {
      to: `/service/${CAFE_SERVICE_ID}`,
      targetName: 'Кафе (общественное питание)',
      title: ru.service.crossToCafeTitle,
      text: ru.service.crossToCafeText,
    }
  return null
}

/** На паспорте аптеки: «Требования к товару: лекарства» → паспорт товара.
 *  У кафе товарной пары пока нет: паспорта напитков ещё не наполнены. */
export function productLinkForService(serviceId: string): CrossLink | null {
  if (serviceId !== PHARMACY_SERVICE_ID) return null
  return {
    to: `/product/${PARACETAMOL_PRODUCT_ID}`,
    targetName: 'Лекарства (на примере парацетамола)',
    title: ru.service.crossTitle('Лекарства (на примере парацетамола)'),
    text: ru.service.crossToProductText,
  }
}

/**
 * Этапы «раздел в работе»: в этапе есть неопубликованные карточки
 * (draft скрыт RLS-ом, фронт о нём знать не может — фиксируем тут).
 * Аптека: этап «Помещение и запуск» — СЭС-заключение на юрпроверке.
 * Кафе: «Текущая работа» — ночной режим; «Прекращение» — отзыв
 * алкогольного уведомления (оба на юрпроверке).
 */
const IN_PROGRESS_STAGES: Record<string, string[]> = {
  [PHARMACY_SERVICE_ID]: ['a1b90d21-5c01-4d10-9a01-000000000002'],
  [CAFE_SERVICE_ID]: [
    'a1b90d21-5c01-4d10-9a01-000000000003',
    'a1b90d21-5c01-4d10-9a01-000000000006',
  ],
}

export function inProgressStageIds(serviceId: string): Set<string> {
  return new Set(IN_PROGRESS_STAGES[serviceId] ?? [])
}
