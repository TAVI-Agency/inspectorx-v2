/**
 * Демо-требования по Казахстану (Блок 4, докатка jurisdiction — Задача 30).
 * В базе KZ-данных ещё нет (LegalX по Казахстану не наполнен — см.
 * docs/MASTER_PLAN_BRIEF.md §«Открытые вопросы»), поэтому карточка товара
 * показывает предметно правдоподобный превью-набор: сигареты/стики — тот же
 * глобальный товар (HS), что и в УЗ (CIGARETTES_PRODUCT_ID), но с требованиями
 * казахстанского законодательства. Источник: не lawyer_verified — trustLabel
 * везде 'ai_draft', CountryCoverage.state = 'preview' (index.ts).
 * Для любого другого productId набор пуст — демо есть только по сигаретам.
 */
import { CIGARETTES_PRODUCT_ID } from './fixtures'
import type { Citation, FaqItem, RequirementCard, RequirementDetail, RequirementRow, StageInfo } from '../types'
import { ok } from '../types'

function isoDaysFromNow(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return d.toISOString()
}

/** Нац. коды KZ для сигарет/стиков — ЕАЭС ТН ВЭД (гармонизирован на уровне HS6 с УЗ). */
export const kzCigaretteCodes: { system: string; code: string }[] = [
  { system: 'tnved', code: '2404110000' },
]

const kzStages = {
  marking: { id: 'mock-kz-stage-marking', name: 'Маркировка и защита прав потребителей', sortOrder: 4 },
  conformity: { id: 'mock-kz-stage-conformity', name: 'Оценка соответствия, декларация и сертификация', sortOrder: 6 },
  fiscal: { id: 'mock-kz-stage-fiscal', name: 'Ценообразование', sortOrder: 34 },
  retail: { id: 'mock-kz-stage-retail', name: 'Правила розничной торговли', sortOrder: 36 },
}

interface KzReq {
  row: RequirementRow
  detail: RequirementDetail
  citations: Citation[]
  faqs: FaqItem[]
  authority?: { name: string; phone?: string; website?: string }
}

const kzReqs = new Map<string, KzReq>()

function defineKzReq(
  id: string,
  stage: { id: string; name: string; sortOrder: number },
  row: Omit<
    RequirementRow,
    | 'id'
    | 'jurisdiction'
    | 'lifecycle'
    | 'stageId'
    | 'stageName'
    | 'stageSortOrder'
    | 'unread'
    | 'underReview'
    | 'status'
  >,
  rest: Omit<KzReq, 'row'>,
): void {
  kzReqs.set(id, {
    row: {
      ...row,
      id,
      jurisdiction: 'KZ',
      lifecycle: 'in_force',
      status: { kind: 'active' },
      unread: false,
      underReview: false,
      stageId: stage.id,
      stageName: stage.name,
      stageSortOrder: stage.sortOrder,
    },
    ...rest,
  })
}

defineKzReq(
  'mock-kz-cig-marking',
  kzStages.marking,
  {
    title: 'Нанести код цифровой маркировки АСУИТ (аналог «Честного знака») на каждую пачку',
    deontic: 'obligation',
    roles: ['producer', 'importer'],
    operation: 'product',
    authorityName: 'Комитет государственных доходов Минфина РК',
    sanctionSummary: 'штраф до 200 МРП',
    category: 'marking',
    nature: 'recurring',
    trustLabel: 'ai_draft',
    trustDate: isoDaysFromNow(-1),
  },
  {
    authority: { name: 'Комитет государственных доходов Министерства финансов РК' },
    detail: {
      description:
        'Табачная продукция включена в перечень товаров, подлежащих цифровой маркировке и прослеживаемости. Каждая потребительская упаковка несёт уникальный код, который проверяется при вводе в оборот и рознице.',
      steps: [
        { text: 'Зарегистрироваться оператором маркировки как участник оборота', term: '2–3 рабочих дня' },
        { text: 'Заказать коды маркировки и интегрировать нанесение в линию фасовки' },
        { text: 'Передавать сведения о вводе в оборот в информационную систему маркировки' },
      ],
      documents: [{ name: 'Регистрация участника оборота маркированных товаров' }],
      sanctions: [{ text: 'Штраф до 200 МРП за оборот немаркированной продукции' }],
    },
    citations: [
      {
        actTitle: 'Правила маркировки отдельных видов товаров средствами идентификации (превью, требует проверки юриста)',
        paragraphRef: 'п. 3',
        isPrimary: true,
      },
    ],
    faqs: [],
  },
)

