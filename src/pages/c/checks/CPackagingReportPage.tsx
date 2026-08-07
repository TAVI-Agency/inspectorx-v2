import { useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ArrowRight, Camera, ExternalLink } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import {
  useEvidenceCropUrls,
  useFindingAction,
  useInspectionBundle,
  useInspectionEvents,
  usePhotoFacts,
  useFactOverride,
  useRetake,
  useStartInspection,
} from '@/data/hooks'
import {
  groupRetakeBySurface,
  isPreliminary,
  reportCounters,
  type InspectionBundle,
  type PhotoFactRow,
  type PhotoFindingRow,
  type PhotoNotCheckableRow,
} from '@/data'
import { ru } from '@/i18n/ru'
import { formatDate, formatDateTime, pluralize } from '@/lib/format'
import { cn } from '@/lib/utils'
import {
  decidedByLabel,
  faceLabel,
  readerCoverageSummary,
  severityLabel,
  splitFindings,
} from './report-utils'
import { CCard, CEyebrow, CStatTile, CountUp } from '../ui'
import { CPackagingWaiting } from './CPackagingWaiting'

const t = ru.packagingCheck

/**
 * Отчёт по постоянной ссылке `/checks/packaging/:inspectionId` (Задача 13,
 * план §7). Пока `status in (queued, running, failed)` — `CPackagingWaiting`
 * (живые стадии/причина отказа); на `done` — четыре списка находок в
 * порядке §7 + аудиторский след. `useInspectionEvents` гасится сразу, как
 * только прогон перестал идти (`enabled = polling`, только `queued`/
 * `running`) — обязанность потребителя (докстрока хука в `hooks.ts`).
 * `failed` — тоже терминальный статус: `CPackagingWaiting` в этой ветке
 * читает только `bundle.inspection.last_error`, события ей не нужны, а
 * держать поллинг живым после отказа означало бы бить `photo_inspection_events`
 * каждые 1.5с вечно без единой новой строки.
 */
export function CPackagingReportPage() {
  const { inspectionId } = useParams<{ inspectionId: string }>()
  const bundle = useInspectionBundle(inspectionId)
  const status = bundle.data?.inspection.status
  const showWaiting = status === 'queued' || status === 'running' || status === 'failed'
  const polling = status === 'queued' || status === 'running'
  const events = useInspectionEvents(inspectionId, polling)

  return (
    <div className="mx-auto max-w-3xl px-4 py-7 sm:px-8">
      <div className="flex items-start justify-between gap-3">
        <div>
          <CEyebrow>{ru.nav.checksSection}</CEyebrow>
          <h1 className="font-display mt-1 text-[22px] leading-tight font-medium tracking-tight sm:text-[28px]">
            {t.title}
          </h1>
          {inspectionId && (
            <p className="mt-1 font-mono text-xs text-muted-foreground">{inspectionId}</p>
          )}
        </div>
        <Button variant="outline" size="sm" nativeButton={false} render={<Link to="/checks/packaging" />}>
          {t.startOverCta}
        </Button>
      </div>

      <div className="mt-6">
        {bundle.isLoading && (
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {Array.from({ length: 4 }, (_, i) => (
                <Skeleton key={i} className="h-20" />
              ))}
            </div>
            <Skeleton className="h-40 w-full" />
          </div>
        )}

        {bundle.isError && (
          <CCard className="p-6 text-center">
            <p className="text-sm text-destructive">{t.reportError}</p>
            <Button variant="outline" className="mt-4" onClick={() => void bundle.refetch()}>
              {ru.common.retry}
            </Button>
          </CCard>
        )}

        {!bundle.isLoading && !bundle.isError && !bundle.data && (
          <CCard className="p-8 text-center">
            <p className="text-sm text-muted-foreground">{t.reportNotFound}</p>
          </CCard>
        )}

        {bundle.data && showWaiting && <CPackagingWaiting bundle={bundle.data} events={events.data} />}

        {bundle.data && status === 'done' && <ReportBody bundle={bundle.data} />}
      </div>
    </div>
  )
}

