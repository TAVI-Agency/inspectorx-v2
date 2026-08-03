/**
 * Мок-фикстуры: то, чего в базе ещё нет.
 * — Требования для молока (реальный товар без контента) и парацетамола (мок-товар).
 * — Лента изменений, проекты НПА, телеметрия, демо-details для реальных требований.
 * Интерфейс тот же, что у Supabase-репозитория, — подмена без правки компонентов.
 */
import type {
  ChangeCard,
  Citation,
  FaqItem,
  LawyerReview,
  ProductPassport,
  RequirementCard,
  RequirementDetail,
  RequirementReviewStats,
  RequirementRow,
  SearchHit,
  StageInfo,
  UserQuestion,
} from '../types'
import { ok } from '../types'

// Реальные id из прод-базы (стабильные, перенесены миграцией контента)
export const CIGARETTES_PRODUCT_ID = 'e95fd48c-697c-1f2a-7967-8e8db36b9f91'
export const CIGARETTES_HS = '2404110001'
export const MILK_PRODUCT_ID = '4c95c6fe-7268-b2b5-4be5-75a6da8424ff'
export const MILK_HS = '0401201100'
export const PARACETAMOL_PRODUCT_ID = 'mock-product-paracetamol'

function isoDaysFromNow(days: number): string {
  const d = new Date()
  d.setDate(d.getDate() + days)
  return d.toISOString()
}

// ── Паспорта ───────────────────────────────────────────────────────

/** Мок-дополнения к реальному паспорту молока (ИКПУ в схеме нет — см. QUESTIONS №1) */
export const milkPassportExtras = {
  ikpuCode: '02202001001000000',
  complexity: 6,
  verifiedAt: isoDaysFromNow(-1),
}

export const paracetamolPassport: ProductPassport = {
  id: PARACETAMOL_PRODUCT_ID,
  displayName: 'Парацетамол',
  officialName:
    'лекарственные средства, содержащие парацетамол, расфасованные для розничной продажи',
  hsCode: '3004900002',
  ikpuCode: '03808001001000000',
  categoryName: 'Фармацевтическая продукция',
  hierarchyLevels: [
    '3004 | Лекарственные средства, расфасованные в виде дозированных лекарственных форм',
    '3004 90 | прочие',
    '3004 90 000 2 | содержащие парацетамол',
  ],
  complexity: 8,
  verifiedAt: isoDaysFromNow(-2),
  // Полностью мок-товар — не привязан к catalog.product_types; countries считает index.ts
  countries: [],
  // Чипы паспорта (Задача 33) рендерятся из codes[], а не из hsCode/ikpuCode
  // напрямую — нужны оба кода, а не только фискальный (ИКПУ).
  codes: [
    { system: 'tnved', code: '3004900002' },
    { system: 'ikpu', code: '03808001001000000' },
  ],
}

export const paracetamolHit: SearchHit = {
  id: PARACETAMOL_PRODUCT_ID,
  kind: 'product',
  displayName: 'Парацетамол',
  officialName: paracetamolPassport.officialName,
  code: paracetamolPassport.hsCode,
  codeKind: 'hs',
  categoryName: paracetamolPassport.categoryName,
}

export function paracetamolMatches(query: string): boolean {
  const q = query.trim().toLowerCase()
  if (q.length < 2) return false
  return (
    'парацетамол'.includes(q) ||
    'paracetamol'.includes(q) ||
    'панадол'.includes(q) ||
    paracetamolPassport.hsCode.startsWith(q.replace(/\D/g, '') || '—')
  )
}

// ── Этапы ЖЦ (мок-товары) ──────────────────────────────────────────

const milkStages = {
  sanitary: { id: 'mock-stage-sanitary', name: 'Санитарные, ветеринарные и фитосанитарные нормы', sortOrder: 3 },
  labeling: { id: 'mock-stage-labeling', name: 'Маркировка и защита прав потребителей', sortOrder: 4 },
  conformity: { id: 'mock-stage-conformity', name: 'Оценка соответствия, декларация и сертификация', sortOrder: 6 },
  retail: { id: 'mock-stage-retail', name: 'Реализация и розничная торговля', sortOrder: 20 },
}

const parStages = {
  registration: { id: 'mock-stage-registration', name: 'Государственная регистрация', sortOrder: 1 },
  licensing: { id: 'mock-stage-licensing', name: 'Лицензирование деятельности', sortOrder: 2 },
  conformity: { id: 'mock-stage-conformity', name: 'Оценка соответствия, декларация и сертификация', sortOrder: 6 },
  labeling: { id: 'mock-stage-labeling', name: 'Маркировка и защита прав потребителей', sortOrder: 4 },
  retail: { id: 'mock-stage-retail', name: 'Реализация и розничная торговля', sortOrder: 20 },
}

// ── Конструктор мок-требования ─────────────────────────────────────

interface MockReq {
  row: RequirementRow
  detail: RequirementDetail
  citations: Citation[]
  faqs: FaqItem[]
  authority?: { name: string; phone?: string; website?: string }
}

const mockReqs = new Map<string, MockReq>()

function defineReq(
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
  > & { status?: RequirementRow['status'] },
  rest: Omit<MockReq, 'row'>,
): MockReq {
  const req: MockReq = {
    row: {
      ...row,
      id,
      // Мок-товары (молоко/парацетамол) живут только в УЗ, действуют сейчас
      jurisdiction: 'UZ',
      lifecycle: 'in_force',
      status: row.status ?? { kind: 'active' },
      unread: false,
      underReview: false,
      stageId: stage.id,
      stageName: stage.name,
      stageSortOrder: stage.sortOrder,
    },
    ...rest,
  }
  mockReqs.set(id, req)
  return req
}

