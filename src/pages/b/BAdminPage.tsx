import { Inbox } from 'lucide-react'
import { useSubscriptionRequests, useContentRequests } from '@/data/hooks'
import type { ContentRequestRow, SubscriptionRequestRow } from '@/data/real'
import { cn } from '@/lib/utils'
import { BCard, StatTile } from './ui'

const statusTone: Record<string, string> = {
  new: 'bg-primary/10 text-primary',
  contacted: 'bg-secondary text-muted-foreground',
  activated: 'bg-positive/10 text-positive',
  rejected: 'bg-sanction/10 text-sanction',
  planned: 'bg-primary/10 text-primary',
  done: 'bg-positive/10 text-positive',
}

const contentKindLabel: Record<string, string> = {
  fill_product: 'Наполнить товар',
  missing_product: 'Нет товара',
  missing_section: 'Нет раздела',
}

function formatDateTime(iso: string): string {
  return new Date(iso).toLocaleDateString('ru-RU', {
    day: '2-digit',
    month: '2-digit',
    year: '2-digit',
  })
}

export function BAdminPage() {
  const subs = useSubscriptionRequests()
  const content = useContentRequests()

  const subRows = subs.data ?? []
  const contentRows = content.data ?? []
  const newSubs = subRows.filter((r) => r.status === 'new').length

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <div className="flex items-center gap-3">
        <span className="grid size-10 place-items-center rounded-xl bg-accent text-accent-foreground">
          <Inbox className="size-5" />
        </span>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Админка · входящие</h1>
          <p className="text-sm text-muted-foreground">Заявки на доступ и на наполнение контента.</p>
        </div>
      </div>

      <div className="mt-6 grid gap-3 sm:grid-cols-3">
        <StatTile label="Заявок на доступ" value={subRows.length} tone="primary" />
        <StatTile label="Из них новых" value={newSubs} tone={newSubs > 0 ? 'sanction' : 'default'} />
        <StatTile label="Заявок на наполнение" value={contentRows.length} />
      </div>

      <section className="mt-8">
        <h2 className="text-sm font-semibold tracking-wide text-muted-foreground uppercase">
          Заявки на доступ
        </h2>
        <BCard className="mt-3 overflow-hidden">
          {subs.isLoading ? (
            <TablePlaceholder />
          ) : subRows.length === 0 ? (
            <EmptyRow text="Нет заявок или нет прав на просмотр (нужна роль администратора в RLS)." />
          ) : (
            <SubsTable rows={subRows} />
          )}
        </BCard>
      </section>

      <section className="mt-8">
        <h2 className="text-sm font-semibold tracking-wide text-muted-foreground uppercase">
          Заявки на наполнение
        </h2>
        <BCard className="mt-3 overflow-hidden">
          {content.isLoading ? (
            <TablePlaceholder />
          ) : contentRows.length === 0 ? (
            <EmptyRow text="Нет заявок или нет прав на просмотр." />
          ) : (
            <ContentTable rows={contentRows} />
          )}
        </BCard>
      </section>
    </div>
  )
}

function StatusChip({ status }: { status: string }) {
  return (
    <span
      className={cn(
        'inline-block rounded-full px-2 py-0.5 text-[11px] font-medium',
        statusTone[status] ?? 'bg-secondary text-muted-foreground',
      )}
    >
      {status}
    </span>
  )
}

function SubsTable({ rows }: { rows: SubscriptionRequestRow[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] text-sm">
        <thead>
          <tr className="border-b bg-secondary/40 text-left text-xs text-muted-foreground">
            <Th>Дата</Th>
            <Th>Имя</Th>
            <Th>Контакт</Th>
            <Th>Компания</Th>
            <Th>Статус</Th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {rows.map((r) => (
            <tr key={r.id} className="hover:bg-secondary/30">
              <Td className="font-mono text-xs text-muted-foreground">{formatDateTime(r.createdAt)}</Td>
              <Td className="font-medium">{r.fullName}</Td>
              <Td>{r.contact}</Td>
              <Td className="text-muted-foreground">{r.company ?? '—'}</Td>
              <Td><StatusChip status={r.status} /></Td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ContentTable({ rows }: { rows: ContentRequestRow[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[520px] text-sm">
        <thead>
          <tr className="border-b bg-secondary/40 text-left text-xs text-muted-foreground">
            <Th>Дата</Th>
            <Th>Тип</Th>
            <Th>Запрос</Th>
            <Th>Статус</Th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {rows.map((r) => (
            <tr key={r.id} className="hover:bg-secondary/30">
              <Td className="font-mono text-xs text-muted-foreground">{formatDateTime(r.createdAt)}</Td>
              <Td>{contentKindLabel[r.kind] ?? r.kind}</Td>
              <Td className="text-muted-foreground">{r.queryText ?? r.comment ?? '—'}</Td>
              <Td><StatusChip status={r.status} /></Td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function Th({ children }: { children: React.ReactNode }) {
  return <th className="px-4 py-2.5 font-medium">{children}</th>
}
function Td({ children, className }: { children: React.ReactNode; className?: string }) {
  return <td className={cn('px-4 py-3 align-middle', className)}>{children}</td>
}
function EmptyRow({ text }: { text: string }) {
  return <p className="px-4 py-8 text-center text-sm text-muted-foreground">{text}</p>
}
function TablePlaceholder() {
  return (
    <div className="space-y-2 p-4">
      {Array.from({ length: 3 }, (_, i) => (
        <div key={i} className="h-9 animate-pulse rounded-lg bg-secondary" />
      ))}
    </div>
  )
}
