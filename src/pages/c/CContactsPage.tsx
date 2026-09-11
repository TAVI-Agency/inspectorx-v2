import { COMPANY, companyRequisitesFilled } from '@/config'
import { ru } from '@/i18n/ru'
import { CCard, CEyebrow } from './ui'

/** Контакты: email + Telegram всегда, реквизиты — только когда заполнены */
export function CContactsPage() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-7 sm:px-8">
      <CEyebrow>Документы</CEyebrow>
      <h1 className="font-display mt-2 text-[22px] leading-tight font-medium tracking-tight sm:text-[30px]">
        {ru.legal.contactsTitle}
      </h1>

      <div className="mt-8 space-y-8">
        <CCard className="p-4">
          <div className="flex flex-col gap-2 text-sm">
            <a href={`mailto:${COMPANY.email}`} className="font-medium text-primary hover:underline">
              {COMPANY.email}
            </a>
            <a
              href={`https://t.me/${COMPANY.telegram.replace('@', '')}`}
              target="_blank"
              rel="noreferrer"
              className="font-medium text-primary hover:underline"
            >
              {COMPANY.telegram}
            </a>
          </div>
        </CCard>

        {companyRequisitesFilled() ? (
          <section>
            <CEyebrow>{ru.legal.requisites}</CEyebrow>
            <CCard className="mt-3 p-4">
              <div className="space-y-1 text-sm text-muted-foreground">
                <p>{COMPANY.legalName}</p>
                <p>{COMPANY.inn}</p>
                <p>{COMPANY.address}</p>
              </div>
            </CCard>
          </section>
        ) : null}
      </div>
    </div>
  )
}