export function getMockReq(id: string): MockReq | undefined {
  return mockReqs.get(id)
}

export function isMockRequirementId(id: string): boolean {
  return id.startsWith('mock-')
}

// ── Молоко: 7 требований ───────────────────────────────────────────

defineReq(
  'mock-milk-cert',
  milkStages.conformity,
  {
    title: 'Получить сертификат соответствия на партию молока',
    deontic: 'obligation',
    roles: ['producer', 'importer'],
    operation: 'product',
    authorityName: 'Узстандарт',
    sanctionSummary: 'штраф до 50 БРВ',
    trustLabel: 'lawyer_verified',
    trustDate: isoDaysFromNow(-6),
  },
  {
    authority: { name: 'Агентство «Узстандарт»', phone: '+998 71 202-02-02', website: 'https://standart.uz' },
    detail: {
      description:
        'Пастеризованное молоко подлежит обязательной сертификации до выпуска в обращение. Сертификат оформляется на партию или на серийное производство и вносится в единый реестр.',
      steps: [
        { text: 'Подать заявку в аккредитованный орган по сертификации (Узстандарт)', term: '1 рабочий день', cost: 'госпошлина от 450 000 сум' },
        { text: 'Передать образцы партии в аккредитованную лабораторию на испытания', term: '5 рабочих дней' },
        { text: 'Получить сертификат и проверить запись в реестре sert.uz', term: '1 рабочий день' },
      ],
      documents: [
        { name: 'Заявка на сертификацию по установленной форме', where: 'орган по сертификации' },
        { name: 'Протокол испытаний', where: 'аккредитованная лаборатория' },
        { name: 'Контракт или договор поставки', where: 'ваш отдел ВЭД' },
      ],
      sanctions: [
        { text: 'Штраф до 50 БРВ за реализацию без сертификата', article: 'ст. 204 КоАО' },
        { text: 'Запрет реализации партии до устранения нарушения' },
      ],
    },
    citations: [
      {
        actTitle: 'ПКМ-343 «О сертификации пищевой продукции»',
        paragraphRef: 'п. 8',
        versionDate: '2026-02-10',
        verbatimRu:
          'Молоко и молочная продукция, выпускаемые в обращение на территории Республики Узбекистан, подлежат обязательной оценке соответствия в форме сертификации либо декларирования соответствия.',
        verbatimUz:
          'O‘zbekiston Respublikasi hududida muomalaga chiqariladigan sut va sut mahsulotlari sertifikatlash yoki muvofiqlik deklaratsiyasi shaklida majburiy muvofiqlikni baholashdan o‘tkazilishi shart.',
        isPrimary: true,
      },
    ],
    faqs: [
      {
        question: 'Можно ли оформить один сертификат на несколько партий?',
        answer:
          'Да — при серийном производстве оформляется сертификат сроком до 3 лет с ежегодным инспекционным контролем. Для разовых поставок сертификат оформляется на партию.',
        trustLabel: 'lawyer_verified',
      },
    ],
  },
)

defineReq(
  'mock-milk-labeling',
  milkStages.labeling,
  {
    title: 'Нанести маркировку на государственном и русском языках',
    deontic: 'obligation',
    roles: ['producer', 'importer'],
    operation: 'product',
    authorityName: 'Комитет по защите прав потребителей',
    sanctionSummary: 'штраф до 30 БРВ',
    trustLabel: 'lawyer_verified',
    trustDate: isoDaysFromNow(-6),
  },
  {
    authority: { name: 'Комитет по защите прав потребителей', website: 'https://istemolchi.uz' },
    detail: {
      description:
        'На потребительской упаковке обязательны: наименование, состав, жирность, дата производства, срок годности, условия хранения и данные производителя — на узбекском и русском языках.',
      steps: [
        { text: 'Проверить макет этикетки на состав обязательных сведений (п. 12 правил маркировки)' },
        { text: 'Заказать перевод и корректуру на государственный язык', cost: 'от 200 000 сум' },
        { text: 'Утвердить макет и внести в спецификацию продукции' },
      ],
      documents: [
        { name: 'Макет этикетки с обязательными сведениями', where: 'ваш дизайнер / типография' },
      ],
      sanctions: [
        { text: 'Штраф до 30 БРВ за отсутствие обязательных сведений', article: 'ст. 178 КоАО' },
      ],
    },
    citations: [
      {
        actTitle: 'ПКМ-149 «Правила маркировки потребительских товаров»',
        paragraphRef: 'п. 12',
        versionDate: '2025-11-03',
        verbatimRu:
          'Информация о товаре доводится до потребителя на государственном языке Республики Узбекистан; допускается дублирование на других языках. Сведения о пищевой продукции должны включать наименование, состав, массу нетто, дату изготовления и срок годности.',
        isPrimary: true,
      },
    ],
    faqs: [],
  },
)

