import { afterEach, describe, expect, it, vi } from 'vitest'

import { prepareImageForUpload, targetSize } from './image'

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
