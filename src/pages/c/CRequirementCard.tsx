import { useState } from 'react'
import {
  ChevronDown,
  ClipboardList,
  ExternalLink,
  FileDown,
  FileText,
  Gavel,
  Globe,
  MessageCircleQuestion,
  Phone,
  Scale,
} from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { useRequirementCard } from '@/data/hooks'
import type {
  Citation,
  CourtCase,
  DocumentTemplate,
  Gated,
  HistoryEntry,
  LawyerInstruction,
  RequirementRow,
} from '@/data/types'
import { formatDate } from '@/lib/format'
import { ru } from '@/i18n/ru'
import { AskQuestionDialog, useAskDialogState } from '@/components/AskQuestionDialog'
import { CEyebrow, CLifecycleBadge, CPaywallGate, CPaywallPanel, CTrustStamp } from './ui'
import { CLawyerReviewsSection } from './CLawyerReviews'

/** Шаги переноса v1 приходят с префиксом «(Пункт 35 …)\n» — выносим в реквизит */
function splitSourcePrefix(text: string): { ref?: string; body: string } {
  const m = text.match(/^\((п|П)ункт[^)]{0,80}\)\s*\n?/)
  if (!m) return { body: text }
  return { ref: m[0].trim().slice(1, -1), body: text.slice(m[0].length).trim() }
}

/**
 * Уровень 1 (инструкция) + уровень 2 (юридический слой) дизайна C.
 * Шаги исполнения — станции на мини-нити: та же метафора маршрута.
 */