defineReq(
  'mock-milk-ses',
  milkStages.sanitary,
  {
    title: 'Получить санитарно-эпидемиологическое заключение',
    deontic: 'obligation',
    roles: ['producer', 'importer'],
    operation: 'product',
    authorityName: 'Санэпидкомитет',
    sanctionSummary: 'штраф до 100 БРВ',
    trustLabel: 'lawyer_verified',
    trustDate: isoDaysFromNow(-6),
  },
  {
    authority: { name: 'Комитет санитарно-эпидемиологического благополучия', phone: '+998 71 241-04-50' },
    detail: {
      description:
        'До выпуска в обращение молочная продукция проходит санитарно-эпидемиологическую экспертизу. Заключение подтверждает соответствие СанПиН по микробиологии и остаточным веществам.',
      steps: [
        { text: 'Подать заявление через ЕПИГУ (my.gov.uz) с приложением документов', term: '1 день' },
        { text: 'Пройти лабораторную экспертизу образцов', term: 'до 10 рабочих дней', cost: 'по прейскуранту центра СЭС' },
        { text: 'Получить заключение в электронном виде', term: '1 день' },
      ],
      documents: [
        { name: 'Заявление через ЕПИГУ', where: 'my.gov.uz' },
        { name: 'Спецификация продукции и состав', where: 'ваш технолог' },
        { name: 'Документы о происхождении сырья', where: 'поставщик' },
      ],
      sanctions: [
        { text: 'Штраф до 100 БРВ за выпуск продукции без заключения', article: 'ст. 55 КоАО' },
        { text: 'Изъятие партии из оборота' },
      ],
    },
    citations: [
      {
        actTitle: 'СанПиН РУз № 0138-03',
        paragraphRef: 'п. 4.2',
        versionDate: '2025-06-18',
        verbatimRu:
          'Молоко и молочные продукты допускаются к реализации при наличии санитарно-эпидемиологического заключения, подтверждающего их соответствие санитарным правилам и нормам.',
        isPrimary: true,
      },
    ],
    faqs: [
      {
        question: 'Нужно ли новое заключение на каждую партию?',
        answer:
          'Нет. Заключение действует на вид продукции; повторная экспертиза требуется при изменении рецептуры, сырья или по истечении срока действия.',
        trustLabel: 'official_answer',
      },
    ],
  },
)

defineReq(
  'mock-milk-coldchain',
  milkStages.retail,
  {
    title: 'Соблюдать холодовую цепь 2–6 °C при хранении и перевозке',
    deontic: 'obligation',
    roles: ['seller', 'carrier'],
    operation: 'realization',
    authorityName: 'Санэпидкомитет',
    sanctionSummary: 'штраф до 25 БРВ',
    trustLabel: 'lawyer_verified',
    trustDate: isoDaysFromNow(-6),
  },
  {
    detail: {
      description:
        'Пастеризованное молоко хранится и перевозится при температуре от +2 до +6 °C. Нарушение температурного режима — основание для снятия партии с реализации.',
      steps: [
        { text: 'Оборудовать транспорт и витрины термодатчиками с журналом контроля' },
        { text: 'Фиксировать температуру при приёмке каждой партии' },
      ],
      documents: [{ name: 'Журнал температурного контроля', where: 'ведётся на месте' }],
      sanctions: [{ text: 'Штраф до 25 БРВ, снятие партии с реализации', article: 'ст. 57 КоАО' }],
    },
    citations: [
      {
        actTitle: 'СанПиН РУз № 0138-03',
        paragraphRef: 'п. 7.1',
        versionDate: '2025-06-18',
        verbatimRu:
          'Хранение и транспортировка пастеризованного молока осуществляются при температуре от +2 °C до +6 °C в специально оборудованных транспортных средствах.',
        isPrimary: true,
      },
    ],
    faqs: [],
  },
)

defineReq(
  'mock-milk-expiry',
  milkStages.retail,
  {
    title: 'Не реализовывать молоко с истёкшим сроком годности',
    deontic: 'prohibition',
    roles: ['seller'],
    operation: 'realization',
    authorityName: 'Комитет по защите прав потребителей',
    sanctionSummary: 'штраф до 50 БРВ + снятие с реализации',
    status: { kind: 'changed', date: isoDaysFromNow(-3) },
    trustLabel: 'lawyer_verified',
    trustDate: isoDaysFromNow(-3),
  },
  {
    detail: {
      description:
        'Продажа молочной продукции после истечения срока годности запрещена. С последним изменением штраф за повторное нарушение удвоен.',
      steps: [
        { text: 'Настроить контроль остатков по сроку годности (FEFO) в учётной системе' },
        { text: 'Проводить ежедневную проверку витрин и снимать просрочку с полки' },
      ],
      documents: [],
      sanctions: [
        { text: 'Штраф до 50 БРВ, при повторном нарушении — до 100 БРВ', article: 'ст. 204-1 КоАО' },
        { text: 'Снятие товара с реализации, возможна приостановка объекта торговли' },
      ],
    },
    citations: [
      {
        actTitle: 'Закон «О защите прав потребителей»',
        paragraphRef: 'ст. 5',
        versionDate: isoDaysFromNow(-3).slice(0, 10),
        verbatimRu:
          'Продажа товара по истечении установленного срока годности, а также товара, срок годности на который не установлен, если его установление обязательно, запрещается.',
        isPrimary: true,
      },
    ],
    faqs: [],
  },
)