// Enum движка (models.py, inspectorx-vision): critical | major | minor | info
const SEVERITY_TONE: Record<string, string> = {
  critical: 'bg-sanction/10 text-sanction ring-1 ring-sanction/25 ring-inset',
  major: 'bg-brass/10 text-brass ring-1 ring-brass/25 ring-inset',
  minor: 'bg-secondary text-secondary-foreground',
  info: 'bg-secondary text-muted-foreground',
}

function ReportBody({ bundle }: { bundle: InspectionBundle }) {
  const { inspection, assets } = bundle
  const counters = reportCounters(bundle)
  const lists = splitFindings(bundle.findings, bundle.notCheckable)
  const preliminary = isPreliminary(bundle)
  const sourceKind = inspection.source_kind === 'master_pdf' ? 'master_pdf' : 'photo'
  const coverage = readerCoverageSummary(sourceKind, inspection.reader_coverage, assets.length)

  const cropPaths = bundle.findings
    .map((f) => f.evidence_crop_path)
    .filter((p): p is string => Boolean(p))
  const cropUrls = useEvidenceCropUrls(cropPaths)

  const retakeGroups = groupRetakeBySurface(lists.needsHuman)
  const [factDialogOpen, setFactDialogOpen] = useState(false)

  const sourceKindWord = sourceKind === 'master_pdf' ? t.sourcePdf : t.sourcePhoto
  const sourceHint =
    coverage?.kind === 'master_pdf'
      ? t.sourceMasterPdf(coverage.pages)
      : coverage?.kind === 'photo'
        ? t.sourcePhotoCoverage(coverage.have, coverage.of)
        : undefined

  return (
    <div className="space-y-8">
      {/* Наверху — четыре числа, без процентной оценки (план §7) */}
      <div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <CStatTile
            label={t.violationsLabel}
            tone={counters.violations > 0 ? 'sanction' : 'positive'}
            value={<CountUp value={counters.violations} />}
            index={0}
          />
          <CStatTile
            label={t.checkedLabel}
            value={t.counterCheckedOf(counters.decided, counters.checked)}
            index={1}
          />
          <CStatTile label={t.needsHumanLabel} value={<CountUp value={counters.needsHuman} />} index={2} />
          <CStatTile label={t.sourceLabel} value={sourceKindWord} hint={sourceHint} index={3} />
        </div>
        <p className="mt-2 text-xs text-muted-foreground">{t.coveragePdfNote}</p>
      </div>

      {/* Бейджи предварительности/устаревания/новой ревизии */}
      {(preliminary || inspection.stale_since || inspection.superseded_by) && (
        <div className="flex flex-wrap gap-2">
          {preliminary && (
            <span className="inline-flex h-6 items-center rounded-[6px] bg-brass/10 px-2 text-xs font-medium text-brass ring-1 ring-brass/25 ring-inset">
              {t.preliminaryBadge}
            </span>
          )}
          {inspection.stale_since && (
            <span className="inline-flex h-6 items-center rounded-[6px] bg-sanction/10 px-2 text-xs font-medium text-sanction ring-1 ring-sanction/25 ring-inset">
              {t.staleBadge(formatDate(inspection.stale_since))}
            </span>
          )}
          {inspection.superseded_by && (
            <Link
              to={`/checks/packaging/${inspection.superseded_by}`}
              className="inline-flex h-6 items-center gap-1 rounded-[6px] bg-primary/10 px-2 text-xs font-medium text-primary hover:underline"
            >
              {t.supersededBadge}
              <ArrowRight className="size-3.5" />
            </Link>
          )}
        </div>
      )}

      {/* Список 1 — нарушения */}
      <Section title={t.reportViolations} count={lists.violations.length}>
        {lists.violations.length === 0 ? (
          <EmptyNote />
        ) : (
          <div className="space-y-3">
            {lists.violations.map((f) => (
              <FindingCard key={f.id} finding={f} productId={inspection.product_id} cropUrls={cropUrls.data} />
            ))}
          </div>
        )}
      </Section>

      {/* Список 2 — требует досъёмки или человека, по граням */}
      <Section title={t.reportNeedsHuman} count={lists.needsHuman.length}>
        {lists.needsHuman.length === 0 ? (
          <EmptyNote />
        ) : (
          <div className="space-y-3">
            <div className="flex justify-end">
              <Button variant="outline" size="sm" onClick={() => setFactDialogOpen(true)}>
                {t.fixFactCta}
              </Button>
            </div>
            {retakeGroups.map((g) => (
              <RetakeGroup
                key={g.surface}
                inspectionId={inspection.id}
                revision={inspection.revision}
                surface={g.surface}
                findings={g.findings}
              />
            ))}
          </div>
        )}
      </Section>
      <FactOverrideDialog
        inspectionId={inspection.id}
        open={factDialogOpen}
        onOpenChange={setFactDialogOpen}
      />

      {/* Список 3 — граница метода */}
      <Section title={t.reportNotCheckable} count={lists.notCheckable.length}>
        {lists.notCheckable.length === 0 ? (
          <EmptyNote />
        ) : (
          <div className="space-y-2">
            {lists.notCheckable.map((n) => (
              <NotCheckableRow key={n.id} row={n} />
            ))}
          </div>
        )}
      </Section>

      {/* Список 4 — без эталона */}
      <Section title={t.reportNoGold} count={lists.noGold.length}>
        {lists.noGold.length === 0 ? (
          <EmptyNote />
        ) : (
          <div className="space-y-2">
            {lists.noGold.map((n) => (
              <NotCheckableRow key={n.id} row={n} />
            ))}
          </div>
        )}
      </Section>

      <AuditSection inspection={inspection} assets={assets} />
    </div>
  )
}

