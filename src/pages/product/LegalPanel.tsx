import { useState } from 'react'
import { ExternalLink } from 'lucide-react'
import { PaywallPanel } from '@/components/PaywallGate'
import type { Citation, Gated, HistoryEntry } from '@/data/types'
import { ru } from '@/i18n/ru'
import { formatDate } from '@/lib/format'

/**
 * Уровень 2 — юридический слой (§4): verbatim-цитата серифом,
 * реквизиты источника (АКТ / ПУНКТ / РЕДАКЦИЯ), история изменений.
 */
export function LegalPanel({
  citations,
  history,
}: {
  citations: Gated<Citation[]>
  history: Gated<HistoryEntry[]>
}) {
  return (
    <aside className="space-y-5">
      <p className="font-mono text-[10px] tracking-[0.12em] text-muted-foreground uppercase">
        {ru.requirement.card.legalPanelTitle}
      </p>

      {citations.state === 'locked' ? (
        <PaywallPanel />
      ) : (
        citations.value.map((c, i) => <CitationBlock key={i} citation={c} />)
      )}

      {history.state === 'ok' && history.value.length > 0 && (
        <section>
          <h4 className="font-mono text-[10px] tracking-[0.12em] text-muted-foreground uppercase">
            {ru.requirement.card.historyCount(history.value.length)}
          </h4>
          <ol className="mt-2 space-y-3">
            {history.value.map((h, i) => (
              <li key={i} className="rounded-md border bg-background/50 p-3">
                <p className="font-mono text-[11px] text-muted-foreground">
                  {formatDate(h.date)}
                </p>
                <p className="mt-1 text-sm font-medium">{h.title}</p>
                {h.was && (
                  <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
                    <span className="font-mono text-[10px] uppercase">
                      {ru.requirement.card.was}:
                    </span>{' '}
                    <span className="line-through decoration-foreground/30">{h.was}</span>
                  </p>
                )}
                {h.now && (
                  <p className="mt-1 text-xs leading-relaxed">
                    <span className="font-mono text-[10px] uppercase text-muted-foreground">
                      {ru.requirement.card.now}:
                    </span>{' '}
                    {h.now}
                  </p>
                )}
              </li>
            ))}
          </ol>
        </section>
      )}
    </aside>
  )
}

function CitationBlock({ citation }: { citation: Citation }) {
  const [showUz, setShowUz] = useState(false)
  const hasRu = Boolean(citation.verbatimRu)
  const hasUz = Boolean(citation.verbatimUz)
  const text = showUz && hasUz ? citation.verbatimUz : (citation.verbatimRu ?? citation.verbatimUz)

  return (
    <section className="rounded-md border bg-background/50">
      {text && (
        <blockquote className="border-l-2 border-foreground/60 px-4 py-3">
          <p className="font-serif text-[15px] leading-relaxed">«{text}»</p>
          {hasRu && hasUz && (
            <button
              type="button"
              onClick={() => setShowUz((v) => !v)}
              className="mt-2 font-mono text-[10px] tracking-[0.08em] text-muted-foreground uppercase underline-offset-2 hover:underline"
            >
              {showUz
                ? ru.requirement.card.verbatimTranslation
                : ru.requirement.card.verbatimOriginal}
            </button>
          )}
        </blockquote>
      )}
      <dl className="requisites grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 border-t px-4 py-3">
        <dt>{ru.requirement.card.sourceAct}</dt>
        <dd className="min-w-0 break-words">
          {citation.actTitle}
          {citation.actNumber ? ` № ${citation.actNumber}` : ''}
        </dd>
        <dt>{ru.requirement.card.sourceParagraph}</dt>
        <dd>{citation.paragraphRef}</dd>
        {citation.versionDate && (
          <>
            <dt>{ru.requirement.card.sourceRevision}</dt>
            <dd>{formatDate(citation.versionDate)}</dd>
          </>
        )}
      </dl>
      {citation.deepLink && (
        <div className="border-t px-4 py-2">
          <a
            href={citation.deepLink}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 font-mono text-[11px] text-muted-foreground hover:text-foreground"
          >
            {ru.requirement.card.openAct}
            <ExternalLink className="size-3" />
          </a>
        </div>
      )}
    </section>
  )
}
