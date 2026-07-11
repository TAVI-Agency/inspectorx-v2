import { FileText, Globe, MessageCircleQuestion, Phone, Scale } from 'lucide-react'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'
import { PaywallGate } from '@/components/PaywallGate'
import { useRequirementCard } from '@/data/hooks'
import type { RequirementRow } from '@/data/types'
import { ru } from '@/i18n/ru'
import { LegalPanel } from './LegalPanel'
import { TrustStamp } from './badges'
import { AskQuestionDialog, useAskDialogState } from './AskQuestionDialog'

/** Шаги из v1 приходят с префиксом «(Пункт 35, абзацы 14, ТР)\n…» — выносим в реквизит */
function splitSourcePrefix(text: string): { ref?: string; body: string } {
  const m = text.match(/^\((п|П)ункт[^)]{0,80}\)\s*\n?/)
  if (!m) return { body: text }
  return { ref: m[0].trim().slice(1, -1), body: text.slice(m[0].length).trim() }
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="font-mono text-[10px] tracking-[0.12em] text-muted-foreground uppercase">
      {children}
    </h4>
  )
}

/** Уровень 1 (карточка) + уровень 2 (правая панель) — §4 */
export function RequirementCardView({
  row,
  productId,
}: {
  row: RequirementRow
  productId: string
}) {
  const { data: card, isLoading } = useRequirementCard(row)
  const dialog = useAskDialogState()

  if (isLoading || !card) {
    return (
      <div className="space-y-3 border-t px-4 py-5 sm:px-6">
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
    <div className="border-t px-4 py-5 sm:px-6">
      <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_330px]">
        {/* Уровень 1: что делать */}
        <div className="min-w-0 space-y-6">
          <TrustStamp trust={row.trustLabel} date={row.trustDate} />

          {locked && <PaywallGate />}

          {detail?.description && (
            <section>
              <SectionTitle>{ru.requirement.card.description}</SectionTitle>
              <p className="mt-2 max-w-prose text-[15px] leading-relaxed whitespace-pre-line">
                {detail.description}
              </p>
            </section>
          )}

          {detail && detail.steps.length > 0 && (
            <section>
              <SectionTitle>{ru.requirement.card.howTo}</SectionTitle>
              <ol className="mt-3 space-y-4">
                {detail.steps.map((step, i) => {
                  const { ref, body } = splitSourcePrefix(step.text)
                  return (
                    <li key={i} className="flex gap-3">
                      <span className="mt-0.5 inline-flex size-6 shrink-0 items-center justify-center rounded-full border font-mono text-xs">
                        {i + 1}
                      </span>
                      <div className="min-w-0 space-y-1">
                        <p className="text-sm leading-relaxed whitespace-pre-line">
                          {body}
                        </p>
                        {(step.term || step.cost) && (
                          <p className="font-mono text-[11px] text-muted-foreground">
                            {step.term && `${ru.requirement.card.term}: ${step.term}`}
                            {step.term && step.cost && ' · '}
                            {step.cost && `${ru.requirement.card.cost}: ${step.cost}`}
                          </p>
                        )}
                        {ref && (
                          <p className="font-mono text-[10px] text-muted-foreground/80">
                            {ref}
                          </p>
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
              <SectionTitle>{ru.requirement.card.documents}</SectionTitle>
              <ul className="mt-3 space-y-2">
                {detail.documents.map((doc, i) => (
                  <li key={i} className="flex items-start gap-2.5 rounded-md border bg-background/50 px-3 py-2.5">
                    <FileText className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                    <div className="min-w-0">
                      <p className="text-sm font-medium">{doc.name}</p>
                      {doc.where && (
                        <p className="text-xs text-muted-foreground">
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
              <SectionTitle>{ru.requirement.card.authority}</SectionTitle>
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
              <SectionTitle>{ru.requirement.card.sanctions}</SectionTitle>
              <ul className="mt-3 space-y-2.5 border-l-2 border-sanction/60 pl-4">
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
            </section>
          )}

          {faqs.length > 0 && (
            <section>
              <SectionTitle>{ru.requirement.card.faq}</SectionTitle>
              <div className="mt-2 divide-y rounded-md border bg-background/50">
                {faqs.map((f, i) => (
                  <details key={i} className="group px-3 py-2.5">
                    <summary className="cursor-pointer list-none text-sm font-medium marker:hidden">
                      {f.question}
                    </summary>
                    <p className="mt-2 text-sm leading-relaxed text-muted-foreground">
                      {f.answer}
                    </p>
                    <TrustStamp trust={f.trustLabel} className="mt-2" />
                  </details>
                ))}
              </div>
            </section>
          )}

          <div className="flex flex-wrap gap-2 border-t pt-4">
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
        <LegalPanel citations={card.citations} history={card.history} />
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