defineReq(
  'mock-milk-aslbelgisi',
  milkStages.labeling,
  {
    title: 'Маркировать каждую единицу кодом Asl Belgisi',
    deontic: 'obligation',
    roles: ['producer', 'importer'],
    operation: 'product',
    authorityName: 'Налоговый комитет',
    sanctionSummary: 'штраф до 100 БРВ',
    status: { kind: 'upcoming', date: isoDaysFromNow(21) },
    trustLabel: 'lawyer_verified',
    trustDate: isoDaysFromNow(-9),
  },
  {
    authority: { name: 'Налоговый комитет (система Asl Belgisi)', website: 'https://aslbelgisi.uz' },
    detail: {
      description:
        'Молочная продукция включается в перечень товаров, подлежащих обязательной цифровой маркировке. С даты вступления каждая потребительская упаковка должна нести код Data Matrix.',
      steps: [
        { text: 'Зарегистрироваться в системе aslbelgisi.uz и получить доступ к заказу кодов', term: '2 рабочих дня' },
        { text: 'Интегрировать нанесение кодов в линию фасовки или заказать типографскую печать', cost: 'код — 68 сум/шт.' },
        { text: 'Настроить передачу данных о вводе в оборот в НИС «Асл белгиси»' },
      ],
      documents: [
        { name: 'Регистрация участника оборота', where: 'aslbelgisi.uz' },
        { name: 'Договор с оператором маркировки', where: 'CRPT Turon' },
      ],
      sanctions: [
        { text: 'Штраф до 100 БРВ за оборот без кодов маркировки', article: 'ст. 227-1 НК' },
        { text: 'Конфискация немаркированной продукции' },
      ],
    },
    citations: [
      {
        actTitle: 'ПКМ-737 «О цифровой маркировке товаров»',
        paragraphRef: 'п. 3, прил. 2',
        versionDate: isoDaysFromNow(-9).slice(0, 10),
        verbatimRu:
          'Ввод в оборот молока и молочной продукции без нанесения средств цифровой маркировки не допускается с даты, установленной приложением 2 к настоящему постановлению.',
        isPrimary: true,
      },
    ],
    faqs: [],
  },
)

defineReq(
  'mock-milk-vat',
  milkStages.retail,
  {
    title: 'Применять льготную ставку НДС на социально значимые молочные продукты',
    deontic: 'permission',
    roles: ['seller', 'producer'],
    operation: 'realization',
    authorityName: 'Налоговый комитет',
    sanctionSummary: 'санкция не установлена — льгота',
    trustLabel: 'lawyer_verified',
    trustDate: isoDaysFromNow(-12),
  },
  {
    detail: {
      description:
        'Для пастеризованного молока базовой жирности действует пониженная ставка НДС. Льгота применяется автоматически при корректном коде ИКПУ в счёте-фактуре.',
      steps: [
        { text: 'Проверить код ИКПУ товара в учётной системе' },
        { text: 'Убедиться, что счета-фактуры формируются с пониженной ставкой' },
      ],
      documents: [],
      sanctions: [],
    },
    citations: [
      {
        actTitle: 'Налоговый кодекс РУз',
        paragraphRef: 'ст. 258-1',
        versionDate: '2026-01-01',
        verbatimRu:
          'Обороты по реализации отдельных видов социально значимых продовольственных товаров по перечню, утверждаемому Кабинетом Министров, облагаются налогом на добавленную стоимость по пониженной ставке.',
        isPrimary: true,
      },
    ],
    faqs: [],
  },
)

// ── Парацетамол: 6 требований ──────────────────────────────────────

defineReq(
  'mock-par-registration',
  parStages.registration,
  {
    title: 'Зарегистрировать лекарственное средство в государственном реестре',
    deontic: 'obligation',
    roles: ['producer', 'importer'],
    operation: 'product',
    authorityName: 'УзФармАгентство',
    sanctionSummary: 'штраф до 100 БРВ + конфискация партии',
    trustLabel: 'lawyer_verified',
    trustDate: isoDaysFromNow(-8),
  },
  {
    authority: { name: 'Агентство по развитию фармацевтической отрасли', website: 'https://uzpharm-control.uz' },
    detail: {
      description:
        'Ввоз и реализация лекарственных средств допускаются только после государственной регистрации и включения в Государственный реестр ЛС Республики Узбекистан.',
      steps: [
        { text: 'Сформировать регистрационное досье (модуль CTD)', term: 'подготовка 2–4 недели' },
        { text: 'Подать досье в УзФармАгентство и оплатить экспертизу', cost: 'от 30 000 000 сум' },
        { text: 'Пройти экспертизу качества, эффективности и безопасности', term: 'до 180 дней' },
        { text: 'Получить регистрационное удостоверение (5 лет)' },
      ],
      documents: [
        { name: 'Регистрационное досье CTD', where: 'производитель' },
        { name: 'Сертификат GMP производителя', where: 'производитель' },
        { name: 'Образцы препарата и стандартные образцы', where: 'производитель' },
      ],
      sanctions: [
        { text: 'Штраф до 100 БРВ за оборот незарегистрированных ЛС', article: 'ст. 186 КоАО' },
        { text: 'Конфискация партии, запрет ввоза' },
      ],
    },
    citations: [
      {
        actTitle: 'Закон «О лекарственных средствах и фармацевтической деятельности»',
        paragraphRef: 'ст. 14',
        versionDate: '2025-09-01',
        verbatimRu:
          'Лекарственные средства допускаются к медицинскому применению, производству, ввозу, реализации и использованию после их государственной регистрации.',
        isPrimary: true,
      },
    ],
    faqs: [
      {
        question: 'Действует ли регистрация других стран (ЕАЭС, ЕС)?',
        answer:
          'Нет, требуется национальная регистрация. Для препаратов из стран со строгой регуляторикой предусмотрена ускоренная процедура признания.',
        trustLabel: 'lawyer_verified',
      },
    ],
  },
)

