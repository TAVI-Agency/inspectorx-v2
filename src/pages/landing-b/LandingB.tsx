import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, Check } from 'lucide-react'
import { RouteCanvas } from './RouteCanvas'
import { PassportDemo } from './PassportDemo'
import { CATEGORY_LABEL, CATEGORY_ORDER } from '@/data/taxonomy'
import './landing-b.css'

/**
 * Лендинг Б — «Один маршрут». Производственная версия витрины.
 * Самодостаточная страница: своя шапка и подвал, живёт вне общего Layout.
 */

/**
 * Вопросы и ответы. Дублируются в JSON-LD (FAQPage) в index.html —
 * при изменении текста обновить и там.
 */
const FAQ_ITEMS = [
  [
    'Что такое ИнспекторX?',
    'ИнспекторX — база требований государственных органов Узбекистана к товарам. Сервис собирает в один «паспорт товара» все этапы, документы, суммы штрафов и дословные цитаты законов — для производства, продажи, импорта и экспорта.',
  ],
  [
    'Как найти требования к своему товару?',
    'Найдите товар в каталоге по названию или коду ТН ВЭД (например, 0401 20 110 0 — молоко), а услугу — по коду ОКЭД (например, 47.73 — аптека), и получите чек-лист требований по этапам.',
  ],
  [
    'Откуда данные и можно ли им доверять?',
    'Каждое требование опирается на дословную цитату нормативного акта с указанием пункта и работающей ссылкой на официальную базу законодательства lex.uz. Мы не пересказываем законы — мы показываем первоисточник.',
  ],
  [
    'Сколько стоит ИнспекторX?',
    'Каталог бесплатный и без регистрации: поиск по товарам, структура паспорта и названия требований. Полные карточки — шаги, документы, санкции, цитаты законов и уведомления об изменениях — по подписке «Ранний доступ» за 490 000 сум в месяц за компанию.',
  ],
  [
    'Кому полезен ИнспекторX?',
    'Импортёрам, экспортёрам, производителям и розничным продавцам в Узбекистане — всем, кого проверяют госорганы: от санитарных требований и маркировки до таможенных процедур.',
  ],
  [
    'Как узнать об изменениях в законах?',
    'Подписчики получают дайджест изменений по своим товарам на email и в Telegram — когда требование меняется, вы узнаёте об этом первым, а не из протокола проверки.',
  ],
] as const

const STATS = [
  { num: '2', label: 'отрасли под ключ' },
  { num: '62', label: 'требования' },
  { num: '39', label: 'актов законодательства' },
  { num: '7', label: 'ведомств-регуляторов' },
] as const

function useRevealObserver() {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    const root = ref.current
    if (!root) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
      root.querySelectorAll('.lb-reveal').forEach((n) => n.classList.add('is-in'))
      return
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (e.isIntersecting) {
            e.target.classList.add('is-in')
            io.unobserve(e.target)
          }
        }
      },
      { threshold: 0.12, rootMargin: '0px 0px -6% 0px' },
    )
    root.querySelectorAll('.lb-reveal').forEach((n) => io.observe(n))
    return () => io.disconnect()
  }, [])
  return ref
}

function Header() {
  const [solid, setSolid] = useState(false)
  useEffect(() => {
    const onScroll = () => setSolid(window.scrollY > window.innerHeight * 0.72)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])
  return (
    <header className="lb-header" data-solid={solid}>
      <div className="lb-container lb-header-inner">
        <Link to="/" className="lb-logo">
          Инспектор<b>X</b>
        </Link>
        <nav className="lb-nav" aria-label="Основная навигация">
          <a href="#passport">Живой пример</a>
          <a href="#how">Как это работает</a>
          <a href="#pricing">Тариф</a>
          <Link to="/login">Войти</Link>
        </nav>
        <Link to="/catalog" className="lb-header-cta">
          Открыть каталог
        </Link>
      </div>
    </header>
  )
}

