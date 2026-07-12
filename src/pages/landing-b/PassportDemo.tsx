import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, ChevronRight, ExternalLink, Lock } from 'lucide-react'
import { CATEGORY_LABEL, type RequirementCategory } from '@/data/taxonomy'

/**
 * Живой «Паспорт товара» — витрина реальных данных v1.
 * Всё содержимое взято из миграции 20260711130000_v1_content:
 * товар ТН ВЭД 2404 11 000 1 (стики, alias «IQOS»), реальные счётчики
 * требований по операциям, реальные названия этапов и требований.
 */

interface DemoReq {
  title: string
  cat: RequirementCategory
}
interface DemoStage {
  index: number // sort_order этапа из lifecycle_stages
  name: string
  reqs: DemoReq[]
}
interface DemoView {
  stages: DemoStage[]
  shown: number // сколько требований показано в демо
}

type OpKey = 'product' | 'realization' | 'import' | 'export'
type TransportKey = 'avto' | 'train'

const OPS: { key: OpKey; label: string; count: number }[] = [
  { key: 'product', label: 'Продукт', count: 51 },
  { key: 'realization', label: 'Реализация', count: 7 },
  { key: 'import', label: 'Импорт', count: 75 },
  { key: 'export', label: 'Экспорт', count: 32 },
]

const VIEWS: Record<'product' | 'realization' | 'import.avto' | 'import.train' | 'export', DemoView> = {
  product: {
    shown: 6,
    stages: [
      {
        index: 1,
        name: 'Технические требования и безопасность',
        reqs: [
          { title: 'Обязательное соответствие регламентам', cat: 'tbt' },
          { title: 'Запрещенные ингредиенты в производстве', cat: 'tbt' },
        ],
      },
      {
        index: 4,
        name: 'Маркировка и защита прав потребителей',
        reqs: [
          { title: 'Медицинское предупреждение', cat: 'marking' },
          { title: 'Информация о производителе и импортере', cat: 'marking' },
        ],
      },
      {
        index: 6,
        name: 'Оценка соответствия, декларация и сертификация',
        reqs: [
          { title: 'Декларация или сертификация', cat: 'tbt' },
          { title: 'Отбор образцов продукции', cat: 'tbt' },
        ],
      },
    ],
  },
  realization: {
    shown: 2,
    stages: [
      {
        index: 33,
        name: 'Требования для выпуска в обращение',
        reqs: [{ title: 'Средство цифровой маркировки', cat: 'marking' }],
      },
      { index: 34, name: 'Ценообразование', reqs: [] },
      {
        index: 36,
        name: 'Правила розничной торговли',
        reqs: [{ title: 'Возрастное ограничение', cat: 'licensing' }],
      },
    ],
  },
  'import.avto': {
    shown: 4,
    stages: [
      {
        index: 7,
        name: 'Регистрация импортного контракта',
        reqs: [{ title: 'Зарегистрировать внешнеторговый контракт в ЕЭИСВО', cat: 'currency' }],
      },
      {
        index: 9,
        name: 'Пересечение границы',
        reqs: [{ title: 'Заполнить импортную таможенную декларацию', cat: 'customs' }],
      },
      {
        index: 12,
        name: 'Санитарно-эпидемиологическое заключение',
        reqs: [
          { title: 'Доставить образцы продукции в лабораторию', cat: 'sps' },
          { title: 'Получить санитарно-эпидемиологическое заключение', cat: 'sps' },
        ],
      },
    ],
  },
  'import.train': {
    shown: 4,
    stages: [
      {
        index: 15,
        name: 'Подготовка к доставке груза ж/д транспортом',
        reqs: [{ title: 'Заключить онлайн соглашение с ТехПД и договор с РЖУ', cat: 'customs' }],
      },
      {
        index: 20,
        name: 'Помещение груза на таможенный склад',
        reqs: [
          { title: 'Заключить договор с таможенным складом', cat: 'customs' },
          { title: 'Внести предоплату за услуги таможенного склада', cat: 'currency' },
        ],
      },
      {
        index: 21,
        name: 'Организация возврата пустых вагонов',
        reqs: [{ title: 'Организовать возврат порожных вагонов', cat: 'customs' }],
      },
    ],
  },
  export: {
    shown: 4,
    stages: [
      {
        index: 23,
        name: 'Получение авианакладной',
        reqs: [
          { title: 'Заключить договор с агентом по продаже авиационных грузовых перевозок', cat: 'customs' },
        ],
      },
      {
        index: 25,
        name: 'Договор с аэропортом на обработку груза',
        reqs: [{ title: 'Запросить допуск на грузовой склад аэропорта', cat: 'customs' }],
      },
      {
        index: 27,
        name: 'Таможенное оформление',
        reqs: [
          { title: 'Заполнить грузовую таможенную декларацию', cat: 'customs' },
          { title: 'Получить разрешение таможни на выпуск груза', cat: 'customs' },
        ],
      },
    ],
  },
}

const TRANSPORTS_BY_OP: Partial<Record<OpKey, { key: TransportKey; label: string; count: number }[]>> = {
  import: [
    { key: 'avto', label: 'Авто · 36', count: 36 },
    { key: 'train', label: 'Поезд · 39', count: 39 },
  ],
}

const AUTOPLAY_ORDER: OpKey[] = ['product', 'realization', 'import', 'export']