defineReq(
  'mock-par-license',
  parStages.licensing,
  {
    title: 'Получить лицензию на фармацевтическую деятельность',
    deontic: 'obligation',
    roles: ['seller'],
    operation: 'realization',
    authorityName: 'Минздрав',
    sanctionSummary: 'штраф до 150 БРВ, приостановление деятельности',
    trustLabel: 'lawyer_verified',
    trustDate: isoDaysFromNow(-8),
  },
  {
    detail: {
      description:
        'Оптовая и розничная реализация лекарственных средств — лицензируемый вид деятельности. Лицензия выдаётся через ЕПИГУ и действует бессрочно.',
      steps: [
        { text: 'Подготовить помещение и штат по лицензионным требованиям' },
        { text: 'Подать заявление через license.gov.uz', term: '10 рабочих дней', cost: 'госпошлина 5 БРВ' },
      ],
      documents: [
        { name: 'Документы на помещение (аренда/собственность)' },
        { name: 'Дипломы фарм. специалистов', where: 'отдел кадров' },
      ],
      sanctions: [
        { text: 'Штраф до 150 БРВ за деятельность без лицензии', article: 'ст. 164 КоАО' },
        { text: 'Приостановление деятельности объекта' },
      ],
    },
    citations: [
      {
        actTitle: 'ПКМ-92 «О лицензировании фармацевтической деятельности»',
        paragraphRef: 'п. 5',
        versionDate: '2025-04-14',
        verbatimRu:
          'Фармацевтическая деятельность осуществляется юридическими лицами на основании лицензии, выдаваемой в установленном порядке.',
        isPrimary: true,
      },
    ],
    faqs: [],
  },
)

defineReq(
  'mock-par-series',
  parStages.conformity,
  {
    title: 'Подтверждать соответствие каждой серии препарата',
    deontic: 'obligation',
    roles: ['importer', 'producer'],
    operation: 'import',
    authorityName: 'УзФармАгентство',
    sanctionSummary: 'штраф до 75 БРВ',
    trustLabel: 'lawyer_verified',
    trustDate: isoDaysFromNow(-8),
  },
  {
    detail: {
      description:
        'Каждая ввозимая серия проходит посерийный контроль качества с выдачей сертификата соответствия серии до поступления в оборот.',
      steps: [
        { text: 'Подать заявку на сертификацию серии с приложением сертификата анализа производителя', term: '3 рабочих дня' },
        { text: 'Передать образцы серии на испытания', term: 'до 10 дней' },
      ],
      documents: [
        { name: 'Сертификат анализа производителя (CoA)', where: 'производитель' },
        { name: 'Инвойс и упаковочный лист', where: 'ваш отдел ВЭД' },
      ],
      sanctions: [{ text: 'Штраф до 75 БРВ, возврат или уничтожение серии', article: 'ст. 186 КоАО' }],
    },
    citations: [
      {
        actTitle: 'ПКМ-213 «О контроле качества лекарственных средств»',
        paragraphRef: 'п. 11',
        versionDate: '2025-12-20',
        verbatimRu:
          'Лекарственные средства, ввозимые на территорию Республики Узбекистан, подлежат посерийному контролю качества до их реализации.',
        isPrimary: true,
      },
    ],
    faqs: [],
  },
)

defineReq(
  'mock-par-instruction',
  parStages.labeling,
  {
    title: 'Вкладывать инструкцию на узбекском и русском языках',
    deontic: 'obligation',
    roles: ['producer', 'importer'],
    operation: 'product',
    authorityName: 'УзФармАгентство',
    sanctionSummary: 'штраф до 30 БРВ',
    trustLabel: 'lawyer_verified',
    trustDate: isoDaysFromNow(-8),
  },
  {
    detail: {
      description:
        'В каждую потребительскую упаковку вкладывается инструкция по медицинскому применению на государственном и русском языках, утверждённая при регистрации.',
      steps: [
        { text: 'Согласовать текст инструкции при регистрации препарата' },
        { text: 'Контролировать наличие вкладыша при фасовке каждой серии' },
      ],
      documents: [{ name: 'Утверждённый текст инструкции', where: 'регистрационное досье' }],
      sanctions: [{ text: 'Штраф до 30 БРВ, приостановка реализации серии', article: 'ст. 178 КоАО' }],
    },
    citations: [
      {
        actTitle: 'Закон «О лекарственных средствах и фармацевтической деятельности»',
        paragraphRef: 'ст. 27',
        versionDate: '2025-09-01',
        verbatimRu:
          'Лекарственные средства поступают в обращение с инструкцией по применению на государственном языке и других языках в соответствии с законодательством.',
        isPrimary: true,
      },
    ],
    faqs: [],
  },
)

defineReq(
  'mock-par-pharmacy-only',
  parStages.retail,
  {
    title: 'Не продавать лекарственные средства вне аптечных организаций',
    deontic: 'prohibition',
    roles: ['seller'],
    operation: 'realization',
    authorityName: 'УзФармНадзор',
    sanctionSummary: 'штраф до 100 БРВ',
    trustLabel: 'lawyer_verified',
    trustDate: isoDaysFromNow(-8),
  },
  {
    detail: {
      description:
        'Розничная реализация лекарственных средств, включая безрецептурные, допускается только через аптечные организации, имеющие лицензию.',
      steps: [],
      documents: [],
      sanctions: [
        { text: 'Штраф до 100 БРВ, конфискация товара', article: 'ст. 164 КоАО' },
      ],
    },
    citations: [
      {
        actTitle: 'Закон «О лекарственных средствах и фармацевтической деятельности»',
        paragraphRef: 'ст. 31',
        versionDate: '2025-09-01',
        verbatimRu:
          'Розничная реализация лекарственных средств осуществляется аптечными организациями в порядке, установленном законодательством.',
        isPrimary: true,
      },
    ],
    faqs: [],
  },
)

