/**
 * Чистые функции отчёта `/checks/packaging/:inspectionId` (Задача 13, план §7):
 * разбор находок на четыре списка, человекочитаемые подписи `decided_by`,
 * стадий ожидания, тяжести и граней упаковки. Без сети и без React — легко
 * покрыть тестами, не поднимая ни компонент, ни Supabase.
 */
import { needsHumanFinding } from '@/data'
import { ru } from '@/i18n/ru'

const t = ru.packagingCheck

/**
 * Минимум, который нужен для разбора находки на список. Раньше здесь было
 * ещё поле `suspected` (подкласс `unreadable` от VLM, план §7 п.2 и
 * `docs/PHOTOCONTROL_PLAN_FIXLOG.md:20`) — но в схеме `photo_findings`
 * (`20260810100000_photo_runtime.sql`) такой колонки нет и не появилось, а
 * значит предикат по ней никогда ничего не отбирал. Его роль — «машина не
 * ручается за прочтение» — уже несёт реальная колонка `confidence_class`,
 * по ней и считаем (`needsHumanFinding`, `src/data/vision.ts`).
 */
export interface FindingLike {
  status: string
  decided_by?: string
  confidence_class?: string | null
}

export interface NotCheckableLike {
  class: string
}

export interface FindingLists<F extends FindingLike, N extends NotCheckableLike> {
  /** Список 1 — нарушения (`status === 'fail'`). */
  violations: F[]
  /**
   * Секция «Выполнено» — решённые пункты (`status === 'pass'`). Раньше эти
   * находки только считались в сводке «Проверено N из K», а карточек с
   * кропом-доказательством при 0 нарушениях не было ни одной, хотя движок их
   * генерирует (задача E, план фотоконтроля волны 2). Тот же предикат, что и
   * счётчик «Проверено» минус нарушения — см. тест согласованности рядом с
   * `splitFindings` в `report-utils.test.ts`.
   */
  passed: F[]
  /** Список 2 — досъёмка или человек (`needsHumanFinding`: `unreadable` либо `needs_human`). */
  needsHuman: F[]
  /** Список 3 — граница метода (`photo_not_checkable`, класс не «нет эталона»). */
  notCheckable: N[]
  /** Список 4 — правило есть, эталона нет (`class === 'нет эталона'`). */
  noGold: N[]
}

/**
 * Разбор находок и строк `photo_not_checkable` на списки §7 плюс секцию
 * «Выполнено» (задача E). Список 2 считается тем же предикатом, что и плитка
 * «Требует человека» наверху отчёта (`needsHumanFinding` в слое данных) —
 * числа под одной подписью на одном экране обязаны совпадать.
 */
export function splitFindings<F extends FindingLike, N extends NotCheckableLike>(
  findings: F[],
  notCheckable: N[],
): FindingLists<F, N> {
  return {
    violations: findings.filter((f) => f.status === 'fail'),
    passed: findings.filter((f) => f.status === 'pass'),
    needsHuman: findings.filter(needsHumanFinding),
    notCheckable: notCheckable.filter((n) => n.class !== 'нет эталона'),
    noGold: notCheckable.filter((n) => n.class === 'нет эталона'),
  }
}

/** `decided_by` словами, не кодом. Незнакомый код — не выдумываем слово, показываем как есть. */
export function decidedByLabel(code: string): string {
  return t.decidedBy[code] ?? code
}

/** Тяжесть находки словами. Незнакомый код — показываем как есть, не подменяем догадкой. */
export function severityLabel(code: string): string {
  return t.severity[code] ?? code
}

/**
 * Грань/зона упаковки словами. Словарь — `ru.packagingCheck.zones`
 * (Задача A, план фотоконтроля волны 2): и короткие коды
 * `photo_findings.surface` (`front`/`back`/…), и коды `photo_assets.face_name`
 * с экрана загрузки (`front_panel`/`back_panel`/…, `CPackagingUpload.tsx`), и
 * полный словарь `requirement_photo_checks.params.surface` из сидов
 * (`all_panels`, `any`, `pallet_side`, …) — контракт значения `surface` со
 * стороны воркера вне этого репозитория не задокументирован (см. Concerns
 * Задачи 11), а ложная подмена кода словом хуже, чем сырой код на экране:
 * незнакомый код по-прежнему показывается как есть.
 */
export function faceLabel(surface: string): string {
  return t.zones[surface] ?? surface
}

export interface ReasonGroup<T> {
  /** Текст причины, по которому схлопнули группу. */
  reason: string
  /** Сколько карточек с этим текстом попало в группу. */
  count: number
  /** Исходные элементы группы, в порядке появления. */
  items: T[]
}

