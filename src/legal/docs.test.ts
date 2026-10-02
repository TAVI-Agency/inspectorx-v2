import { describe, expect, it } from 'vitest'

import { LEGAL_DOCS, publishedLegalDocs } from './docs'

describe('LEGAL_DOCS', () => {
  it('оба документа есть и до вычитки юристом не опубликованы', () => {
    expect(Object.keys(LEGAL_DOCS).sort()).toEqual(['offer', 'privacy'])
    expect(publishedLegalDocs()).toEqual([])
  })
})
