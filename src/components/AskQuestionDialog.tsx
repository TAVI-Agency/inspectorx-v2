import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { useAuth } from '@/app/auth'
import { useAskQuestion } from '@/data/hooks'
import { ru } from '@/i18n/ru'

/**
 * «Задать вопрос» / «Официальный запрос (GR)» — воронка §5a.
 * Пишет в user_questions (нужен вход).
 */
export function AskQuestionDialog({
  open,
  onOpenChange,
  requirementId,
  productId,
  requirementTitle,
  grByDefault,
}: {
  open: boolean
  onOpenChange: (v: boolean) => void
  requirementId: string
  productId?: string
  requirementTitle: string
  grByDefault?: boolean
}) {
  const { session } = useAuth()
  const ask = useAskQuestion()
  const [text, setText] = useState('')
  const [legalReview, setLegalReview] = useState(true)
  const [official, setOfficial] = useState(Boolean(grByDefault))
  const [urgent, setUrgent] = useState(false)

  function submit() {
    ask.mutate({
      questionText: text.trim(),
      requirementId,
      productId,
      legalReviewOnly: legalReview,
      allowOfficialRequest: official,
      isUrgent: urgent,
    })
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{ru.requirement.card.askQuestion}</DialogTitle>
          <DialogDescription className="line-clamp-2">
            {requirementTitle}
          </DialogDescription>
        </DialogHeader>

        {!session ? (
          <div className="space-y-3">
            <p className="text-sm text-muted-foreground">{ru.auth.loginRequired}</p>
            <Button nativeButton={false} render={<Link to="/login" />} size="sm">
              {ru.common.signIn}
            </Button>
          </div>
        ) : ask.isSuccess ? (
          <p className="text-sm text-positive">
            Вопрос отправлен. Ответим на email в течение 1–2 рабочих дней.
          </p>
        ) : (
          <div className="space-y-4">
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              rows={4}
              placeholder="Опишите ситуацию: что ввозите/производите и что непонятно в требовании"
              className="w-full rounded-lg border border-input bg-transparent px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
            />
            <div className="space-y-2.5">
              <label className="flex items-center gap-2.5 text-sm">
                <Switch size="sm" checked={legalReview} onCheckedChange={setLegalReview} />
                Нужна юридическая экспертиза
              </label>
              <label className="flex items-center gap-2.5 text-sm">
                <Switch size="sm" checked={official} onCheckedChange={setOfficial} />
                {ru.requirement.card.grRequest}
              </label>
              <label className="flex items-center gap-2.5 text-sm">
                <Switch size="sm" checked={urgent} onCheckedChange={setUrgent} />
                Срочно
              </label>
            </div>
            {ask.isError && (
              <p className="text-sm text-destructive">{ru.auth.errors.generic}</p>
            )}
            <div className="flex justify-end gap-2">
              <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
                {ru.common.cancel}
              </Button>
              <Button
                size="sm"
                disabled={text.trim().length < 10 || ask.isPending}
                onClick={submit}
              >
                {ask.isPending ? ru.common.sending : ru.common.send}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

export function useAskDialogState() {
  const [state, setState] = useState<{ open: boolean; gr: boolean }>({
    open: false,
    gr: false,
  })
  return {
    open: state.open,
    gr: state.gr,
    openAsk: () => setState({ open: true, gr: false }),
    openGr: () => setState({ open: true, gr: true }),
    onOpenChange: (v: boolean) => setState((s) => ({ ...s, open: v })),
  }
}
