import { afterEach, describe, expect, it, vi } from 'vitest'

import { prepareImageForUpload, preparePhotoForUpload, targetSize } from './image'

describe('targetSize', () => {
  it('длинная сторона ужимается до 2048, пропорции сохраняются', () => {
    expect(targetSize(4096, 2048)).toEqual({ w: 2048, h: 1024 })
    expect(targetSize(1000, 3000)).toEqual({ w: 682, h: 2048 })
  })
  it('маленький кадр не растягивается', () => {
    expect(targetSize(800, 600)).toEqual({ w: 800, h: 600 })
  })
})

describe('prepareImageForUpload', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('декодирует по EXIF-ориентации, ужимает через canvas и отдаёт JPEG 0.85', async () => {
    const close = vi.fn()
    const fakeBitmap = { width: 4096, height: 2048, close }
    const createImageBitmapMock = vi.fn().mockResolvedValue(fakeBitmap)
    vi.stubGlobal('createImageBitmap', createImageBitmapMock)

    const drawImage = vi.fn()
    let toBlobArgs: [string | undefined, number | undefined] | null = null
    const fakeCanvas = {
      width: 0,
      height: 0,
      getContext: vi.fn(() => ({ drawImage })),
      toBlob: vi.fn(
        (cb: (b: Blob | null) => void, type?: string, quality?: number) => {
          toBlobArgs = [type, quality]
          cb(new Blob(['jpeg-bytes'], { type }))
        },
      ),
    }
    vi.stubGlobal('document', { createElement: vi.fn(() => fakeCanvas) })

    const file = new File([new Uint8Array([1, 2, 3])], 'pack.heic', { type: 'image/heic' })
    const blob = await prepareImageForUpload(file)

    expect(createImageBitmapMock).toHaveBeenCalledWith(file, { imageOrientation: 'from-image' })
    // 4096x2048 сжимается до 2048x1024 — та же логика, что и в targetSize
    expect(fakeCanvas.width).toBe(2048)
    expect(fakeCanvas.height).toBe(1024)
    expect(drawImage).toHaveBeenCalledWith(fakeBitmap, 0, 0, 2048, 1024)
    expect(toBlobArgs).toEqual(['image/jpeg', 0.85])
    expect(blob.type).toBe('image/jpeg')
    expect(close).toHaveBeenCalled()
  })

  it('bitmap закрывается даже если canvas.toBlob не вернул кадр', async () => {
    const close = vi.fn()
    vi.stubGlobal(
      'createImageBitmap',
      vi.fn().mockResolvedValue({ width: 100, height: 100, close }),
    )
    const fakeCanvas = {
      width: 0,
      height: 0,
      getContext: vi.fn(() => ({ drawImage: vi.fn() })),
      toBlob: vi.fn((cb: (b: Blob | null) => void) => cb(null)),
    }
    vi.stubGlobal('document', { createElement: vi.fn(() => fakeCanvas) })

    const file = new File([new Uint8Array([1])], 'pack.jpg', { type: 'image/jpeg' })
    await expect(prepareImageForUpload(file)).rejects.toThrow('canvas_to_blob_failed')
    expect(close).toHaveBeenCalled()
  })
})

describe('preparePhotoForUpload', () => {
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('HEIC, который браузер не декодирует, уходит оригиналом — воркер развернёт сам', async () => {
    // Chrome/Firefox не умеют HEIC: createImageBitmap кидает — деградируем к оригиналу
    vi.stubGlobal('createImageBitmap', vi.fn().mockRejectedValue(new Error('decode failed')))
    const file = new File([new Uint8Array([1, 2, 3])], 'IMG_0001.HEIC', { type: 'image/heic' })
    const out = await preparePhotoForUpload(file)
    expect(out.blob).toBe(file)
    expect(out.ext).toBe('heic')
    expect(out.contentType).toBe('image/heic')
  })

  it('расширение берётся из MIME, если имя файла без расширения', async () => {
    vi.stubGlobal('createImageBitmap', vi.fn().mockRejectedValue(new Error('decode failed')))
    const file = new File([new Uint8Array([1])], 'photo', { type: 'image/png' })
    const out = await preparePhotoForUpload(file)
    expect(out.ext).toBe('png')
    expect(out.contentType).toBe('image/png')
  })

  it('неизвестный формат при провале конвертации — именованная ошибка, не нативная', async () => {
    vi.stubGlobal('createImageBitmap', vi.fn().mockRejectedValue(new Error('decode failed')))
    const file = new File([new Uint8Array([1])], 'scan.tiff', { type: 'image/tiff' })
    await expect(preparePhotoForUpload(file)).rejects.toThrow('unsupported_image')
  })

  it('среда без createImageBitmap тоже деградирует к оригиналу, а не падает нативно', async () => {
    vi.stubGlobal('createImageBitmap', undefined)
    const file = new File([new Uint8Array([1])], 'pack.jpg', { type: 'image/jpeg' })
    const out = await preparePhotoForUpload(file)
    expect(out.blob).toBe(file)
    expect(out.ext).toBe('jpg')
    expect(out.contentType).toBe('image/jpeg')
  })

  it('успешная конвертация по-прежнему отдаёт JPEG', async () => {
    vi.stubGlobal(
      'createImageBitmap',
      vi.fn().mockResolvedValue({ width: 100, height: 100, close: vi.fn() }),
    )
    const fakeCanvas = {
      width: 0,
      height: 0,
      getContext: vi.fn(() => ({ drawImage: vi.fn() })),
      toBlob: vi.fn((cb: (b: Blob | null) => void, type?: string) =>
        cb(new Blob(['jpeg'], { type })),
      ),
    }
    vi.stubGlobal('document', { createElement: vi.fn(() => fakeCanvas) })
    const file = new File([new Uint8Array([1])], 'IMG.HEIC', { type: 'image/heic' })
    const out = await preparePhotoForUpload(file)
    expect(out.ext).toBe('jpg')
    expect(out.contentType).toBe('image/jpeg')
    expect(out.blob.type).toBe('image/jpeg')
  })
})
