import { FeedbackForm } from '@/components/FeedbackDialog'
import { ru } from '@/i18n/ru'
import { CCard, CEyebrow } from './ui'

/** Помощь: FAQ, контакты и форма фидбэка на одной странице */
export function CHelpPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-7 sm:px-8">
      <CEyebrow>Поддержка</CEyebrow>
      <h1 className="font-display mt-2 text-[22px] leading-tight font-medium tracking-tight sm:text-[30px]">
        {ru.help.title}
      </h1>

      <div className="mt-8 space-y-8">
        <section>
          <CEyebrow>{ru.help.faqTitle}</CEyebrow>
          <div className="mt-3 space-y-3">
            {ru.help.faq.map((item, i) => (
              <CCard key={i} className="p-4">
                <p className="text-sm font-semibold">{item.q}</p>
                <p className="mt-1.5 text-sm leading-relaxed text-muted-foreground">{item.a}</p>
              </CCard>
            ))}
          </div>
        </section>

        <section>
          <CEyebrow>{ru.help.contactsTitle}</CEyebrow>
          <CCard className="mt-3 p-4">
            <p className="text-sm text-muted-foreground">{ru.help.contactsText}</p>
            <div className="mt-3 flex flex-col gap-2 text-sm">
              <a href="mailto:hello@inspectorx.uz" className="font-medium text-primary hover:underline">
                {ru.footer.email}
              </a>
              <a
                href="https://t.me/inspectorx_uz"
                target="_blank"
                rel="noreferrer"
                className="font-medium text-primary hover:underline"
              >
                {ru.footer.telegram}
              </a>
            </div>
          </CCard>
        </section>

        <section>
          <CEyebrow>{ru.help.feedbackTitle}</CEyebrow>
          <CCard className="mt-3 p-4">
            <p className="text-sm text-muted-foreground">{ru.help.feedbackText}</p>
            <div className="mt-3">
              <FeedbackForm />
            </div>
          </CCard>
        </section>
      </div>
    </div>
  )
}
