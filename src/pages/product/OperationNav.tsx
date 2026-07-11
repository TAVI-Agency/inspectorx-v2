import type { Operation, TransportType } from '@/data/types'
import { OPERATION_GROUPS, TRANSPORTS, type OperationNode } from '@/data/taxonomy'
import { cn } from '@/lib/utils'

/**
 * Верхний уровень навигации по требованиям (§ таксономия): операции, сгруппированные
 * в «Требования к товару» и «Внешнеэкономические процедуры». Показываются только
 * операции, у которых есть требования. Вид вкладок — подчёркивание (отличает от
 * чипов-этапов ниже).
 */
export function OperationNav({
  nodes,
  active,
  onChange,
}: {
  nodes: OperationNode[]
  active: Operation
  onChange: (op: Operation) => void
}) {
  return (
    <div className="flex flex-col gap-x-10 gap-y-4 border-b sm:flex-row sm:flex-wrap">
      {OPERATION_GROUPS.map((group) => {
        const groupNodes = nodes.filter((n) => n.meta.group === group.key)
        if (groupNodes.length === 0) return null
        return (
          <div key={group.key} className="min-w-0">
            <p className="font-mono text-[10px] tracking-[0.1em] text-muted-foreground uppercase">
              {group.title}
            </p>
            <div
              className="scrollbar-none -mx-4 mt-1 flex gap-1 overflow-x-auto px-4 sm:mx-0 sm:px-0"
              role="tablist"
              aria-label={group.title}
            >
              {groupNodes.map((node) => (
                <button
                  key={node.meta.key}
                  type="button"
                  role="tab"
                  aria-selected={active === node.meta.key}
                  title={node.meta.full}
                  onClick={() => onChange(node.meta.key)}
                  className={cn(
                    'relative inline-flex shrink-0 items-baseline gap-1.5 border-b-2 px-1 pt-1 pb-2 text-sm whitespace-nowrap transition-colors focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none',
                    active === node.meta.key
                      ? 'border-primary font-medium text-foreground'
                      : 'border-transparent text-muted-foreground hover:text-foreground',
                  )}
                >
                  {node.meta.label}
                  <span className="font-mono text-[11px] text-muted-foreground tabular-nums">
                    {node.count}
                  </span>
                </button>
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

/** Переключатель транспорта внутри процедуры (Авто · Поезд · Самолёт). */
export function TransportSwitcher({
  available,
  active,
  onChange,
}: {
  available: TransportType[]
  active: TransportType | null
  onChange: (t: TransportType | null) => void
}) {
  if (available.length === 0) return null
  const options = TRANSPORTS.filter((t) => available.includes(t.key))
  return (
    <div className="flex items-center gap-2">
      <span className="font-mono text-[10px] tracking-[0.1em] text-muted-foreground uppercase">
        Транспорт
      </span>
      <div className="flex rounded-lg bg-muted p-0.5" role="radiogroup" aria-label="Вид транспорта">
        <SegBtn label="Все" selected={active === null} onClick={() => onChange(null)} />
        {options.map((t) => (
          <SegBtn
            key={t.key}
            label={t.label}
            selected={active === t.key}
            onClick={() => onChange(t.key)}
          />
        ))}
      </div>
    </div>
  )
}

function SegBtn({
  label,
  selected,
  onClick,
}: {
  label: string
  selected: boolean
  onClick: () => void
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      onClick={onClick}
      className={cn(
        'rounded-[7px] px-3 py-1 text-[13px] font-medium transition-colors',
        selected ? 'bg-paper text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground',
      )}
    >
      {label}
    </button>
  )
}
