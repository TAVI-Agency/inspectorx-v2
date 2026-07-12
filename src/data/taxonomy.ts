/**
 * Единый справочник таксономии требований — используют оба фронта (A и Б).
 * Модель: требование = операция × (транспорт?) × этап. Подтверждена
 * нац. порталом uztradeinfo.uz и Киотской конвенцией ВТамО (см. docs/TAXONOMY.md).
 */
import type { Operation, RequirementRow, StageInfo, TransportType } from './types'

export interface OperationMeta {
  key: Operation
  /** Короткая подпись вкладки */
  label: string
  /** Полная формулировка (заголовок раздела / подсказка) */
  full: string
  group: 'internal' | 'external'
  /** Трансграничная процедура — может иметь переключатель транспорта */
  isProcedure: boolean
}

export const OPERATIONS: OperationMeta[] = [
  { key: 'product', label: 'Продукт', full: 'Требования к продукту', group: 'internal', isProcedure: false },
  { key: 'realization', label: 'Реализация', full: 'Требования к реализации', group: 'internal', isProcedure: false },
  { key: 'import', label: 'Импорт', full: 'Процедура импорта', group: 'external', isProcedure: true },
  { key: 'export', label: 'Экспорт', full: 'Процедура экспорта', group: 'external', isProcedure: true },
  { key: 'transit', label: 'Транзит', full: 'Процедура транзита', group: 'external', isProcedure: true },
  { key: 're_export', label: 'Реэкспорт', full: 'Процедура реэкспорта', group: 'external', isProcedure: true },
  { key: 're_import', label: 'Реимпорт', full: 'Процедура реимпорта', group: 'external', isProcedure: true },
]

export const OPERATION_GROUPS = [
  { key: 'internal' as const, title: 'Требования к товару' },
  { key: 'external' as const, title: 'Внешнеэкономические процедуры' },
]

const OPERATION_META = new Map(OPERATIONS.map((o) => [o.key, o]))
export function operationMeta(op: Operation): OperationMeta {
  return OPERATION_META.get(op) ?? { key: op, label: op, full: op, group: 'external', isProcedure: true }
}
const OPERATION_ORDER = new Map(OPERATIONS.map((o, i) => [o.key, i]))

export const TRANSPORTS: { key: TransportType; label: string }[] = [
  { key: 'avto', label: 'Авто' },
  { key: 'train', label: 'Поезд' },
  { key: 'avia', label: 'Самолёт' },
]
const TRANSPORT_LABEL = new Map(TRANSPORTS.map((t) => [t.key, t.label]))
export function transportLabel(t: TransportType): string {
  return TRANSPORT_LABEL.get(t) ?? t
}

// ── Дерево операций из фактических строк ─────────────────────────────

export interface OperationNode {
  meta: OperationMeta
  count: number
  /** Виды транспорта, реально встречающиеся в этой операции (по порядку) */
  transports: TransportType[]
}

/** Операции, у которых есть требования, — в каноническом порядке, с транспортом. */
export function buildOperationNodes(rows: RequirementRow[]): OperationNode[] {
  const byOp = new Map<Operation, { count: number; transports: Set<TransportType> }>()
  for (const r of rows) {
    let node = byOp.get(r.operation)
    if (!node) {
      node = { count: 0, transports: new Set() }
      byOp.set(r.operation, node)
    }
    node.count += 1
    if (r.transport) node.transports.add(r.transport)
  }
  return [...byOp.entries()]
    .map(([op, v]) => ({
      meta: operationMeta(op),
      count: v.count,
      transports: TRANSPORTS.map((t) => t.key).filter((t) => v.transports.has(t)),
    }))
    .sort((a, b) => (OPERATION_ORDER.get(a.meta.key) ?? 99) - (OPERATION_ORDER.get(b.meta.key) ?? 99))
}

/** Строки выбранной операции (и, если задан, вида транспорта). */
export function filterRows(
  rows: RequirementRow[],
  operation: Operation | null,
  transport: TransportType | null,
): RequirementRow[] {
  return rows.filter(
    (r) =>
      (operation === null || r.operation === operation) &&
      (transport === null || r.transport === transport),
  )
}

// ── Род требования (тег по UNCTAD NTM) ─────────────────────────────
// Свёртка 16 глав NTM в 8 понятных категорий. Пока выводится эвристикой из
// названия этапа/требования (display-only); при персисте — колонка
// requirements.requirement_category (см. миграцию + docs/TAXONOMY.md).

export type RequirementCategory =
  | 'sps'
  | 'tbt'
  | 'marking'
  | 'licensing'
  | 'fiscal'
  | 'currency'
  | 'customs'
  | 'origin'

export const CATEGORY_LABEL: Record<RequirementCategory, string> = {
  sps: 'Санитария',
  tbt: 'Техрегламент',
  marking: 'Маркировка',
  licensing: 'Лицензия',
  fiscal: 'Налоги',
  currency: 'Валюта',
  customs: 'Таможня',
  origin: 'Происхождение',
}

export const CATEGORY_ORDER: RequirementCategory[] = [
  'tbt', 'sps', 'marking', 'licensing', 'fiscal', 'currency', 'customs', 'origin',
]

/** Категория из названия этапа + заголовка (порядок правил важен). */
export function categoryOf(row: { stageName: string; title: string }): RequirementCategory {
  const s = `${row.stageName} ${row.title}`.toLowerCase()
  if (/санитар|ветеринар|фитосанитар|карантин|эпидемиолог/.test(s)) return 'sps'
  if (/происхожд|ст-1/.test(s)) return 'origin'
  if (/маркиров|этикет|упаковк|защита прав потребител/.test(s)) return 'marking'
  if (/лиценз|разрешени|запрет|квот/.test(s)) return 'licensing'
  if (/акциз|налог|пошлин|ценообраз|тариф|мрц|ставк/.test(s)) return 'fiscal'
  if (/валют|контракт|взаиморасч|оплат|платёж|платеж|финанс/.test(s)) return 'currency'
  if (/сертификац|технич|деклараци|соответстви|качеств|безопасн|производств|эколог|энергоэфф/.test(s))
    return 'tbt'
  return 'customs'
}

/** Этапы (для чипов) по произвольному подмножеству строк — со счётчиками. */
export function stagesOf(rows: RequirementRow[]): StageInfo[] {
  const map = new Map<string, StageInfo>()
  for (const r of rows) {
    const s = map.get(r.stageId)
    if (s) {
      s.count += 1
      if (r.unread) s.unreadCount += 1
    } else {
      map.set(r.stageId, {
        id: r.stageId,
        name: r.stageName,
        sortOrder: r.stageSortOrder,
        count: 1,
        unreadCount: r.unread ? 1 : 0,
      })
    }
  }
  return [...map.values()].sort((a, b) => a.sortOrder - b.sortOrder)
}
