import { useState } from 'react'
import { Camera, Check, FileCheck } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useContentRequest } from '@/data/hooks'
import { ru } from '@/i18n/ru'
import { CEyebrow } from './ui'

const CHECK_META = {
  packaging: { icon: Camera, storageKey: 'ix-notify-packaging', query: 'Анонс: проверка упаковки' },
  documents: { icon: FileCheck, storageKey: 'ix-notify-documents', query: 'Анонс: проверка документов' },
} as const

/** Пустая страница-анонс будущей проверки: ценность + заявка на уведомление */
export function CCheckAnnouncePage({ check }: { check: 'packaging' | 'documents' }) {
  const meta = CHECK_META[check]
  const t = ru.checks[check]
  const Icon = meta.icon
  const request = useContentRequest()
  const [done, setDone] = useState(() => localStorage.getItem(meta.storageKey) === '1')

  function notify() {
    request.mutate(
      { kind: 'missing_section', queryText: meta.query },
      {
        onSuccess: () => {
          localStorage.setItem(meta.storageKey, '1')
          setDone(true)
        },
      },
    )
  }

  return (
    <div className="mx-auto flex max-w-6xl flex-col items-center px-4 py-24 text-center sm:px-8">
      <span className="grid size-16 place-items-center rounded-2xl border border-primary/30 bg-accent text-primary">
        <Icon className="size-7" />
      </span>
      <CEyebrow className="mt-5">{ru.nav.checksSection} · {ru.nav.soon}</CEyebrow>
      <h1 className="font-display mt-2 text-[22px] leading-tight font-medium tracking-tight sm:text-[28px]">
        {t.title}
      </h1>
      <p className="mt-3 max-w-md text-sm leading-relaxed text-muted-foreground sm:text-[15px]">
        {t.text}
      </p>
      {done ? (
        <p className="mt-6 inline-flex items-center gap-2 text-sm font-medium text-positive">
          <Check className="size-4" />
          {ru.checks.notifyDone}
        </p>
      ) : (
        <Button variant="outline" className="mt-6" disabled={request.isPending} onClick={notify}>
          {request.isPending ? ru.common.sending : ru.checks.notifyCta}
        </Button>
      )}
      {request.isError && <p className="mt-2 text-xs text-destructive">{ru.checks.notifyError}</p>}
    </div>
  )
}
