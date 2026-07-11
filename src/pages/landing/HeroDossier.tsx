import { ru } from '@/i18n/ru'

/**
 * Фирменный элемент лендинга — «живое досье» товара.
 * Строки требований самособираются на загрузке (staggered), сверху опускается
 * таможенный штамп «Проверено». Метафора продукта: паспорт/дело товара.
 * Чистая декорация — не тянет данные; смысл несёт реальная витрина.
 */
const rowMeta: { deontic: 'obligation' | 'prohibition' | 'permission'; stage: string }[] = [
  { deontic: 'obligation', stage: 'Маркировка' },
  { deontic: 'obligation', stage: 'Оценка соответствия' },
  { deontic: 'prohibition', stage: 'Реализация' },
  { deontic: 'obligation', stage: 'Импорт' },
]

const deonticColor: Record<string, string> = {
  obligation: 'bg-foreground/70',
  prohibition: 'bg-sanction',
  permission: 'bg-positive',
}

export function HeroDossier() {
  const d = ru.marketing.dossier
  return (
    <div className="dossier-card relative w-full max-w-md rounded-xl border bg-paper p-5 shadow-[0_1px_0_rgba(0,0,0,0.02),0_24px_60px_-30px_rgba(28,27,25,0.35)] sm:p-6">
      {/* штамп */}
      <span className="dossier-stamp stamp absolute -top-3 right-5 rotate-[-6deg] bg-paper text-primary sm:right-7">
        {d.stamp} 07.2026
      </span>

      {/* шапка досье */}
      <p className="font-mono text-[10px] tracking-[0.14em] text-muted-foreground uppercase">
        {d.caption}
      </p>
      <div className="mt-1.5 flex items-baseline justify-between gap-3">
        <h3 className="font-serif text-xl font-medium tracking-tight">{d.product}</h3>
        <span className="shrink-0 font-mono text-xs text-muted-foreground">{d.code}</span>
      </div>

      {/* метрики */}
      <dl className="mt-4 grid grid-cols-3 gap-2 border-y py-3">
        {[
          { v: '203', l: d.metricReq },
          { v: '18', l: d.metricDocs },
          { v: '100 БРВ', l: d.metricSanction },
        ].map((m) => (
          <div key={m.l}>
            <dt className="sr-only">{m.l}</dt>
            <dd className="text-lg font-semibold tracking-tight tabular-nums">{m.v}</dd>
            <dd className="mt-0.5 text-[11px] leading-tight text-muted-foreground">{m.l}</dd>
          </div>
        ))}
      </dl>

      {/* самособирающийся чек-лист */}
      <ul className="mt-2">
        {d.rows.map((row, i) => (
          <li
            key={row}
            className="dossier-row flex items-center gap-3 border-b border-border/60 py-2.5 last:border-0"
            style={{ animationDelay: `${300 + i * 140}ms` }}
          >
            <span className="font-mono text-[11px] text-muted-foreground tabular-nums">
              {String(i + 1).padStart(2, '0')}
            </span>
            <span
              className={`size-1.5 shrink-0 rounded-full ${deonticColor[rowMeta[i].deontic]}`}
              aria-hidden
            />
            <span className="min-w-0 flex-1 truncate text-sm">{row}</span>
            <span className="shrink-0 font-mono text-[10px] tracking-wide text-muted-foreground uppercase">
              {rowMeta[i].stage}
            </span>
          </li>
        ))}
        <li
          className="dossier-row py-2 text-center text-xs text-muted-foreground"
          style={{ animationDelay: `${300 + rowMeta.length * 140}ms` }}
        >
          … и ещё 199
        </li>
      </ul>
    </div>
  )
}