export function CRequirementCard({
  row,
  productId,
}: {
  row: RequirementRow
  /** Не передаётся на странице услуги — вопрос уйдёт без привязки к товару */
  productId?: string
}) {
  const { data: card, isLoading } = useRequirementCard(row)
  const dialog = useAskDialogState()

  if (isLoading || !card) {
    return (
      <div className="space-y-3 border-t border-border px-4 py-5 sm:px-6">
        <Skeleton className="h-4 w-2/3" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
      </div>
    )
  }

  const detail = card.detail.state === 'ok' ? card.detail.value : null
  const faqs = card.faqs.state === 'ok' ? card.faqs.value : []
  const locked = card.detail.state === 'locked'

  return (
    <div className="border-t border-border bg-background/40 px-4 py-5 sm:px-6">
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-6">
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <CTrustStamp
                trust={row.trustLabel}
                date={row.trustDate ? formatDate(row.trustDate) : undefined}
              />
              <CLifecycleBadge
                lifecycle={row.lifecycle}
                effectiveFrom={row.effectiveFrom}
                transitionUntil={row.transitionUntil}
                validTo={row.validTo}
              />
            </div>
            {detail?.statusNote && (
              <p className="max-w-prose text-xs leading-relaxed text-muted-foreground">
                {detail.statusNote}
              </p>
            )}
          </div>

          {locked && <CPaywallGate />}

          {detail?.description && (
            <section>
              <CEyebrow>{ru.requirement.card.description}</CEyebrow>
              <p className="mt-2 max-w-prose text-[15px] leading-relaxed whitespace-pre-line">
                {detail.description}
              </p>
            </section>
          )}

          {detail && detail.steps.length > 0 && (
            <section>
              <CEyebrow>{ru.requirement.card.howTo}</CEyebrow>
              <ol className="relative mt-3 space-y-4">
                {/* Мини-нить шагов */}
                <span
                  aria-hidden
                  className="absolute top-2 bottom-2 left-[11px] w-px bg-primary/25"
                />
                {detail.steps.map((step, i) => {
                  const { ref, body } = splitSourcePrefix(step.text)
                  return (
                    <li key={i} className="relative flex gap-3.5">
                      <span className="relative z-10 mt-0.5 inline-flex size-6 shrink-0 items-center justify-center rounded-full border border-primary/45 bg-card font-mono text-xs font-semibold text-primary">
                        {i + 1}
                      </span>
                      <div className="min-w-0 space-y-1">
                        <p className="text-sm leading-relaxed whitespace-pre-line">{body}</p>
                        {(step.term || step.cost) && (
                          <p className="font-mono text-[11px] text-muted-foreground">
                            {step.term && `${ru.requirement.card.term}: ${step.term}`}
                            {step.term && step.cost && ' · '}
                            {step.cost && `${ru.requirement.card.cost}: ${step.cost}`}
                          </p>
                        )}
                        {ref && (
                          <p className="font-mono text-[10px] text-muted-foreground/80">{ref}</p>
                        )}
                      </div>
                    </li>
                  )
                })}
              </ol>
            </section>
          )}

          {detail && detail.documents.length > 0 && (
            <section>
              <CEyebrow>{ru.requirement.card.documents}</CEyebrow>
              <ul className="mt-3 space-y-2">
                {detail.documents.map((doc, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-2.5 rounded-lg border border-border bg-card px-3 py-2.5"
                  >
                    <FileText className="mt-0.5 size-4 shrink-0 text-primary/70" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{doc.name}</p>
                      {doc.where && (
                        <p className="mt-0.5 text-xs text-muted-foreground">
                          {ru.requirement.card.whereToGet}: {doc.where}
                        </p>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}

          {card.authority && (
            <section>
              <CEyebrow>{ru.requirement.card.authority}</CEyebrow>
              <div className="mt-2 space-y-1 text-sm">
                <p className="font-medium">{card.authority.name}</p>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-muted-foreground">
                  {card.authority.phone && (
                    <span className="inline-flex items-center gap-1.5 font-mono text-xs">
                      <Phone className="size-3" />
                      {card.authority.phone}
                    </span>
                  )}
                  {card.authority.website && (
                    <a
                      href={card.authority.website}
                      target="_blank"
                      rel="noreferrer"
                      className="inline-flex items-center gap-1.5 font-mono text-xs hover:text-foreground"
                    >
                      <Globe className="size-3" />
                      {card.authority.website.replace(/^https?:\/\//, '')}
                    </a>
                  )}
                </div>
              </div>
            </section>
          )}

          {detail && detail.sanctions.length > 0 && (
            <section>
              <CEyebrow>{ru.requirement.card.sanctions}</CEyebrow>
              <div className="mt-3 rounded-lg border border-sanction/25 bg-sanction/[0.04] p-4">
                <ul className="space-y-3">
                  {detail.sanctions.map((s, i) => (
                    <li key={i}>
                      <p className="text-sm font-medium text-sanction">
                        <Scale className="mr-1.5 inline size-3.5 align-[-2px]" />
                        {s.text}
                      </p>
                      {s.article && (
                        <p className="mt-0.5 font-mono text-[11px] text-muted-foreground">
                          {ru.requirement.card.sanctionArticle}: {s.article}
                        </p>
                      )}
                      {s.extra && (
                        <p className="mt-0.5 text-xs text-muted-foreground">{s.extra}</p>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            </section>
          )}

          {/* Под санкциями — судебная практика по той же статье, дальше шаблоны
              и инструкция юриста (TARGET_FORMAT §4б-в). Блоки внутри
              раскрытой карточки не скрываются — пустой рисует «Данных пока нет». */}
          {detail && <CCourtCasesSection cases={detail.courtCases ?? null} />}

          {detail && <CTemplatesSection templates={detail.templates ?? null} />}

          {detail && <CLawyerInstructionSection instruction={detail.lawyerInstruction ?? null} />}

          {faqs.length > 0 && (
            <section>
              <CEyebrow>{ru.requirement.card.faq}</CEyebrow>
              <div className="mt-2 divide-y divide-border rounded-lg border border-border bg-card">
                {faqs.map((f, i) => (
                  <details key={i} className="group px-3.5 py-3">
                    <summary className="flex cursor-pointer list-none items-center justify-between gap-2 text-sm font-medium marker:hidden">
                      {f.question}
                      <ChevronDown className="size-3.5 shrink-0 text-muted-foreground transition-transform duration-300 ease-[var(--ease-brand)] group-open:rotate-180" />
                    </summary>
                    <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{f.answer}</p>
                    <CTrustStamp trust={f.trustLabel} className="mt-2.5" />
                  </details>
                ))}
              </div>
            </section>
          )}

          <CLawyerReviewsSection row={row} />

          <div className="flex flex-wrap gap-2 border-t border-border pt-4">
            <Button variant="outline" size="sm" onClick={dialog.openAsk}>
              <MessageCircleQuestion />
              {ru.requirement.card.askQuestion}
            </Button>
            <Button variant="ghost" size="sm" onClick={dialog.openGr}>
              {ru.requirement.card.grRequest}
            </Button>
          </div>
        </div>

        {/* Уровень 2: юридический слой */}
        <div className="lg:sticky lg:top-6 lg:self-start">
          <CLegalPanel citations={card.citations} history={card.history} />
        </div>
      </div>

      <AskQuestionDialog
        open={dialog.open}
        onOpenChange={dialog.onOpenChange}
        grByDefault={dialog.gr}
        requirementId={row.id}
        productId={productId}
        requirementTitle={row.title}
      />
    </div>
  )
}

/**
 * Пустой блок ВНУТРИ раскрытой карточки — не скрывается (в отличие от
 * пустых разделов страницы товара, TARGET_FORMAT §3): подписчик должен
 * видеть, что блок существует и пока не наполнен, а не гадать, есть ли он.
 */
function CNoDataYet() {
  return (
    <p className="mt-3 rounded-lg border border-dashed border-border px-3.5 py-2.5 text-sm text-muted-foreground">
      {ru.requirement.noDataYet}
    </p>
  )
}

/** Судебная практика по статье санкции: до 5 кейсов, раскрывашка со счётчиком, только UZ-снапшот */
function CCourtCasesSection({ cases }: { cases: CourtCase[] | null }) {
  return (
    <section>
      <CEyebrow>{ru.requirement.courtCases.title}</CEyebrow>
      {!cases || cases.length === 0 ? (
        <CNoDataYet />
      ) : (
        <details className="group mt-3 overflow-hidden rounded-lg border border-border bg-card">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-3.5 py-3 text-sm font-medium marker:hidden">
            <span className="inline-flex items-center gap-2">
              <Gavel className="size-4 text-primary/70" />
              {ru.requirement.courtCases.button(cases.length)}
            </span>
            <ChevronDown className="size-3.5 shrink-0 text-muted-foreground transition-transform duration-300 ease-[var(--ease-brand)] group-open:rotate-180" />
          </summary>
          <ul className="divide-y divide-border border-t border-border">
            {cases.slice(0, 5).map((c, i) => (
              <li key={i} className="px-3.5 py-3">
                <p className="text-sm leading-relaxed">{c.summaryLine}</p>
                {(c.outcome || c.amount) && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    {[c.outcome, c.amount].filter(Boolean).join(' · ')}
                  </p>
                )}
                <a
                  href={c.caseUrl}
                  target="_blank"
                  rel="noopener"
                  className="mt-1.5 inline-flex items-center gap-1.5 font-mono text-[11px] text-primary underline-offset-2 hover:underline"
                >
                  {c.caseTitle}
                  <ExternalLink className="size-3" />
                </a>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  )
}

/** Шаблоны документов от Template hunter: []/null неотличимо от null для пользователя */
function CTemplatesSection({ templates }: { templates: DocumentTemplate[] | null }) {
  return (
    <section>
      <CEyebrow>{ru.requirement.templates.title}</CEyebrow>
      {!templates || templates.length === 0 ? (
        <CNoDataYet />
      ) : (
        <ul className="mt-3 space-y-2">
          {templates.map((t, i) => (
            <li
              key={i}
              className="flex items-start gap-2.5 rounded-lg border border-border bg-card px-3 py-2.5"
            >
              <FileDown className="mt-0.5 size-4 shrink-0 text-primary/70" />
              <div className="min-w-0">
                <a
                  href={t.sourceUrl}
                  target="_blank"
                  rel="noopener"
                  className="text-sm font-medium text-primary underline-offset-2 hover:underline"
                >
                  {t.name}
                </a>
                {t.note && <p className="mt-0.5 text-xs text-muted-foreground">{t.note}</p>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}

/** Рекомендация in-house юриста: вердикт сверху + шаги нумерованным списком */
function CLawyerInstructionSection({ instruction }: { instruction: LawyerInstruction | null }) {
  return (
    <section>
      <CEyebrow>{ru.requirement.lawyerInstruction.title}</CEyebrow>
      {!instruction || (!instruction.verdict && instruction.steps.length === 0) ? (
        <CNoDataYet />
      ) : (
        <div className="mt-3 space-y-3">
          {instruction.verdict && (
            <p className="flex items-start gap-2 rounded-lg border border-primary/25 bg-primary/[0.04] px-3.5 py-2.5 text-sm font-medium">
              <ClipboardList className="mt-0.5 size-4 shrink-0 text-primary/70" />
              {instruction.verdict}
            </p>
          )}
          {instruction.steps.length > 0 && (
            <ol className="space-y-2">
              {instruction.steps.map((step, i) => (
                <li key={i} className="flex gap-2.5 text-sm">
                  <span className="mt-0.5 inline-flex size-5 shrink-0 items-center justify-center rounded-full border border-primary/45 font-mono text-[11px] font-semibold text-primary">
                    {i + 1}
                  </span>
                  <span className="leading-relaxed">{step}</span>
                </li>
              ))}
            </ol>
          )}
        </div>
      )}
    </section>
  )
}

/** Юридический слой: точная цитата закона серифом + реквизиты + история */
function CLegalPanel({
  citations,
  history,
}: {
  citations: Gated<Citation[]>
  history: Gated<HistoryEntry[]>
}) {
  return (
    <aside className="space-y-4">
      <CEyebrow>{ru.requirement.card.legalPanelTitle}</CEyebrow>

      {citations.state === 'locked' ? (
        <CPaywallPanel />
      ) : (
        citations.value.map((c, i) => <CCitation key={i} citation={c} />)
      )}

      {history.state === 'ok' && history.value.length > 0 && (
        <section>
          <CEyebrow>{ru.requirement.card.historyCount(history.value.length)}</CEyebrow>
          <ol className="mt-2 space-y-2.5">
            {history.value.map((h, i) => (
              <li key={i} className="rounded-lg border border-border bg-card p-3">
                <p className="font-mono text-[11px] text-muted-foreground">{formatDate(h.date)}</p>
                <p className="mt-1 text-sm font-medium">{h.title}</p>
                {h.was && (
                  <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
                    <span className="font-mono text-[10px] uppercase">
                      {ru.requirement.card.was}:
                    </span>{' '}
                    <span className="line-through decoration-sanction/40">{h.was}</span>
                  </p>
                )}
                {h.now && (
                  <p className="mt-1 text-xs leading-relaxed">
                    <span className="font-mono text-[10px] text-muted-foreground uppercase">
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

function CCitation({ citation }: { citation: Citation }) {
  const [showUz, setShowUz] = useState(false)
  const hasRu = Boolean(citation.verbatimRu)
  const hasUz = Boolean(citation.verbatimUz)
  const text = showUz && hasUz ? citation.verbatimUz : (citation.verbatimRu ?? citation.verbatimUz)

  return (
    <section className="overflow-hidden rounded-lg border border-border bg-card">
      {text && (
        <blockquote className="border-l-2 border-primary/60 px-4 py-3">
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
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 border-t border-border px-4 py-3 font-mono text-xs">
        <dt className="text-[10px] tracking-[0.08em] text-muted-foreground uppercase">
          {ru.requirement.card.sourceAct}
        </dt>
        <dd className="min-w-0 break-words">
          {citation.actTitle}
          {citation.actNumber ? ` № ${citation.actNumber}` : ''}
        </dd>
        <dt className="text-[10px] tracking-[0.08em] text-muted-foreground uppercase">
          {ru.requirement.card.sourceParagraph}
        </dt>
        <dd>{citation.paragraphRef}</dd>
        {citation.versionDate && (
          <>
            <dt className="text-[10px] tracking-[0.08em] text-muted-foreground uppercase">
              {ru.requirement.card.sourceRevision}
            </dt>
            <dd>{formatDate(citation.versionDate)}</dd>
          </>
        )}
      </dl>
      {citation.deepLink && (
        <div className="border-t border-border px-4 py-2">
          <a
            href={citation.deepLink}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1.5 font-mono text-[11px] text-primary underline-offset-2 hover:underline"
          >
            {ru.requirement.card.openAct}
            <ExternalLink className="size-3" />
          </a>
        </div>
      )}
    </section>
  )
}