defineKzReq(
  'mock-kz-cig-cert',
  kzStages.conformity,
  {
    title: 'Подтвердить соответствие ТР ТС 035 «О безопасности табачной продукции»',
    deontic: 'obligation',
    roles: ['producer', 'importer'],
    operation: 'product',
    authorityName: 'Комитет технического регулирования и метрологии МТИ РК',
    sanctionSummary: 'штраф до 100 МРП, запрет реализации партии',
    category: 'tbt',
    trustLabel: 'ai_draft',
    trustDate: isoDaysFromNow(-1),
  },
  {
    detail: {
      description:
        'Табачная продукция, обращаемая на территории ЕАЭС, подлежит обязательному подтверждению соответствия техническому регламенту ТР ТС 035/2014 в форме декларирования.',
      steps: [
        { text: 'Подготовить доказательную базу (протоколы испытаний, техдокументацию)' },
        { text: 'Зарегистрировать декларацию о соответствии в аккредитованном органе' },
      ],
      documents: [{ name: 'Протокол испытаний аккредитованной лаборатории' }],
      sanctions: [{ text: 'Штраф до 100 БРВ, запрет реализации партии до устранения' }],
    },
    citations: [
      {
        actTitle: 'ТР ТС 035/2014 «О безопасности табачной продукции» (превью, требует проверки юриста)',
        paragraphRef: 'ст. 6',
        isPrimary: true,
      },
    ],
    faqs: [],
  },
)

defineKzReq(
  'mock-kz-cig-excise',
  kzStages.fiscal,
  {
    title: 'Уплатить акциз и нанести акцизную марку единого образца ЕАЭС',
    deontic: 'obligation',
    roles: ['producer', 'importer'],
    operation: 'import',
    authorityName: 'Комитет государственных доходов Минфина РК',
    sanctionSummary: 'штраф до 150 МРП, конфискация немаркированной партии',
    category: 'fiscal',
    trustLabel: 'ai_draft',
    trustDate: isoDaysFromNow(-1),
  },
  {
    detail: {
      description:
        'Ввоз и производство табачных изделий облагаются акцизом; каждая пачка маркируется акцизной маркой установленного образца до выпуска в оборот.',
      steps: [
        { text: 'Приобрести акцизные марки в налоговом органе по месту учёта' },
        { text: 'Уплатить акциз и заполнить декларацию по подакцизным товарам' },
      ],
      documents: [{ name: 'Декларация по акцизам' }],
      sanctions: [{ text: 'Штраф до 150 МРП, конфискация немаркированной партии' }],
    },
    citations: [
      {
        actTitle: 'Налоговый кодекс РК, раздел «Акцизы» (превью, требует проверки юриста)',
        paragraphRef: 'ст. 462',
        isPrimary: true,
      },
    ],
    faqs: [],
  },
)

defineKzReq(
  'mock-kz-cig-warning',
  kzStages.marking,
  {
    title: 'Разместить предупреждающую надпись о вреде на казахском и русском языках',
    deontic: 'obligation',
    roles: ['producer', 'importer'],
    operation: 'product',
    authorityName: 'Комитет контроля качества и безопасности товаров и услуг МЗ РК',
    sanctionSummary: 'штраф до 50 МРП',
    category: 'marking',
    trustLabel: 'ai_draft',
    trustDate: isoDaysFromNow(-1),
  },
  {
    detail: {
      description:
        'На каждой потребительской упаковке — предупреждение о вреде табака на государственном и русском языках, площадь и формулировка регламентированы.',
      steps: [{ text: 'Согласовать макет упаковки с обязательными предупреждениями' }],
      documents: [{ name: 'Макет упаковки с предупредительной надписью' }],
      sanctions: [{ text: 'Штраф до 50 МРП за отсутствие или неполное предупреждение' }],
    },
    citations: [
      {
        actTitle: 'Кодекс РК «О здоровье народа и системе здравоохранения» (превью, требует проверки юриста)',
        paragraphRef: 'ст. 165',
        isPrimary: true,
      },
    ],
    faqs: [],
  },
)