export function PassportDemo() {
  const [op, setOp] = useState<OpKey>('product')
  const [transport, setTransport] = useState<TransportKey>('avto')
  const [openReq, setOpenReq] = useState<string | null>(null)
  const [engaged, setEngaged] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  // автолистание вкладок, пока посетитель не потрогал демо
  useEffect(() => {
    if (engaged) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const id = window.setInterval(() => {
      if (document.hidden) return
      setOp((prev) => AUTOPLAY_ORDER[(AUTOPLAY_ORDER.indexOf(prev) + 1) % AUTOPLAY_ORDER.length])
    }, 4200)
    return () => window.clearInterval(id)
  }, [engaged])

  const engage = () => setEngaged(true)

  const viewKey = op === 'import' ? (`import.${transport}` as const) : op
  const view = VIEWS[viewKey]
  const opMeta = OPS.find((o) => o.key === op)!
  const transports = TRANSPORTS_BY_OP[op]

  let reqIndex = 0

  return (
    <div className="lb-passport" ref={rootRef} onPointerDown={engage} onPointerEnter={engage} onKeyDown={engage}>
      <div className="lb-passport-head">
        <div>
          <div className="lb-passport-kicker">Паспорт товара · пример из базы</div>
          <h3 className="lb-passport-title">Табачные стики для нагревания (IQOS)</h3>
        </div>
        <span className="lb-passport-code">ТН ВЭД 2404 11 000 1</span>
      </div>

      <div className="lb-passport-body">
        <div className="lb-ops" role="tablist" aria-label="Операции">
          <div className="lb-ops-label">Операция</div>
          {OPS.map((o) => (
            <button
              key={o.key}
              role="tab"
              aria-selected={op === o.key}
              className="lb-op"
              onClick={() => {
                engage()
                setOp(o.key)
                setOpenReq(null)
              }}
            >
              {o.label}
              <span className="lb-op-count">{o.count}</span>
            </button>
          ))}
          <div className="lb-ops-foot">Также в базе: реэкспорт — 16 и реимпорт — 22 требования.</div>
        </div>

        <div className="lb-stage-pane">
          {transports && (
            <div className="lb-transports" role="tablist" aria-label="Вид транспорта">
              {transports.map((t) => (
                <button
                  key={t.key}
                  role="tab"
                  aria-selected={transport === t.key}
                  className="lb-transport"
                  onClick={() => {
                    engage()
                    setTransport(t.key)
                    setOpenReq(null)
                  }}
                >
                  {t.label}
                </button>
              ))}
            </div>
          )}

          <div key={viewKey} className="lb-route">
            <span className="lb-thread" aria-hidden="true" />
            {view.stages.map((stage) => (
              <div className="lb-stage" key={stage.index}>
                <div className="lb-stage-name lb-anim-in" style={{ '--d': reqIndex * 60 } as React.CSSProperties}>
                  <span className="lb-station" style={{ '--d': reqIndex * 60 } as React.CSSProperties}>
                    {String(stage.index).padStart(2, '0')}
                  </span>
                  {stage.name}
                </div>
                {stage.reqs.length === 0 && (
                  <div className="lb-stage-empty lb-anim-in" style={{ '--d': (reqIndex += 1) * 60 } as React.CSSProperties}>
                    <Lock size={13} aria-hidden /> Требования этапа — в полном паспорте в каталоге
                  </div>
                )}
                {stage.reqs.map((req) => {
                  const id = `${viewKey}:${req.title}`
                  const open = openReq === id
                  reqIndex += 1
                  return (
                    <div key={id}>
                      <button
                        className="lb-req lb-anim-in"
                        style={{ '--d': reqIndex * 60 } as React.CSSProperties}
                        aria-expanded={open}
                        onClick={() => {
                          engage()
                          setOpenReq(open ? null : id)
                        }}
                      >
                        <span className="lb-req-cat">{CATEGORY_LABEL[req.cat]}</span>
                        <span className="lb-req-title">{req.title}</span>
                        <ChevronRight size={16} className="lb-req-chev" aria-hidden />
                      </button>
                      {open && (
                        <div className="lb-req-detail lb-anim-in">
                          <div className="lb-detail-item">
                            <h4>Шаги исполнения</h4>
                            <p>
                              <span className="lb-lock">
                                <Lock size={13} aria-hidden /> Пошаговый порядок — в тарифе «Ранний доступ»
                              </span>
                            </p>
                          </div>
                          <div className="lb-detail-item">
                            <h4>Документы</h4>
                            <p>
                              <span className="lb-lock">
                                <Lock size={13} aria-hidden /> Список и где получить — в тарифе
                              </span>
                            </p>
                          </div>
                          <div className="lb-detail-item lb-detail-sanction">
                            <h4>Санкция за нарушение</h4>
                            <p>Штраф с точной суммой и статьёй — в полной карточке</p>
                          </div>
                          <div className="lb-detail-item">
                            <h4>Ведомство</h4>
                            <p>Контролирующий орган и контакты — в полной карточке</p>
                          </div>
                          <div className="lb-detail-cite">
                            <div className="lb-detail-item">
                              <h4>Цитата закона</h4>
                              <p>Дословный фрагмент акта — с пунктом и работающей ссылкой. Пример из базы:</p>
                            </div>
                            <a
                              className="lb-cite-ref"
                              href="https://lex.uz/uz/docs/-6931425"
                              target="_blank"
                              rel="noreferrer"
                            >
                              ПКМ-290, Технический регламент · lex.uz
                              <ExternalLink size={12} aria-hidden />
                            </a>
                          </div>
                        </div>
                      )}
                    </div>
                  )
                })}
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="lb-passport-foot">
        <span>
          Показано {view.shown} из {opMeta.count} требований операции «{opMeta.label.toLowerCase()}»
        </span>
        <Link to="/catalog">
          Открыть полный паспорт в каталоге
          <ArrowRight size={15} aria-hidden />
        </Link>
      </div>
    </div>
  )
}
