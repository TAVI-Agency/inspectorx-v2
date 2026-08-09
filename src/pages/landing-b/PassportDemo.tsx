import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, ChevronRight, ExternalLink, Lock } from 'lucide-react'
import { CATEGORY_LABEL, type RequirementCategory } from '@/data/taxonomy'

/**
 * Живой «Паспорт услуги» — витрина реальных данных.
 * Всё содержимое — из опубликованных карточек услуги «Розничная аптека»
 * (ОКЭД 47.73): реальные названия требований, этапы жизни бизнеса и счётчики.
 */

interface DemoReq {
  title: string
  cat: RequirementCategory
}
interface DemoGroup {
  index: number
  name: string
  reqs: DemoReq[]
}
interface DemoView {
  groups: DemoGroup[]
  shown: number // сколько требований показано в демо
}

type StageKey = 'start' | 'premises' | 'operations' | 'inspections' | 'changes' | 'closure'

const STAGES: { key: StageKey; label: string; count: number }[] = [
  { key: 'start', label: 'Старт и допуск', count: 5 },
  { key: 'premises', label: 'Помещение и запуск', count: 5 },
  { key: 'operations', label: 'Текущая работа', count: 14 },
  { key: 'inspections', label: 'Проверки', count: 4 },
  { key: 'changes', label: 'Изменения и продление', count: 3 },
  { key: 'closure', label: 'Прекращение', count: 4 },
]

const VIEWS: Record<StageKey, DemoView> = {
  start: {
    shown: 4,
    groups: [
      {
        index: 1,
        name: 'Лицензирование аптеки',
        reqs: [
          { title: 'Получить лицензию на розничную реализацию лекарственных средств', cat: 'licensing' },
          { title: 'Назначить заведующего аптекой с высшим фармацевтическим образованием', cat: 'licensing' },
        ],
      },
      {
        index: 2,
        name: 'Допуск к деятельности',
        reqs: [
          { title: 'Проверить, какой режим допуска нужен вашему виду деятельности', cat: 'licensing' },
          { title: 'Проверить персонал по реестру недобросовестных фармацевтических работников', cat: 'licensing' },
        ],
      },
    ],
  },
  premises: {
    shown: 3,
    groups: [
      {
        index: 1,
        name: 'Санитарные нормы помещения',
        reqs: [
          { title: 'Привести помещение аптеки в соответствие с СанПиН', cat: 'sps' },
          { title: 'Организовать хранение лекарств по санитарным правилам', cat: 'sps' },
        ],
      },
      {
        index: 2,
        name: 'Касса и приём платежей',
        reqs: [
          { title: 'Установить онлайн-кассу с контролем рецептурного отпуска и платёжный терминал', cat: 'fiscal' },
        ],
      },
    ],
  },
  operations: {
    shown: 5,
    groups: [
      {
        index: 1,
        name: 'Маркировка лекарств',
        reqs: [{ title: 'Продавать только маркированные лекарства (Asl Belgisi)', cat: 'marking' }],
      },
      {
        index: 2,
        name: 'Санитария и хранение',
        reqs: [
          { title: 'Проводить обязательные медицинские осмотры персонала', cat: 'sps' },
          { title: 'Списывать и уничтожать просроченные лекарства', cat: 'sps' },
        ],
      },
      {
        index: 3,
        name: 'Цены и учёт',
        reqs: [
          { title: 'Соблюдать предельные наценки на рецептурные лекарства', cat: 'fiscal' },
          { title: 'Указывать верный код ИКПУ в каждом чеке', cat: 'fiscal' },
        ],
      },
    ],
  },
  inspections: {
    shown: 2,
    groups: [
      {
        index: 1,
        name: 'Проверки ведомств',
        reqs: [
          { title: 'Проходить проверки фарминспекции Агентства', cat: 'licensing' },
          { title: 'Проходить проверки Санэпидкомитета', cat: 'sps' },
        ],
      },
    ],
  },
  changes: {
    shown: 2,
    groups: [
      {
        index: 1,
        name: 'Продление и переоформление',
        reqs: [
          { title: 'Продлевать лицензию по истечении срока действия', cat: 'licensing' },
          { title: 'Переоформить лицензию при смене адреса или руководителя', cat: 'licensing' },
        ],
      },
    ],
  },
  closure: {
    shown: 2,
    groups: [
      {
        index: 1,
        name: 'Закрытие аптеки',
        reqs: [
          { title: 'Уведомить лицензиара о прекращении деятельности', cat: 'licensing' },
          { title: 'Распорядиться остатками лекарств при закрытии по правилам', cat: 'licensing' },
        ],
      },
    ],
  },
}

