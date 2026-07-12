import type { Operation, TransportType } from '@/data/types'
import type { OperationNode } from '@/data/taxonomy'
import { OPERATION_GROUPS, TRANSPORTS, transportLabel } from '@/data/taxonomy'
import { cn } from '@/lib/utils'
import { OPERATION_ICON } from './ui'

/**
 * Подпись дизайна C: операции как станции на вертикальном маршруте товара.
 * Нить прорисовывается при входе, у активной трансграничной станции
 * появляется ветка выбора транспорта.
 */
export function CRouteNav({
  nodes,
  activeOp,
  transport,
  onSelectOp,
  onSelectTransport,
}: {
  nodes: OperationNode[]
  activeOp: Operation
  transport: TransportType | null
  onSelectOp: (op: Operation) => void
  onSelectTransport: (t: TransportType | null) => void
}) {
  let stationIndex = -1
  return (
    <nav aria-label="Операции" className="relative">
      {/* Нить маршрута */}
      <span
        aria-hidden
        className="c-thread absolute top-3 bottom-3 left-[13px] w-px bg-gradient-to-b from-primary/60 via-primary/35 to-primary/60"
      />
      <div className="space-y-6">
        {OPERATION_GROUPS.map((group) => {
          const groupNodes = nodes.filter((n) => n.meta.group === group.key)
          if (groupNodes.length === 0) return null
          return (
            <div key={group.key}>
              <p className="pl-9 font-mono text-[10px] font-medium tracking-[0.12em] text-muted-foreground uppercase">
                {group.title}
              </p>
              <ul className="mt-1.5 space-y-0.5">
                {groupNodes.map((node) => {
                  stationIndex += 1
                  const active = node.meta.key === activeOp
                  const Icon = OPERATION_ICON[node.meta.key]
                  const showBranch = active && node.transports.length > 0
                  return (
                    <li
                      key={node.meta.key}
                      className="c-station"
                      style={{ '--i': stationIndex } as React.CSSProperties}
                    >
                      <button
                        type="button"
                        aria-current={active ? 'true' : undefined}
                        title={node.meta.full}
                        onClick={() => onSelectOp(node.meta.key)}
                        className={cn(
                          'group relative flex w-full items-center gap-2.5 rounded-lg py-2 pr-2.5 pl-9 text-left text-sm transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
                          active
                            ? 'bg-accent font-semibold text-accent-foreground'
                            : 'text-foreground/80 hover:bg-secondary/60 hover:text-foreground',
                        )}
                      >
                        {/* Станция на нити */}
                        <span
                          aria-hidden
                          className={cn(
                            'absolute top-1/2 left-[8.5px] size-[10px] -translate-y-1/2 rounded-full border-2 bg-card transition-all',
                            active
                              ? 'scale-110 border-primary bg-primary ring-4 ring-primary/15'
                              : 'border-primary/50 group-hover:border-primary',
                          )}
                        />
                        <Icon className={cn('size-4 shrink-0', active ? 'text-primary' : 'opacity-70')} />
                        <span className="min-w-0 flex-1 truncate">{node.meta.label}</span>
                        <span
                          className={cn(
                            'font-mono text-[11px] tabular-nums',
                            active ? 'font-medium text-primary' : 'text-muted-foreground',
                          )}
                        >
                          {node.count}
                        </span>
                      </button>

                      {/* Ветка транспорта у активной процедуры */}
                      {showBranch && (
                        <div className="relative mt-1 mb-1.5 ml-[13px] border-l border-dashed border-primary/40 pt-0.5 pb-0.5 pl-4">
                          <div className="flex flex-wrap gap-1">
                            <TransportChip
                              label="Все"
                              active={transport === null}
                              onClick={() => onSelectTransport(null)}
                            />
                            {TRANSPORTS.filter((t) => node.transports.includes(t.key)).map((t) => (
                              <TransportChip
                                key={t.key}
                                label={transportLabel(t.key)}
                                active={transport === t.key}
                                onClick={() => onSelectTransport(t.key)}
                              />
                            ))}
                          </div>
                        </div>
                      )}
                    </li>
                  )
                })}
              </ul>
            </div>
          )
        })}
      </div>
    </nav>
  )
}

function TransportChip({
  label,
  active,
  onClick,
}: {
  label: string
  active: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cn(
        'rounded-md px-2 py-1 text-[12px] font-medium transition-colors focus-visible:ring-2 focus-visible:ring-ring focus-visible:outline-none',
        active
          ? 'bg-primary text-primary-foreground'
          : 'bg-secondary text-muted-foreground hover:text-foreground',
      )}
    >
      {label}
    </button>
  )
}

/** Мобильная версия маршрута: горизонтальные станции + ветка транспорта */
export function CRouteNavMobile({
  nodes,
  activeOp,
  transport,
  onSelectOp,
  onSelectTransport,
}: {
  nodes: OperationNode[]
  activeOp: Operation
  transport: TransportType | null
  onSelectOp: (op: Operation) => void
  onSelectTransport: (t: TransportType | null) => void
}) {
  const activeNode = nodes.find((n) => n.meta.key === activeOp)
  return (
    <div className="space-y-2.5">
      <div className="-mx-4 overflow-x-auto px-4">
        <div className="flex w-max gap-1.5">
          {nodes.map((node) => {
            const active = node.meta.key === activeOp
            const Icon = OPERATION_ICON[node.meta.key]
            return (
              <button
                key={node.meta.key}
                type="button"
                aria-pressed={active}
                onClick={() => onSelectOp(node.meta.key)}
                className={cn(
                  'flex shrink-0 items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[13px] font-medium transition-colors',
                  active
                    ? 'border-primary bg-primary text-primary-foreground'
                    : 'border-border bg-card text-muted-foreground',
                )}
              >
                <Icon className="size-3.5" />
                {node.meta.label}
                <span className="font-mono text-[11px] tabular-nums opacity-75">{node.count}</span>
              </button>
            )
          })}
        </div>
      </div>
      {activeNode && activeNode.transports.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          <TransportChip label="Все" active={transport === null} onClick={() => onSelectTransport(null)} />
          {TRANSPORTS.filter((t) => activeNode.transports.includes(t.key)).map((t) => (
            <TransportChip
              key={t.key}
              label={transportLabel(t.key)}
              active={transport === t.key}
              onClick={() => onSelectTransport(t.key)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