defineReq(
  'mock-par-storage',
  parStages.retail,
  {
    title: 'Соблюдать температурный режим хранения до 25 °C',
    deontic: 'obligation',
    roles: ['seller', 'carrier'],
    operation: 'realization',
    authorityName: 'УзФармНадзор',
    sanctionSummary: 'штраф до 25 БРВ',
    trustLabel: 'lawyer_verified',
    trustDate: isoDaysFromNow(-8),
  },
  {
    detail: {
      description:
        'Парацетамол хранится в сухом, защищённом от света месте при температуре не выше 25 °C. Условия контролируются при хранении и перевозке.',
      steps: [
        { text: 'Обеспечить термокарты/датчики в местах хранения' },
        { text: 'Вести журнал контроля температуры и влажности' },
      ],
      documents: [{ name: 'Журнал контроля условий хранения', where: 'ведётся на месте' }],
      sanctions: [{ text: 'Штраф до 25 БРВ, изъятие партии при нарушении условий', article: 'ст. 57 КоАО' }],
    },
    citations: [
      {
        actTitle: 'Приказ МЗ № 340 «Правила хранения лекарственных средств»',
        paragraphRef: 'п. 6.4',
        versionDate: '2025-03-02',
        verbatimRu:
          'Хранение лекарственных средств осуществляется с учётом требований нормативной документации производителя к температурному режиму и влажности.',
        isPrimary: true,
      },
    ],
    faqs: [],
  },
)

// ── Списки строк по товарам ────────────────────────────────────────

const MILK_REQ_IDS = [
  'mock-milk-cert',
  'mock-milk-labeling',
  'mock-milk-ses',
  'mock-milk-coldchain',
  'mock-milk-expiry',
  'mock-milk-aslbelgisi',
  'mock-milk-vat',
]

const PAR_REQ_IDS = [
  'mock-par-registration',
  'mock-par-license',
  'mock-par-series',
  'mock-par-instruction',
  'mock-par-pharmacy-only',
  'mock-par-storage',
]

export function mockRowsFor(productId: string): RequirementRow[] {
  const ids =
    productId === MILK_PRODUCT_ID
      ? MILK_REQ_IDS
      : productId === PARACETAMOL_PRODUCT_ID
        ? PAR_REQ_IDS
        : []
  return ids
    .map((id) => mockReqs.get(id)!.row)
    .sort((a, b) => a.stageSortOrder - b.stageSortOrder)
}

export function stagesFromRows(rows: RequirementRow[]): StageInfo[] {
  const map = new Map<string, StageInfo>()
  for (const row of rows) {
    const s = map.get(row.stageId)
    if (s) {
      s.count += 1
      if (row.unread) s.unreadCount += 1
    } else {
      map.set(row.stageId, {
        id: row.stageId,
        name: row.stageName,
        sortOrder: row.stageSortOrder,
        count: 1,
        unreadCount: row.unread ? 1 : 0,
      })
    }
  }
  return [...map.values()].sort((a, b) => a.sortOrder - b.sortOrder)
}

export function mockCardFor(requirementId: string): RequirementCard | undefined {
  const req = mockReqs.get(requirementId)
  if (!req) return undefined
  const history =
    req.row.status.kind === 'changed'
      ? [
          {
            date: req.row.status.date,
            title: 'Ужесточена ответственность за повторное нарушение',
            was: 'Штраф до 50 БРВ независимо от повторности',
            now: 'Повторное нарушение в течение года — до 100 БРВ',
          },
        ]
      : req.row.status.kind === 'upcoming'
        ? [
            {
              date: req.row.status.date,
              title: 'Требование вступает в силу',
              was: 'Маркировка добровольная',
              now: 'Маркировка обязательна для всех участников оборота',
            },
          ]
        : []
  return {
    requirementId,
    jurisdiction: req.row.jurisdiction,
    lifecycle: req.row.lifecycle,
    authority: req.authority ?? (req.row.authorityName ? { name: req.row.authorityName } : undefined),
    detail: ok(req.detail),
    citations: ok(req.citations),
    faqs: ok(req.faqs),
    history: ok(history),
  }
}

// ── Демо-details для реальных требований (мок-режим «я подписчик») ──
// Реальные details закрыты RLS для анонима; чтобы показать клиенту полный
// вид, генерируем правдоподобный шаблон. Под реальной подпиской не используется.

export function demoDetailFor(row: RequirementRow): RequirementCard {
  const detail: RequirementDetail = {
    description:
      row.deontic === 'prohibition'
        ? `Запрет действует для ролей: ${row.roles.join(', ')}. Нарушение фиксируется при проверке и влечёт санкции вплоть до снятия партии с оборота.`
        : `Требование «${row.title}» исполняется до выпуска продукции в обращение. Ниже — шаги, документы и ответственность.`,
    steps:
      row.deontic === 'prohibition'
        ? [{ text: 'Проверить ассортимент и процессы на предмет нарушения запрета' }]
        : [
            { text: 'Изучить пункт техрегламента и сверить текущую практику', term: '1 день' },
            { text: 'Подготовить документы и внести изменения в упаковку/процессы', term: '5–10 рабочих дней' },
            { text: 'Зафиксировать исполнение (акт, макет, запись в системе)' },
          ],
    documents:
      row.deontic === 'prohibition'
        ? []
        : [
            { name: 'Действующий макет упаковки / спецификация', where: 'ваш технолог' },
            { name: 'Подтверждающий документ по требованию', where: row.authorityName ?? 'уполномоченный орган' },
          ],
    sanctions: [
      { text: 'Штраф до 50 БРВ', article: 'ст. 204 КоАО' },
      { text: 'Приостановка реализации партии до устранения' },
    ],
  }
  return {
    requirementId: row.id,
    jurisdiction: row.jurisdiction,
    lifecycle: row.lifecycle,
    authority: row.authorityName ? { name: row.authorityName } : undefined,
    detail: ok(detail),
    citations: ok([
      {
        actTitle: 'ПКМ-290, Технический регламент',
        paragraphRef: 'п. 35',
        versionDate: '2026-01-15',
        verbatimRu:
          'Табачная продукция и устройства для употребления табака и никотина выпускаются в обращение при соответствии требованиям настоящего технического регламента.',
        isPrimary: true,
      },
    ]),
    faqs: ok([]),
    history: ok([]),
  }
}