function Section({
  title,
  count,
  children,
}: {
  title: string
  count: number
  children: React.ReactNode
}) {
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <h2 className="font-display text-lg font-medium tracking-tight">{title}</h2>
        <span className="text-xs font-medium text-muted-foreground">{count}</span>
      </div>
      <div className="mt-3">{children}</div>
    </div>
  )
}

function EmptyNote() {
  return <p className="text-sm text-muted-foreground">—</p>
}

interface EvidenceEntry {
  text?: string
  page?: number
  frame_idx?: number
  [key: string]: unknown
}

function FindingCard({
  finding,
  productId,
  cropUrls,
}: {
  finding: PhotoFindingRow
  productId: string | null
  cropUrls: Record<string, string> | undefined
}) {
  const action = useFindingAction()
  const [mode, setMode] = useState<'idle' | 'accepting'>('idle')
  const [reason, setReason] = useState('')
  const [done, setDone] = useState<'fixed' | 'accepted_with_reason' | 'escalated' | null>(null)

  const evidenceList: EvidenceEntry[] = Array.isArray(finding.evidence)
    ? (finding.evidence as EvidenceEntry[])
    : []
  const cropUrl = finding.evidence_crop_path ? cropUrls?.[finding.evidence_crop_path] : undefined

  function run(a: 'fixed' | 'accepted_with_reason' | 'escalated', r?: string) {
    action.mutate({ findingId: finding.id, action: a, reason: r }, { onSuccess: () => setDone(a) })
  }

  return (
    <CCard className="p-4">
      <div className="flex flex-wrap items-center gap-1.5">
        <span
          className={cn(
            'inline-flex h-[19px] items-center rounded-[6px] px-1.5 text-[11px] font-medium',
            SEVERITY_TONE[finding.severity] ?? 'bg-secondary text-muted-foreground',
          )}
        >
          {severityLabel(finding.severity)}
        </span>
        <span className="text-xs text-muted-foreground">{decidedByLabel(finding.decided_by)}</span>
      </div>

      <p className="mt-2 text-sm">{finding.message || finding.rule_ref}</p>

      <p className="mt-2 text-xs text-muted-foreground">
        {t.ruleRefLabel}: {finding.rule_ref}
      </p>

      {finding.requirement_id && productId ? (
        <Link
          to={`/product/${productId}?req=${finding.requirement_id}`}
          className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-primary hover:underline"
        >
          {ru.cabinet.toRequirement}
          <ExternalLink className="size-3" />
        </Link>
      ) : (
        <p className="mt-1 text-xs text-muted-foreground">{t.noRequirementLink}</p>
      )}

      {evidenceList.map(
        (e, i) =>
          typeof e.text === 'string' &&
          e.text.length > 0 && (
            <blockquote
              key={i}
              className="mt-2 border-l-2 border-border pl-2.5 text-xs leading-relaxed text-muted-foreground italic"
            >
              «{e.text}»
              {(e.page !== undefined || e.frame_idx !== undefined) && (
                <span className="not-italic">
                  {' '}
                  — {e.page !== undefined ? `стр. ${e.page}` : `кадр ${e.frame_idx}`}
                </span>
              )}
            </blockquote>
          ),
      )}

      {cropUrl && (
        // eslint-disable-next-line @next/next/no-img-element -- нет next в проекте, обычный img
        <img
          src={cropUrl}
          alt={t.evidenceCrop}
          className="mt-2 max-h-40 rounded-lg border border-border object-contain"
        />
      )}

      {finding.recommendation && (
        <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{finding.recommendation}</p>
      )}

      {done ? (
        <p className="mt-3 text-xs font-medium text-positive">{t.actionDone}</p>
      ) : (
        <>
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" variant="outline" disabled={action.isPending} onClick={() => run('fixed')}>
              {t.fixedCta}
            </Button>
            <Button
              size="sm"
              variant="outline"
              disabled={action.isPending}
              onClick={() => setMode(mode === 'accepting' ? 'idle' : 'accepting')}
            >
              {t.acceptCta}
            </Button>
            <Button size="sm" variant="outline" disabled={action.isPending} onClick={() => run('escalated')}>
              {t.escalateCta}
            </Button>
          </div>

          {mode === 'accepting' && (
            <div className="mt-2 space-y-1.5">
              <label className="text-xs font-medium text-muted-foreground">{t.acceptReasonLabel}</label>
              <textarea
                value={reason}
                onChange={(e) => setReason(e.target.value)}
                rows={2}
                placeholder={t.acceptReasonPlaceholder}
                className="w-full resize-none rounded-lg border border-input bg-transparent px-3 py-2 text-xs outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
              />
              {reason.trim().length > 0 && reason.trim().length < 10 && (
                <p className="text-xs text-destructive">{t.acceptReasonRequired}</p>
              )}
              <Button
                size="sm"
                disabled={reason.trim().length < 10 || action.isPending}
                onClick={() => run('accepted_with_reason', reason.trim())}
              >
                {action.isPending ? ru.common.sending : t.acceptCta}
              </Button>
            </div>
          )}

          {action.isError && <p className="mt-2 text-xs text-destructive">{t.actionError}</p>}
        </>
      )}
    </CCard>
  )
}

