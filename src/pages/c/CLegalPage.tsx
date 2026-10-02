import { Link } from 'react-router-dom'
import { LEGAL_DOCS } from '@/legal/docs'
import { ru } from '@/i18n/ru'
import { formatDate } from '@/lib/format'
import { CCard, CEyebrow } from './ui'

/** Оферта / политика конфиденциальности — одна страница на оба документа */
export function CLegalPage({ kind }: { kind: 'offer' | 'privacy' }) {
  const doc = LEGAL_DOCS[kind]
  const title = kind === 'offer' ? ru.legal.offerTitle : ru.legal.privacyTitle

  return (
    <div className="mx-auto max-w-3xl px-4 py-7 sm:px-8">
      <CEyebrow>{ru.legal.docsEyebrow}</CEyebrow>
      <h1 className="font-display mt-2 text-[22px] leading-tight font-medium tracking-tight sm:text-[30px]">
        {title}
      </h1>

      {!doc.published ? (
        <CCard className="mt-8 p-4">
          <p className="text-sm text-muted-foreground">{ru.legal.notPublished}</p>
          <Link to="/contacts" className="mt-3 inline-block text-sm font-medium text-primary hover:underline">
            {ru.legal.writeUs}
          </Link>
        </CCard>
      ) : (
        <div className="mt-8 space-y-8">
          <p className="text-xs text-muted-foreground">{formatDate(doc.updatedAt)}</p>
          {doc.sections.map((section, i) => (
            <section key={i}>
              <CEyebrow>{section.heading}</CEyebrow>
              <div className="mt-3 space-y-3 text-sm leading-relaxed text-muted-foreground">
                {section.paragraphs.map((p, j) => (
                  <p key={j}>{p}</p>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}

      <Link to="/" className="mt-8 inline-block text-sm font-medium text-primary hover:underline">
        {ru.legal.backHome}
      </Link>
    </div>
  )
}