// ── Лента изменений (мок) ──────────────────────────────────────────

export interface CigaretteChangeSlot {
  changeId: string
  titleIncludes: string[]
  fallbackIndex: number
  status: { kind: 'changed'; date: string } | { kind: 'upcoming'; date: string }
}

/** Какие реальные требования сигарет «изменились» — резолвится по заголовку в рантайме */
export const cigaretteChangeSlots: CigaretteChangeSlot[] = [
  {
    changeId: 'mock-change-warn',
    titleIncludes: ['предупрежд', 'маркировк', 'надпис'],
    fallbackIndex: 2,
    status: { kind: 'upcoming', date: isoDaysFromNow(51) },
  },
  {
    changeId: 'mock-change-cert',
    titleIncludes: ['сертифика'],
    fallbackIndex: 0,
    status: { kind: 'changed', date: isoDaysFromNow(-3) },
  },
]

export interface ChangeFixture extends Omit<ChangeCard, 'unread' | 'requirementId'> {
  /** id мок-требования или слот сигарет (резолвится в рантайме) */
  requirementId?: string
  cigaretteSlot?: string
}

export const changeFixtures: ChangeFixture[] = [
  {
    id: 'mock-change-warn',
    importance: 'high',
    productId: CIGARETTES_PRODUCT_ID,
    productName: 'Стики IQOS',
    stageName: 'Маркировка и защита прав потребителей',
    date: isoDaysFromNow(-2),
    title: 'Увеличена обязательная площадь предупредительных надписей',
    was: 'Предупреждение о вреде — не менее 40% площади каждой большей стороны пачки',
    now: 'Не менее 65% площади каждой большей стороны, пиктограмма — на обеих сторонах',
    effectiveDate: isoDaysFromNow(51),
    action: 'Обновить макеты упаковки и согласовать с типографией до вступления в силу',
    cigaretteSlot: 'mock-change-warn',
  },
  {
    id: 'mock-change-cert',
    importance: 'high',
    productId: CIGARETTES_PRODUCT_ID,
    productName: 'Стики IQOS',
    stageName: 'Оценка соответствия, декларация и сертификация',
    date: isoDaysFromNow(-3),
    title: 'Изменён порядок подтверждения соответствия при ввозе',
    was: 'Сертификат соответствия оформлялся на каждую партию',
    now: 'Допускается декларация о соответствии на серийные поставки сроком до 1 года',
    action: 'Перейти на декларацию — это дешевле и быстрее на повторных партиях',
    inFavor: true,
    cigaretteSlot: 'mock-change-cert',
  },
  {
    id: 'mock-change-aslbelgisi',
    importance: 'medium',
    productId: MILK_PRODUCT_ID,
    productName: 'Молоко',
    stageName: 'Маркировка и защита прав потребителей',
    date: isoDaysFromNow(-5),
    title: 'Молочная продукция включена в перечень обязательной цифровой маркировки',
    was: 'Маркировка Asl Belgisi — добровольная',
    now: 'Каждая упаковка должна нести код Data Matrix',
    effectiveDate: isoDaysFromNow(21),
    action: 'Зарегистрироваться в aslbelgisi.uz и заказать пилотную партию кодов',
    requirementId: 'mock-milk-aslbelgisi',
  },
  {
    id: 'mock-change-expiry',
    importance: 'medium',
    productId: MILK_PRODUCT_ID,
    productName: 'Молоко',
    stageName: 'Реализация и розничная торговля',
    date: isoDaysFromNow(-3),
    title: 'Удвоен штраф за повторную продажу просроченной продукции',
    was: 'Штраф до 50 БРВ независимо от повторности',
    now: 'Повторное нарушение в течение года — до 100 БРВ',
    action: 'Проверить настройки FEFO-контроля в учётной системе',
    requirementId: 'mock-milk-expiry',
  },
  {
    id: 'mock-change-ses-favor',
    importance: 'low',
    productId: MILK_PRODUCT_ID,
    productName: 'Молоко',
    stageName: 'Санитарные, ветеринарные и фитосанитарные нормы',
    date: isoDaysFromNow(-6),
    title: 'Отменено требование дублировать СЭЗ бумажной копией при каждой партии',
    was: 'К каждой партии прикладывалась заверенная копия заключения',
    now: 'Достаточно электронного заключения в системе ЕПИГУ',
    inFavor: true,
    requirementId: 'mock-milk-ses',
  },
  {
    id: 'mock-change-npa-display',
    importance: 'low',
    productId: CIGARETTES_PRODUCT_ID,
    productName: 'Стики IQOS',
    date: isoDaysFromNow(-4),
    title: 'Обсуждается запрет открытой выкладки табачной продукции на кассах',
    isDraftNpa: true,
    discussionUrl: 'https://regulation.gov.uz',
  },
  {
    id: 'mock-change-npa-milk',
    importance: 'low',
    productId: MILK_PRODUCT_ID,
    productName: 'Молоко',
    date: isoDaysFromNow(-1),
    title: 'Проект: обязательное указание доли сухого молока в составе',
    isDraftNpa: true,
    discussionUrl: 'https://regulation.gov.uz',
  },
]

// ── Демо-вопросы («Мои вопросы» в мок-режиме без входа) ────────────
// Реальные вопросы живут в user_questions; фикстуры показывают путь
// эскалации AI → юрист → официальный запрос на витрине.