function NotCheckableRow({ row }: { row: PhotoNotCheckableRow }) {
  return (
    <CCard className="p-3.5">
      <p className="text-sm">{row.reason}</p>
      <p className="mt-1 text-xs text-muted-foreground">
        {t.ruleRefLabel}: {row.rule_ref || '—'}
      </p>
    </CCard>
  )
}

function RetakeGroup({
  inspectionId,
  revision,
  surface,
  findings,
}: {
  inspectionId: string
  revision: number
  surface: string
  findings: PhotoFindingRow[]
}) {
  const navigate = useNavigate()
  const retake = useRetake()
  const start = useStartInspection()
  const inputRef = useRef<HTMLInputElement>(null)
  const [error, setError] = useState<string | null>(null)
  const limitReached = revision >= 3

  async function submit(list: FileList | null) {
    if (!list || list.length === 0) return
    const picked = Array.from(list)
    setError(null)
    try {
      const newId = await retake.mutateAsync({
        inspectionId,
        files: picked,
        faces: picked.map(() => surface),
      })
      void start.mutateAsync(newId).catch(() => {})
      navigate(`/checks/packaging/${newId}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'unknown')
    }
  }

  return (
    <CCard className="p-4">
      <p className="text-sm font-semibold">{faceLabel(surface)}</p>
      <p className="mt-1 text-xs text-muted-foreground">
        {t.missingFace(faceLabel(surface), pluralize(findings.length, 'пункт', 'пункта', 'пунктов'))}
      </p>
      <ul className="mt-2 space-y-1">
        {findings.map((f) => (
          <li key={f.id} className="text-xs text-muted-foreground">
            {f.message || f.rule_ref}
          </li>
        ))}
      </ul>

      <input
        ref={inputRef}
        type="file"
        accept="image/*,.heic,.heif"
        multiple
        capture="environment"
        className="hidden"
        onChange={(e) => {
          void submit(e.target.files)
          e.target.value = ''
        }}
      />
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={limitReached || retake.isPending}
          onClick={() => inputRef.current?.click()}
        >
          <Camera />
          {retake.isPending ? t.uploading : t.retakeCta}
        </Button>
        {limitReached && <span className="text-xs text-muted-foreground">{t.revisionLimitHint}</span>}
      </div>
      {error && <p className="mt-2 text-xs text-destructive">{error}</p>}
    </CCard>
  )
}

function FactOverrideDialog({
  inspectionId,
  open,
  onOpenChange,
}: {
  inspectionId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const facts = usePhotoFacts(inspectionId, open)
  const override = useFactOverride()
  const navigate = useNavigate()
  const [edits, setEdits] = useState<Record<string, string>>({})
  const [note, setNote] = useState('')

  function rawOf(fact: PhotoFactRow): string {
    return edits[fact.slot_id] ?? JSON.stringify(fact.payload)
  }

  async function submit() {
    if (!facts.data) return
    const changed = facts.data.filter((f) => {
      const raw = edits[f.slot_id]
      return raw !== undefined && raw !== JSON.stringify(f.payload)
    })
    if (changed.length === 0 || note.trim().length === 0) return
    try {
      const newId = await override.mutateAsync({
        inspectionId,
        overrides: changed.map((f) => ({
          slotId: f.slot_id,
          payload: parsePayload(edits[f.slot_id]),
          note: note.trim(),
        })),
      })
      onOpenChange(false)
      navigate(`/checks/packaging/${newId}`)
    } catch {
      // ошибка показана ниже через override.isError
    }
  }

  const changedCount = facts.data
    ? facts.data.filter((f) => {
        const raw = edits[f.slot_id]
        return raw !== undefined && raw !== JSON.stringify(f.payload)
      }).length
    : 0

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t.fixFactDialogTitle}</DialogTitle>
          <DialogDescription>{t.fixFactDialogText}</DialogDescription>
        </DialogHeader>

        {facts.isLoading && <Skeleton className="h-24 w-full" />}

        {!facts.isLoading && (facts.data?.length ?? 0) === 0 && (
          <p className="text-sm text-muted-foreground">{t.fixFactNoSlots}</p>
        )}

        {!facts.isLoading && facts.data && facts.data.length > 0 && (
          <div className="max-h-72 space-y-3 overflow-y-auto">
            {facts.data.map((f) => (
              <div key={f.id}>
                <label className="text-xs font-medium text-muted-foreground">{f.slot_id}</label>
                <input
                  value={rawOf(f)}
                  onChange={(e) => setEdits((prev) => ({ ...prev, [f.slot_id]: e.target.value }))}
                  className="mt-1 w-full rounded-lg border border-input bg-transparent px-3 py-1.5 font-mono text-xs outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                />
              </div>
            ))}
          </div>
        )}

        {facts.data && facts.data.length > 0 && (
          <div>
            <label className="text-xs font-medium text-muted-foreground">{t.fixFactNoteLabel}</label>
            <textarea
              value={note}
              onChange={(e) => setNote(e.target.value)}
              rows={2}
              placeholder={t.fixFactNotePlaceholder}
              className="mt-1 w-full resize-none rounded-lg border border-input bg-transparent px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            />
            {note.trim().length === 0 && changedCount > 0 && (
              <p className="mt-1 text-xs text-destructive">{t.fixFactNoteRequired}</p>
            )}
          </div>
        )}

        {override.isError && <p className="text-xs text-destructive">{t.actionError}</p>}

        <DialogFooter>
          <Button
            disabled={changedCount === 0 || note.trim().length === 0 || override.isPending}
            onClick={() => void submit()}
          >
            {override.isPending ? t.fixFactSubmitting : t.fixFactSubmit}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function parsePayload(raw: string): unknown {
  try {
    return JSON.parse(raw)
  } catch {
    return raw
  }
}

function AuditSection({
  inspection,
  assets,
}: {
  inspection: InspectionBundle['inspection']
  assets: InspectionBundle['assets']
}) {
  return (
    <div>
      <h2 className="font-display text-lg font-medium tracking-tight">{t.auditTitle}</h2>
      <CCard className="mt-3 p-4">
        <dl className="grid grid-cols-1 gap-x-6 gap-y-2.5 text-sm sm:grid-cols-2">
          <Row label={t.evaluatedAtLabel} value={formatDate(inspection.evaluated_at) || '—'} />
          <Row label={t.checkedAtLabel} value={formatDateTime(inspection.checked_at) || '—'} />
          <Row label={t.ruleset} value={`${inspection.ruleset_version ?? '—'} · ${inspection.ruleset_sha256.slice(0, 12)}…`} />
          <Row label={t.costUsd} value={inspection.cost_usd != null ? `$${inspection.cost_usd.toFixed(4)}` : '—'} />
          <Row label={t.degradedMode} value={inspection.degraded_mode ?? '—'} />
          <Row label={t.signedBy} value={inspection.signed_by ?? t.signedNo} />
        </dl>

        {inspection.reader_coverage != null && (
          <details className="mt-3">
            <summary className="cursor-pointer text-xs font-medium text-muted-foreground">
              {t.readerCoverage}
            </summary>
            <pre className="mt-1.5 overflow-x-auto rounded-lg bg-secondary/50 p-2.5 text-[11px] leading-relaxed">
              {JSON.stringify(inspection.reader_coverage, null, 2)}
            </pre>
          </details>
        )}

        {inspection.model_versions != null && (
          <details className="mt-2">
            <summary className="cursor-pointer text-xs font-medium text-muted-foreground">
              {t.modelVersions}
            </summary>
            <pre className="mt-1.5 overflow-x-auto rounded-lg bg-secondary/50 p-2.5 text-[11px] leading-relaxed">
              {JSON.stringify(inspection.model_versions, null, 2)}
            </pre>
          </details>
        )}

        {inspection.policy_applied != null && (
          <details className="mt-2">
            <summary className="cursor-pointer text-xs font-medium text-muted-foreground">
              {t.policyApplied}
            </summary>
            <pre className="mt-1.5 overflow-x-auto rounded-lg bg-secondary/50 p-2.5 text-[11px] leading-relaxed">
              {JSON.stringify(inspection.policy_applied, null, 2)}
            </pre>
          </details>
        )}

        {assets.length > 0 && (
          <details className="mt-2">
            <summary className="cursor-pointer text-xs font-medium text-muted-foreground">
              {t.fileHashes}
            </summary>
            <ul className="mt-1.5 space-y-1 font-mono text-[11px] text-muted-foreground">
              {assets.map((a) => (
                <li key={a.idx}>
                  {t.frameLabel(a.idx)}: {a.sha256 ?? '—'}
                </li>
              ))}
            </ul>
          </details>
        )}

        <p className="mt-3 text-xs leading-relaxed text-muted-foreground">{t.normEditionMissing}</p>
      </CCard>
    </div>
  )
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 sm:block">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-right font-medium sm:text-left">{value}</dd>
    </div>
  )
}