/**
 * Схлопывает карточки с одинаковым текстом причины в одну строку со
 * счётчиком «× N» (Задача A, план фотоконтроля волны 2, п.2): владелец
 * увидел «простыню одинаковых причин» в списках «нужен человек/досъёмка» и
 * «границы метода» — эта функция общая для обоих списков. Порядок групп —
 * по убыванию `count`; при равенстве числа — порядок первого появления
 * причины во входном массиве (`Array.prototype.sort` стабилен в V8 с
 * ES2019). Разные тексты причины остаются разными группами.
 */
export function groupByReason<T>(items: T[], reasonOf: (item: T) => string): ReasonGroup<T>[] {
  const order: string[] = []
  const byReason = new Map<string, T[]>()
  for (const item of items) {
    const reason = reasonOf(item)
    const list = byReason.get(reason)
    if (list) list.push(item)
    else {
      byReason.set(reason, [item])
      order.push(reason)
    }
  }
  return order
    .map((reason) => {
      const list = byReason.get(reason) as T[]
      return { reason, count: list.length, items: list }
    })
    .sort((a, b) => b.count - a.count)
}

/**
 * Стадия ожидания словами. `prepare` расходится по источнику: разбор
 * макета — другой текст, чем подготовка кадров. Остальные стадии не зависят
 * от источника. Незнакомая стадия — сырой код, не пустая строка (план §7:
 * отсутствие данных ≠ норма).
 */
export function stageLabel(stage: string, sourceKind: 'photo' | 'master_pdf'): string {
  switch (stage) {
    case 'received':
      return t.stageReceived
    case 'prepare':
      return sourceKind === 'master_pdf' ? t.stagePrepareArtwork : t.stagePrepare
    case 'read':
      return t.stageRead
    case 'judge':
      return t.stageJudge
    case 'render':
      return t.stageRender
    default:
      return stage
  }
}

/** Причина отказа проверки словами; возвратные причины показывают отдельную приписку про квоту. */
const REFUNDABLE_REASONS = new Set([
  'worker_unreachable',
  'worker_timeout',
  'dispatch_lost',
  'ruleset_drift',
  'ocr_unavailable',
  'vlm_unavailable',
])

export function isRefundableReason(reason: string): boolean {
  return REFUNDABLE_REASONS.has(reason)
}

export function failReasonLabel(reason: string): string {
  return t.failReasons[reason] ?? reason
}

export type ReaderCoverageSummary =
  | { kind: 'master_pdf'; pages: number }
  | { kind: 'photo'; have: number; of: number }
  | null

/**
 * Разбор `photo_inspections.reader_coverage` (план §5, `_reader_coverage(ctx)
 * -> set[str]` на стороне воркера) в пару чисел для строки источника
 * («покрытие: X граней из Y» / «M страниц»). Точная JSON-форма поля не
 * задокументирована в этом репозитории (воркер — `inspectorx-vision`, вне
 * этого репо) — читаем по распространённым формам (массив покрытых
 * граней/страниц, либо объект с числами), а когда форма непонятна, честно
 * возвращаем `null` вместо того, чтобы подставить нафантазированное число:
 * отсутствие покрытия — не то же самое, что «покрыто всё» или «не проверено».
 * `assetCount` — запасной знаменатель/числитель, когда `reader_coverage`
 * ещё не пришёл (например прямо на границе `queued → done`).
 */
export function readerCoverageSummary(
  sourceKind: 'photo' | 'master_pdf',
  readerCoverage: unknown,
  assetCount: number,
): ReaderCoverageSummary {
  if (sourceKind === 'master_pdf') {
    if (Array.isArray(readerCoverage)) return { kind: 'master_pdf', pages: readerCoverage.length }
    if (readerCoverage && typeof readerCoverage === 'object') {
      const pages = (readerCoverage as Record<string, unknown>).pages
      if (typeof pages === 'number') return { kind: 'master_pdf', pages }
    }
    return assetCount > 0 ? { kind: 'master_pdf', pages: assetCount } : null
  }
  if (Array.isArray(readerCoverage)) {
    return { kind: 'photo', have: readerCoverage.length, of: Math.max(assetCount, readerCoverage.length) }
  }
  if (readerCoverage && typeof readerCoverage === 'object') {
    const o = readerCoverage as Record<string, unknown>
    const have = typeof o.have === 'number' ? o.have : typeof o.covered === 'number' ? o.covered : undefined
    const of = typeof o.of === 'number' ? o.of : typeof o.total === 'number' ? o.total : undefined
    if (have !== undefined && of !== undefined) return { kind: 'photo', have, of }
  }
  return assetCount > 0 ? { kind: 'photo', have: assetCount, of: assetCount } : null
}
