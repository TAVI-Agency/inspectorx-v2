import type { Deontic, PartyRole, RequirementStatus, TrustLabel } from '@/data/types'
import { ru } from '@/i18n/ru'
import { formatDate } from '@/lib/format'
import { cn } from '@/lib/utils'

/** Тип требования (деонтика). Зелёный — только льгота («в вашу пользу»). */
export function DeonticBadge({ deontic }: { deontic: Deontic }) {
  return (
    <span
      className={cn(
        'inline-flex h-[18px] shrink-0 items-center rounded px-1.5 text-[11px] font-medium',
        deontic === 'obligation' && 'bg-secondary text-secondary-foreground',
        deontic === 'prohibition' && 'border border-foreground/30 text-foreground',
        deontic === 'permission' && 'bg-positive/12 text-positive',
      )}
    >
      {ru.requirement.deontic[deontic]}
    </span>
  )
}

export function rolesLabel(roles: PartyRole[]): string {
  return roles.map((r) => ru.requirement.roles[r]).join(', ')
}

export function StatusLabel({
  status,
  className,
}: {
  status: RequirementStatus
  className?: string
}) {
  if (status.kind === 'active') {
    return (
      <span className={cn('text-xs text-muted-foreground', className)}>
        {ru.requirement.status.active}
      </span>
    )
  }
  return (
    <span className={cn('text-xs font-medium text-primary', className)}>
      {status.kind === 'changed'
        ? ru.requirement.status.changed(formatDate(status.date))
        : ru.requirement.status.upcoming(formatDate(status.date))}
    </span>
  )
}

/** Метка доверия контента (сквозной слой доверия из §5a) */
export function TrustStamp({
  trust,
  date,
  className,
}: {
  trust: TrustLabel
  date?: string
  className?: string
}) {
  if (trust === 'lawyer_verified') {
    return (
      <span className={cn('stamp text-positive', className)}>
        {ru.requirement.trust.lawyer_verified(formatDate(date) || '—')}
      </span>
    )
  }
  if (trust === 'official_answer') {
    return (
      <span className={cn('stamp text-positive', className)}>
        {ru.requirement.trust.official_answer}
      </span>
    )
  }
  return (
    <span className={cn('stamp text-muted-foreground', className)}>
      {ru.requirement.trust.ai_draft}
    </span>
  )
}
