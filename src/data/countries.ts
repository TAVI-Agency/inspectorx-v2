/**
 * Коды стран и жизненный цикл требования — общий алфавит для слоя данных.
 * Человекочитаемые названия стран — НЕ здесь, а в src/i18n/ru.ts (Задача 31):
 * этот модуль — только код/enum-уровень, без строк UI.
 */

/** ISO 3166-1 alpha-2. Порядок — порядок запуска стран (docs/MASTER_PLAN_BRIEF.md). */
export type CountryCode = 'UZ' | 'KZ' | 'AE'

export const COUNTRIES: readonly CountryCode[] = ['UZ', 'KZ', 'AE'] as const

/**
 * Вычисляемый статус требования (public.lifecycle_status(), view
 * requirements_with_status) — НЕ хранится текстом, считается на лету из
 * effective_from/transition_until/valid_to.
 */
export type LifecycleStatus =
  | 'upcoming'
  | 'in_force'
  | 'transitional'
  | 'expiring'
  | 'repealed'
