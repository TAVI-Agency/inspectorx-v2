/**
 * Юридические документы витрины (оферта, политика конфиденциальности).
 * Тексты пишет параллельная задача (docs/legal/), юрист вычитывает позже —
 * до апрува документы остаются `published: false` и на витрине не видны.
 */
export type LegalDoc = {
  slug: 'offer' | 'privacy'
  published: boolean
  updatedAt: string
  sections: Array<{ heading: string; paragraphs: string[] }>
}

export const LEGAL_DOCS: Record<'offer' | 'privacy', LegalDoc> = {
  offer: {
    slug: 'offer',
    published: false,
    updatedAt: '2026-09-11',
    sections: [],
  },
  privacy: {
    slug: 'privacy',
    published: false,
    updatedAt: '2026-09-11',
    sections: [],
  },
}

export const publishedLegalDocs = () => Object.values(LEGAL_DOCS).filter((d) => d.published)