const AUTOPLAY_ORDER: StageKey[] = ['start', 'premises', 'operations', 'inspections', 'changes', 'closure']

export function PassportDemo() {
  const [stage, setStage] = useState<StageKey>('start')
  const [openReq, setOpenReq] = useState<string | null>(null)
  const [engaged, setEngaged] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)

  // автолистание вкладок, пока посетитель не потрогал демо
  useEffect(() => {
    if (engaged) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
    const id = window.setInterval(() => {
      if (document.hidden) return
      setStage((prev) => AUTOPLAY_ORDER[(AUTOPLAY_ORDER.indexOf(prev) + 1) % AUTOPLAY_ORDER.length])
    }, 4200)
    return () => window.clearInterval(id)
  }, [engaged])

  const engage = () => setEngaged(true)

  const view = VIEWS[stage]
  const stageMeta = STAGES.find((s) => s.key === stage)!

  let reqIndex = 0

  return (
    <div className="lb-passport" ref={rootRef} onPointerDown={engage} onPointerEnter={engage} onKeyDown={engage}>
      <div className="lb-passport-head">
        <div>
          <div className="lb-passport-kicker">Паспорт услуги · пример из базы</div>
          <h3 className="lb-passport-title">Розничная аптека</h3>
        </div>
        <span className="lb-passport-code">ОКЭД 47.73</span>
      </div>

      <div className="lb-passport-body">
        <div className="lb-ops" role="tablist" aria-label="Этапы жизни бизнеса">
          <div className="lb-ops-label">Этап</div>
          {STAGES.map((s) => (
            <button
              key={s.key}
              role="tab"
              aria-selected={stage === s.key}
              className="lb-op"
              onClick={() => {
                engage()
                setStage(s.key)
                setOpenReq(null)
              }}
            >
              {s.label}
              <span className="lb-op-count">{s.count}</span>
            </button>
          ))}
          <div className="lb-ops-foot">Такой же маршрут — у услуги «Кафе» (ОКЭД 56.10).</div>
        </div>

        <div className="lb-stage-pane">
          <div key={stage} className="lb-route">
            <span className="lb-thread" aria-hidden="true" />
            {view.groups.map((group) => (
              <div className="lb-stage" key={group.index}>
                <div className="lb-stage-name lb-anim-in" style={{ '--d': reqIndex * 60 } as React.CSSProperties}>
                  <span className="lb-station" style={{ '--d': reqIndex * 60 } as React.CSSProperties}>
                    {String(group.index).padStart(2, '0')}
                  </span>
                  {group.name}
                </div>
                {group.reqs.map((req) => {
                  const id = `${stage}:${req.title}`
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
                              <p>
                                Дословный фрагмент акта — с пунктом и работающей ссылкой на lex.uz. Так выглядит
                                готовая карточка (пример по другому товару из базы, уже проверенному):
                              </p>
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
          Показано {view.shown} из {stageMeta.count} требований этапа «{stageMeta.label.toLowerCase()}»
        </span>
        <Link to="/service/47d1ce01-8c19-1ba7-7e5f-8b4681a68a29">
          Открыть полный паспорт услуги
          <ArrowRight size={15} aria-hidden />
        </Link>
      </div>
    </div>
  )
}