defineKzReq(
  'mock-kz-cig-age',
  kzStages.retail,
  {
    title: 'Не реализовывать табачную и никотинсодержащую продукцию лицам младше 21 года',
    deontic: 'prohibition',
    roles: ['seller'],
    operation: 'realization',
    authorityName: 'Комитет контроля качества и безопасности товаров и услуг МЗ РК',
    sanctionSummary: 'штраф до 30 МРП',
    category: 'licensing',
    trustLabel: 'ai_draft',
    trustDate: isoDaysFromNow(-1),
  },
  {
    detail: {
      description:
        'Продажа табачных изделий, никотинсодержащей продукции и устройств для их потребления лицам младше 21 года запрещена; продавец обязан проверять документ, удостоверяющий возраст, при малейшем сомнении.',
      steps: [{ text: 'Обучить персонал проверке возраста покупателя на кассе' }],
      documents: [],
      sanctions: [{ text: 'Штраф до 30 МРП за продажу несовершеннолетнему/лицу младше 21 года' }],
    },
    citations: [
      {
        actTitle: 'Кодекс РК «О здоровье народа и системе здравоохранения» (превью, требует проверки юриста)',
        paragraphRef: 'ст. 168',
        isPrimary: true,
      },
    ],
    faqs: [],
  },
)

defineKzReq(
  'mock-kz-cig-declaration',
  kzStages.conformity,
  {
    title: 'Зарегистрировать декларацию о соответствии в едином реестре ЕАЭС',
    deontic: 'obligation',
    roles: ['producer', 'importer'],
    operation: 'import',
    authorityName: 'Комитет технического регулирования и метрологии МТИ РК',
    sanctionSummary: 'штраф до 80 МРП',
    category: 'customs',
    trustLabel: 'ai_draft',
    trustDate: isoDaysFromNow(-1),
  },
  {
    detail: {
      description:
        'Декларация о соответствии ТР ТС 035 подлежит регистрации в едином реестре ЕАЭС до выпуска партии в свободное обращение на таможенной территории.',
      steps: [{ text: 'Подать сведения о декларации в единый реестр через оператора' }],
      documents: [{ name: 'Декларация о соответствии' }],
      sanctions: [{ text: 'Штраф до 80 МРП, приостановка таможенного выпуска партии' }],
    },
    citations: [
      {
        actTitle: 'Решение Коллегии ЕЭК о едином реестре деклараций о соответствии (превью, требует проверки юриста)',
        paragraphRef: 'п. 4',
        isPrimary: true,
      },
    ],
    faqs: [],
  },
)

const KZ_CIGARETTE_REQ_IDS = [
  'mock-kz-cig-marking',
  'mock-kz-cig-cert',
  'mock-kz-cig-excise',
  'mock-kz-cig-warning',
  'mock-kz-cig-age',
  'mock-kz-cig-declaration',
]

export function isKzRequirementId(id: string): boolean {
  return id.startsWith('mock-kz-')
}

/** Демо-набор KZ есть только по сигаретам/стикам — для остальных товаров пусто (данные ещё не собраны). */
export function kzRowsFor(productId: string): RequirementRow[] {
  if (productId !== CIGARETTES_PRODUCT_ID) return []
  return KZ_CIGARETTE_REQ_IDS.map((id) => kzReqs.get(id)!.row).sort(
    (a, b) => a.stageSortOrder - b.stageSortOrder,
  )
}

export function kzStagesFor(productId: string): StageInfo[] {
  const map = new Map<string, StageInfo>()
  for (const row of kzRowsFor(productId)) {
    const s = map.get(row.stageId)
    if (s) s.count += 1
    else map.set(row.stageId, { id: row.stageId, name: row.stageName, sortOrder: row.stageSortOrder, count: 1, unreadCount: 0 })
  }
  return [...map.values()].sort((a, b) => a.sortOrder - b.sortOrder)
}

export function kzCardFor(requirementId: string): RequirementCard | undefined {
  const req = kzReqs.get(requirementId)
  if (!req) return undefined
  return {
    requirementId,
    jurisdiction: 'KZ',
    lifecycle: 'in_force',
    authority: req.authority ?? (req.row.authorityName ? { name: req.row.authorityName } : undefined),
    detail: ok(req.detail),
    citations: ok(req.citations),
    faqs: ok(req.faqs),
    history: ok([]),
  }
}

/** Нац. коды выбранной страны для паспорта — KZ пока только для сигарет/стиков. */
export function kzCodesFor(productId: string): { system: string; code: string }[] {
  return productId === CIGARETTES_PRODUCT_ID ? kzCigaretteCodes : []
}
