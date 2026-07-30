import { useState } from 'react'
import { Link } from 'react-router-dom'
import { MessageCircle, Send } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useAuth } from '@/app/auth'
import { useAppMode } from '@/app/app-mode'
import { useAskQuestion, useMyQuestions } from '@/data/hooks'
import type { QuestionStatus, UserQuestion } from '@/data/types'
import { formatDate } from '@/lib/format'
import { ru } from '@/i18n/ru'
import { cn } from '@/lib/utils'
import { CCard, CEyebrow, CTrustStamp } from './ui'

const STATUS_TONE: Record<QuestionStatus, string> = {
  new: 'bg-secondary text-muted-foreground',
  ai_answered: 'bg-positive/10 text-positive',
  expert_answered: 'bg-positive/10 text-positive',
  gr_sent: 'bg-primary/10 text-primary',
  gr_answered: 'bg-positive/10 text-positive',
  closed: 'bg-secondary text-muted-foreground',
}

const TRUST_FOR: Partial<Record<QuestionStatus, 'ai_draft' | 'lawyer_verified' | 'official_answer'>> = {
  ai_answered: 'ai_draft',
  expert_answered: 'lawyer_verified',
  gr_answered: 'official_answer',
}

export function CQuestionsPage() {
  const { session } = useAuth()
  const { mockSubscriber } = useAppMode()
  const { data: questions } = useMyQuestions()

  if (!session && !mockSubscriber) return <CLoginCard />

  return (
    <div className="mx-auto max-w-3xl px-4 py-7 sm:px-8">
      <CEyebrow>Вопрос — ответ</CEyebrow>
      <h1 className="font-display mt-2 text-[22px] leading-tight font-medium tracking-tight sm:text-[30px]">
        {ru.questions.title}
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">{ru.questions.subtitle}</p>

      {session && <CAskForm />}

      <div className="mt-6 space-y-3">
        {(questions ?? []).length === 0 ? (
          <CCard className="p-6 text-sm text-muted-foreground">{ru.questions.empty}</CCard>
        ) : (
          (questions ?? []).map((q, i) => <CQuestionCard key={q.id} q={q} index={i} />)
        )}
      </div>
    </div>
  )
}

function CAskForm() {
  const ask = useAskQuestion()
  const [text, setText] = useState('')
  const [flash, setFlash] = useState(false)

  function submit() {
    const questionText = text.trim()
    if (!questionText) return
    ask.mutate(
      { questionText, legalReviewOnly: false, allowOfficialRequest: true, isUrgent: false },
      {
        onSuccess: () => {
          setText('')
          setFlash(true)
          setTimeout(() => setFlash(false), 4000)
        },
      },
    )
  }

  return (
    <CCard className="mt-6 p-4">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={2}
        placeholder={ru.questions.placeholder}
        className="w-full resize-none rounded-lg border border-input bg-transparent px-3 py-2 text-sm outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
      />
      <div className="mt-2.5 flex items-center gap-3">
        <Button size="sm" disabled={ask.isPending || !text.trim()} onClick={submit}>
          <Send />
          {ask.isPending ? ru.common.sending : ru.questions.ask}
        </Button>
        {flash && <p className="text-xs text-positive">{ru.questions.asked}</p>}
        {ask.isError && <p className="text-xs text-destructive">{ru.questions.askError}</p>}
      </div>
    </CCard>
  )
}

function CQuestionCard({ q, index }: { q: UserQuestion; index: number }) {
  const trust = TRUST_FOR[q.status]
  return (
    <CCard className="c-rise p-4 sm:p-5" style={{ '--i': index } as React.CSSProperties}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
        <span className={cn('rounded-[6px] px-2 py-0.5 text-[11px] font-medium', STATUS_TONE[q.status])}>
          {ru.questions.status[q.status]}
        </span>
        {q.isUrgent && (
          <span className="rounded-[6px] bg-sanction/10 px-2 py-0.5 text-[11px] font-medium text-sanction">
            {ru.questions.urgent}
          </span>
        )}
        <span className="ml-auto font-mono text-[11px] text-muted-foreground">
          {formatDate(q.createdAt)}
        </span>
      </div>
      <p className="mt-2 text-[15px] font-semibold tracking-tight">{q.questionText}</p>
      {q.answerText && (
        <div className="mt-3 rounded-lg bg-secondary/50 p-3.5">
          {trust && <CTrustStamp trust={trust} date={q.answeredAt ? formatDate(q.answeredAt) : undefined} />}
          <p className="mt-2 text-sm leading-relaxed">{q.answerText}</p>
        </div>
      )}
    </CCard>
  )
}

function CLoginCard() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-24 sm:px-8">
      <CCard className="mx-auto max-w-md p-8 text-center">
        <span className="mx-auto grid size-12 place-items-center rounded-full border border-primary/40 bg-accent text-accent-foreground">
          <MessageCircle className="size-5" />
        </span>
        <h1 className="mt-4 text-xl font-semibold tracking-tight">{ru.questions.loginTitle}</h1>
        <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{ru.questions.loginText}</p>
        <Button className="mt-5" nativeButton={false} render={<Link to="/login" />}>
          {ru.common.signIn}
        </Button>
      </CCard>
    </div>
  )
}
