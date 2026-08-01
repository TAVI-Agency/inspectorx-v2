import { useState } from 'react'
import { Send } from 'lucide-react'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { useContentRequest } from '@/data/hooks'
import { ru } from '@/i18n/ru'

/** Фидбэк уходит существующим механизмом заявок (content_requests) */
export function FeedbackForm({ onDone }: { onDone?: () => void }) {
  const request = useContentRequest()
  const [text, setText] = useState('')
  const [done, setDone] = useState(false)

  function submit() {
    const comment = text.trim()
    if (!comment) return
    request.mutate(
      { kind: 'missing_section', queryText: 'Фидбэк из приложения', comment },
      {
        onSuccess: () => {
          setDone(true)
          setText('')
          onDone?.()
        },
      },
    )
  }

  if (done) return <p className="text-sm font-medium text-positive">{ru.help.feedbackDone}</p>

  return (
    <div>
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={3}
        placeholder={ru.help.feedbackPlaceholder}
        className="w-full resize-none rounded-lg border border-input bg-transparent px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
      />
      <div className="mt-2.5 flex items-center gap-3">
        <Button size="sm" disabled={request.isPending || !text.trim()} onClick={submit}>
          <Send />
          {request.isPending ? ru.common.sending : ru.help.feedbackSend}
        </Button>
        {request.isError && <p className="text-xs text-destructive">{ru.help.feedbackError}</p>}
      </div>
    </div>
  )
}

export function FeedbackDialog({
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
          <DialogTitle>{ru.help.feedbackTitle}</DialogTitle>
          <DialogDescription>{ru.help.feedbackText}</DialogDescription>
        </DialogHeader>
        <FeedbackForm />
      </DialogContent>
    </Dialog>
  )
}
