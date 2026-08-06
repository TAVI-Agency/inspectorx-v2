import { describe, expect, it } from 'vitest'

import { ru } from './ru'

describe('ru.packagingCheck', () => {
  it('обязательные ключи раздела на месте', () => {
    const required = [
      'title', 'pickProduct', 'pickLevel', 'levelConsumer', 'levelTransport',
      'whatWeCheck', 'counterCheckable', 'counterPartial', 'counterNotCheckable',
      'counterNoGold', 'noChecklistTitle', 'noChecklistText', 'notifyCta',
      'uploadPdfTitle', 'uploadPdfHint', 'uploadPhotoTitle', 'needFourFrames',
      'startCheck', 'uploading',
    ] as const
    for (const key of required) expect(ru.packagingCheck).toHaveProperty(key)
  })
})