function Seal() {
  return (
    <svg className="lb-seal" viewBox="0 0 128 128" aria-hidden="true">
      <defs>
        <path id="lb-seal-arc" d="M 64 14 a 50 50 0 1 1 -0.01 0" fill="none" />
      </defs>
      <circle cx="64" cy="64" r="62" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.5" />
      <circle cx="64" cy="64" r="40" fill="none" stroke="currentColor" strokeWidth="1" opacity="0.5" />
      <g className="lb-seal-spin">
        <text
          fontFamily="'JetBrains Mono Variable', monospace"
          fontSize="9.2"
          letterSpacing="2.6"
          fill="currentColor"
        >
          <textPath href="#lb-seal-arc" startOffset="0" textLength="312" lengthAdjust="spacingAndGlyphs">
            ИНСПЕКТОРX · БАЗА ТРЕБОВАНИЙ · УЗБЕКИСТАН ·
          </textPath>
        </text>
      </g>
      <path
        d="M 52 64 l 8.5 8.5 L 77 56"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export function LandingB() {
  const revealRef = useRevealObserver()

  useEffect(() => {
    const prev = document.title
    document.title = 'ИнспекторX — все требования к вашему товару в Узбекистане'
    return () => {
      document.title = prev
    }
  }, [])

  return (
    <div className="lb" ref={revealRef}>
      <Header />

      {/* ── Герой ─────────────────────────────────────────────── */}
      <section className="lb-hero">
        <RouteCanvas className="lb-hero-canvas" />
        <div className="lb-container lb-hero-inner">
          <div className="lb-hero-copy">
            <p className="lb-eyebrow lb-eyebrow--dark lb-rise" style={{ '--d': 0 } as React.CSSProperties}>
              База требований госорганов · Узбекистан
            </p>
            <h1 className="lb-h1 lb-rise" style={{ '--d': 120 } as React.CSSProperties}>
              Все требования. <em>Один маршрут.</em>
            </h1>
            <p className="lb-hero-sub lb-rise" style={{ '--d': 260 } as React.CSSProperties}>
              Импортируете, производите или продаёте — <b>ИнспекторX</b> собирает требования
              государства к вашему товару в один паспорт: этапы, документы, суммы штрафов
              и точные цитаты законов.
            </p>
            <div className="lb-hero-ctas lb-rise" style={{ '--d': 380 } as React.CSSProperties}>
              <Link to="/catalog" className="lb-btn lb-btn--primary">
                Найти свой товар
                <ArrowRight size={17} aria-hidden />
              </Link>
              <a href="#passport" className="lb-btn lb-btn--glass">
                Смотреть живой пример
              </a>
            </div>
          </div>
          <div className="lb-hero-stats lb-rise" style={{ '--d': 520 } as React.CSSProperties}>
            {STATS.map((s) => (
              <div key={s.label}>
                <div className="lb-stat-num">{s.num}</div>
                <div className="lb-stat-label">{s.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── Цена незнания ─────────────────────────────────────── */}
      <section className="lb-section">
        <div className="lb-container">
          <div className="lb-section-head">
            <p className="lb-eyebrow lb-reveal">Цена незнания</p>
            <h2 className="lb-h2 lb-reveal" style={{ '--d': 80 } as React.CSSProperties}>
              Проверка приходит с готовым списком
            </h2>
            <p className="lb-lede lb-reveal" style={{ '--d': 160 } as React.CSSProperties}>
              Требования к одному товару разбросаны по десяткам нормативных актов.
              Проверяющий знает их наизусть — предприниматель часто узнаёт о них из протокола.
            </p>
          </div>
          <div className="lb-risk-grid">
            <article className="lb-risk-card lb-reveal">
              <div className="lb-risk-ref">Внезапность</div>
              <h3>Проверка не предупреждает</h3>
              <p>
                Инспектор приходит с готовым чек-листом. Единственная защита — держать
                перед глазами тот же список требований, что и у него.
              </p>
            </article>
            <article className="lb-risk-card lb-reveal" style={{ '--d': 120 } as React.CSSProperties}>
              <div className="lb-risk-ref">Ответственность</div>
              <h3>Незнание не освобождает</h3>
              <p>
                Штраф выписывают за факт нарушения. Объяснение «мы не знали об этом
                требовании» не принимается.
              </p>
            </article>
            <article className="lb-risk-card lb-reveal" style={{ '--d': 240 } as React.CSSProperties}>
              <div className="lb-risk-ref">Эскалация</div>
              <h3>Повторное нарушение — кратно дороже</h3>
              <p>
                За повторные нарушения — кратные штрафы, приостановка деятельности
                и конфискация партии товара.
              </p>
            </article>
          </div>
          <p className="lb-risk-note lb-reveal">
            Точные суммы санкций и статьи — в каждой карточке требования.
          </p>
        </div>
      </section>

      {/* ── Паспорт товара (демо) ─────────────────────────────── */}
      <section className="lb-section lb-section--tint" id="passport">
        <div className="lb-container">
          <div className="lb-section-head">
            <p className="lb-eyebrow lb-reveal">Живой пример</p>
            <h2 className="lb-h2 lb-reveal" style={{ '--d': 80 } as React.CSSProperties}>
              Паспорт вашего дела
            </h2>
            <p className="lb-lede lb-reveal" style={{ '--d': 160 } as React.CSSProperties}>
              Один экран вместо десятков актов: выберите этап — и увидите требования
              именно для него. Ниже реальные данные из базы, не макет.
            </p>
          </div>
          <div className="lb-reveal" style={{ '--d': 240 } as React.CSSProperties}>
            <PassportDemo />
          </div>
        </div>
      </section>

      {/* ── Как это работает ──────────────────────────────────── */}
      <section className="lb-section" id="how">
        <div className="lb-container">
          <div className="lb-section-head">
            <p className="lb-eyebrow lb-reveal">Как это работает</p>
            <h2 className="lb-h2 lb-reveal" style={{ '--d': 80 } as React.CSSProperties}>
              Три шага до чек-листа
            </h2>
          </div>
          <div className="lb-steps">
            <article className="lb-step lb-reveal">
              <div className="lb-step-num">01</div>
              <h3>Найдите товар</h3>
              <p>
                По названию или коду — например, ОКЭД <code>47.73</code> для аптеки.
                Каталог пополняется каждую неделю.
              </p>
            </article>
            <article className="lb-step lb-reveal" style={{ '--d': 120 } as React.CSSProperties}>
              <div className="lb-step-num">02</div>
              <h3>Выберите операцию</h3>
              <p>
                Производство, продажа, импорт, экспорт. Для границы — ещё и транспорт:
                авто, поезд или самолёт.
              </p>
            </article>
            <article className="lb-step lb-reveal" style={{ '--d': 240 } as React.CSSProperties}>
              <div className="lb-step-num">03</div>
              <h3>Работайте по паспорту</h3>
              <p>
                Этапы по порядку, документы, сроки, суммы штрафов и цитаты законов —
                в каждой карточке требования.
              </p>
            </article>
          </div>
        </div>
      </section>

      {/* ── Первоисточник ─────────────────────────────────────── */}
      <section className="lb-section lb-section--tint">
        <div className="lb-container">
          <div className="lb-section-head">
            <p className="lb-eyebrow lb-reveal">Внутри карточки</p>
            <h2 className="lb-h2 lb-reveal" style={{ '--d': 80 } as React.CSSProperties}>
              Не пересказ, а первоисточник
            </h2>
            <p className="lb-lede lb-reveal" style={{ '--d': 160 } as React.CSSProperties}>
              Каждое требование опирается на дословную цитату нормативного акта —
              с пунктом и работающей ссылкой на lex.uz.
            </p>
          </div>

          <div className="lb-inside">
            <div className="lb-cite-card lb-reveal">
              <p className="lb-eyebrow lb-eyebrow--dark">Цитата закона · из базы</p>
              <blockquote>
                «Маркировка ящика (короба) должна содержать следующие сведения: …
                информация о сертификации».
              </blockquote>
              <a
                className="lb-cite-ref"
                href="https://lex.uz/uz/docs/-6931425"
                target="_blank"
                rel="noreferrer"
              >
                ПКМ-290, Технический регламент · п. 36 · lex.uz
              </a>
              <div className="lb-cite-meta">
                Требование «Информация о сертификации» · этап «Маркировка и защита прав
                потребителей» · дословно проверено по первоисточнику
              </div>
            </div>

            <ul className="lb-checklist lb-reveal" style={{ '--d': 140 } as React.CSSProperties}>
              {[
                ['Шаги исполнения', 'порядок действий, сроки и стоимость'],
                ['Документы', 'что оформить и где получить'],
                ['Санкции', 'точные суммы штрафов и статьи'],
                ['Цитата закона', 'дословно, со ссылкой на lex.uz'],
                ['Ведомство', 'кто контролирует и как связаться'],
                ['Обновления', 'дайджест изменений на email и в Telegram'],
              ].map(([title, text]) => (
                <li key={title}>
                  <Check size={16} className="lb-check-ico" aria-hidden />
                  <span>
                    <b>{title}</b> — <span>{text}</span>
                  </span>
                </li>
              ))}
            </ul>
          </div>

          <div className="lb-cats lb-reveal">
            {CATEGORY_ORDER.map((cat) => (
              <div className="lb-cat" key={cat}>
                <i />
                {CATEGORY_LABEL[cat]}
              </div>
            ))}
          </div>
          <p className="lb-risk-note lb-reveal">
            Требования сгруппированы по понятным категориям — от сертификации до маркировки.
          </p>
        </div>
      </section>

      {/* ── Тариф ─────────────────────────────────────────────── */}
      <section className="lb-section" id="pricing">
        <div className="lb-container">
          <div className="lb-section-head">
            <p className="lb-eyebrow lb-reveal">Тариф</p>
            <h2 className="lb-h2 lb-reveal" style={{ '--d': 80 } as React.CSSProperties}>
              Каталог бесплатный. Глубина — по подписке
            </h2>
          </div>
          <div className="lb-price-grid">
            <div className="lb-price-card lb-reveal">
              <div className="lb-price-tag">Каталог</div>
              <div className="lb-price-num">Бесплатно</div>
              <div className="lb-price-per">без регистрации</div>
              <ul className="lb-price-list">
                <li>
                  <Check size={15} className="lb-check-ico" aria-hidden />
                  Поиск по каталогу — название, ОКЭД или код ТН ВЭД
                </li>
                <li>
                  <Check size={15} className="lb-check-ico" aria-hidden />
                  Структура паспорта: операции, транспорт, этапы
                </li>
                <li>
                  <Check size={15} className="lb-check-ico" aria-hidden />
                  Названия всех требований к товару
                </li>
              </ul>
              <Link to="/catalog" className="lb-btn lb-btn--line">
                Открыть каталог
              </Link>
            </div>
            <div className="lb-price-card lb-price-card--pro lb-reveal" style={{ '--d': 120 } as React.CSSProperties}>
              <div className="lb-price-tag">Ранний доступ</div>
              <div className="lb-price-num">490 000 сум</div>
              <div className="lb-price-per">в месяц за компанию</div>
              <ul className="lb-price-list">
                <li>
                  <Check size={15} className="lb-check-ico" aria-hidden />
                  Полные карточки: шаги, документы, сроки
                </li>
                <li>
                  <Check size={15} className="lb-check-ico" aria-hidden />
                  Санкции с точными суммами и статьями
                </li>
                <li>
                  <Check size={15} className="lb-check-ico" aria-hidden />
                  Цитаты законов со ссылками на lex.uz
                </li>
                <li>
                  <Check size={15} className="lb-check-ico" aria-hidden />
                  Уведомления об изменениях: email-дайджест и Telegram
                </li>
              </ul>
              <Link to="/pricing" className="lb-btn lb-btn--primary">
                Подключить ранний доступ
                <ArrowRight size={16} aria-hidden />
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* ── Вопросы и ответы ──────────────────────────────────── */}
      <section className="lb-section lb-section--tint" id="faq">
        <div className="lb-container">
          <div className="lb-section-head">
            <p className="lb-eyebrow lb-reveal">Вопросы и ответы</p>
            <h2 className="lb-h2 lb-reveal" style={{ '--d': 80 } as React.CSSProperties}>
              Частые вопросы
            </h2>
          </div>
          <div className="lb-faq lb-reveal" style={{ '--d': 160 } as React.CSSProperties}>
            {FAQ_ITEMS.map(([q, a]) => (
              <details key={q}>
                <summary>{q}</summary>
                <p className="lb-faq-a">{a}</p>
              </details>
            ))}
          </div>
        </div>
      </section>

      {/* ── Финал ─────────────────────────────────────────────── */}
      <section className="lb-final lb-section">
        <div className="lb-container">
          <div className="lb-reveal">
            <Seal />
          </div>
          <div className="lb-section-head">
            <h2 className="lb-h2 lb-reveal" style={{ '--d': 100 } as React.CSSProperties}>
              Начните с вашего товара
            </h2>
            <p className="lb-lede lb-reveal" style={{ '--d': 180 } as React.CSSProperties}>
              Найдите его в каталоге — структура требований открыта бесплатно.
            </p>
          </div>
          <div className="lb-final-ctas lb-reveal" style={{ '--d': 260 } as React.CSSProperties}>
            <Link to="/catalog" className="lb-btn lb-btn--primary">
              Открыть каталог
              <ArrowRight size={17} aria-hidden />
            </Link>
            <Link to="/pricing" className="lb-btn lb-btn--glass">
              Смотреть тариф
            </Link>
          </div>
        </div>
      </section>

      {/* ── Подвал ────────────────────────────────────────────── */}
      <footer className="lb-footer">
        <div className="lb-container">
          <div className="lb-footer-grid">
            <Link to="/" className="lb-logo">
              Инспектор<b>X</b>
            </Link>
            <nav className="lb-footer-links" aria-label="Подвал">
              <Link to="/catalog">Каталог</Link>
              <Link to="/pricing">Тариф</Link>
              <Link to="/login">Войти</Link>
              <Link to="/register">Регистрация</Link>
            </nav>
            <div>
              <a href="mailto:hello@inspectorx.uz">hello@inspectorx.uz</a>
              <br />
              <a href="https://t.me/inspectorx_uz" target="_blank" rel="noreferrer">
                Telegram · @inspectorx_uz
              </a>
            </div>
          </div>
          <div className="lb-footer-note">
            <span>© 2026 ИнспекторX · Сделано в Узбекистане</span>
            <span>Информация носит справочный характер и не является юридической консультацией.</span>
          </div>
        </div>
      </footer>
    </div>
  )
}
