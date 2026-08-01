import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { ru } from '@/i18n/ru'

/** «Что нового»: честный changelog выехавших фич */
export function WhatsNewDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{ru.whatsNew.title}</DialogTitle>
        </DialogHeader>
        <ul className="space-y-4">
          {ru.whatsNew.entries.map((e) => (
            <li key={e.date + e.title}>
              <p className="font-mono text-[10px] tracking-[0.1em] text-muted-foreground uppercase">
                {e.date}
              </p>
              <p className="mt-0.5 text-sm font-semibold tracking-tight">{e.title}</p>
              <p className="mt-0.5 text-[13px] leading-relaxed text-muted-foreground">{e.text}</p>
            </li>
          ))}
        </ul>
      </DialogContent>
    </Dialog>
  )
}