export const demoQuestions: UserQuestion[] = [
  {
    id: 'mock-question-transit',
    questionText: 'Нужна ли маркировка стиков при транзите через Узбекистан?',
    status: 'expert_answered',
    answerText:
      'При таможенной процедуре транзита требования обязательной маркировки не применяются: товар не выпускается в обращение на территории республики. Важно: транзитная партия должна быть опломбирована, а маршрут — согласован в транзитной декларации. Если часть партии останется в Узбекистане, на неё маркировка обязательна до выпуска.',
    answeredAt: isoDaysFromNow(-1),
    createdAt: isoDaysFromNow(-3),
    isUrgent: false,
    legalReviewOnly: true,
    productId: CIGARETTES_PRODUCT_ID,
  },
  {
    id: 'mock-question-milk-cert',
    questionText: 'Какой сертификат нужен на молоко для экспорта в Казахстан?',
    status: 'ai_answered',
    answerText:
      'Для экспорта молока в Казахстан нужны: ветеринарный сертификат (выдаёт Комитет ветеринарии, на каждую партию) и декларация о соответствии O‘zDSt 1112:2020. Казахстан признаёт узбекскую декларацию в рамках соглашений СНГ, отдельная казахстанская сертификация на границе не требуется.',
    answeredAt: isoDaysFromNow(-5),
    createdAt: isoDaysFromNow(-5),
    isUrgent: false,
    legalReviewOnly: false,
    productId: MILK_PRODUCT_ID,
  },
  {
    id: 'mock-question-gr',
    questionText:
      'Считается ли обезжиренное молоко «молочным напитком» для целей маркировки Asl Belgisi?',
    status: 'gr_sent',
    createdAt: isoDaysFromNow(-8),
    isUrgent: false,
    legalReviewOnly: false,
    productId: MILK_PRODUCT_ID,
  },
]

/** Мок-метрики для товаров, где реальные details закрыты или отсутствуют */
export const mockMetrics: Record<string, { documents: number; maxSanction: string }> = {
  [CIGARETTES_PRODUCT_ID]: { documents: 14, maxSanction: 'до 150 БРВ' },
  [MILK_PRODUCT_ID]: { documents: 9, maxSanction: 'до 100 БРВ' },
  [PARACETAMOL_PRODUCT_ID]: { documents: 11, maxSanction: 'до 150 БРВ' },
}

export const mockWeeklyChangesCount = changeFixtures.filter(
  (c) => !c.isDraftNpa && new Date(c.date).getTime() > Date.now() - 7 * 86_400_000,
).length

// ── Демо-заключения юристов (мок-требования: молоко, парацетамол) ──

/** Витринные заключения: показывают UI секции на мок-товарах */
export const mockLawyerReviews: Record<string, LawyerReview[]> = {
  'mock-milk-cert': [
    {
      id: 'mock-review-milk-cert-1',
      requirementId: 'mock-milk-cert',
      verdict: 'confirm',
      commentText:
        'Подтверждаю: декларация о соответствии по O‘zDSt 1112:2020 обязательна для молока в потребительской упаковке. Обратите внимание — с 2025 года орган по сертификации проверяет и маркировку на соответствие техрегламенту, отдельная экспертиза не нужна.',
      status: 'published',
      lawyerId: 'mock-lawyer-aziza',
      lawyerName: 'Азиза Каримова',
      credentials: 'Юрист по техническому регулированию, 12 лет практики',
      officialReply:
        'Спасибо за уточнение! Добавили ссылку на объединённую процедуру в шаги исполнения.',
      officialRepliedAt: isoDaysFromNow(-3),
      helpful: 14,
      notHelpful: 1,
      myVote: null,
      isMine: false,
      createdAt: isoDaysFromNow(-6),
    },
    {
      id: 'mock-review-milk-cert-2',
      requirementId: 'mock-milk-cert',
      verdict: 'addition',
      commentText:
        'Дополнение: для фермерских хозяйств с объёмом до 500 л/сутки действует упрощённый порядок — декларация на основании собственных доказательств, без протокола аккредитованной лаборатории.',
      status: 'published',
      lawyerId: 'mock-lawyer-jasur',
      lawyerName: 'Жасур Абдуллаев',
      credentials: 'Адвокат, специализация — агробизнес и ВЭД',
      helpful: 6,
      notHelpful: 0,
      myVote: null,
      isMine: false,
      createdAt: isoDaysFromNow(-4),
    },
  ],
  'mock-par-license': [
    {
      id: 'mock-review-par-license-1',
      requirementId: 'mock-par-license',
      verdict: 'outdated',
      commentText:
        'Требование частично устарело: с марта 2026 лицензия на оптовую реализацию лекарств выдаётся через единый портал license.gov.uz, бумажная подача в УзФарм больше не принимается. Срок рассмотрения сократился с 20 до 10 рабочих дней.',
      status: 'published',
      lawyerId: 'mock-lawyer-aziza',
      lawyerName: 'Азиза Каримова',
      credentials: 'Юрист по техническому регулированию, 12 лет практики',
      helpful: 9,
      notHelpful: 2,
      myVote: null,
      isMine: false,
      createdAt: isoDaysFromNow(-2),
    },
  ],
}

/** Счётчики бейджей для мок-строк — согласованы с mockLawyerReviews */
export const mockReviewStats: Record<string, RequirementReviewStats> = {
  'mock-milk-cert': { confirms: 1, disputes: 0, total: 2 },
  'mock-par-license': { confirms: 0, disputes: 1, total: 1 },
}
