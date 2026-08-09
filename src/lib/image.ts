/**
 * Подготовка кадра к заливке в бакет фотоконтроля: HEIC/EXIF-независимая
 * ориентация + сжатие до разумного размера. Чистая функция `targetSize` и
 * побочная `prepareImageForUpload` разделены — первую легко тестировать
 * без DOM, вторая нужна canvas/createImageBitmap браузера.
 */

/** Длинная сторона ужимается до `maxSide` (2048 по умолчанию), пропорции сохраняются. Меньший кадр не растягивается. */
export function targetSize(w: number, h: number, maxSide = 2048): { w: number; h: number } {
  const long = Math.max(w, h)
  if (long <= maxSide) return { w, h }
  const scale = maxSide / long
  if (w >= h) return { w: maxSide, h: Math.floor(h * scale) }
  return { w: Math.floor(w * scale), h: maxSide }
}

/**
 * HEIC/HEIF → JPEG, EXIF-ориентация применяется декодером (`imageOrientation:
 * 'from-image'`), длинная сторона ≤ 2048px. `createImageBitmap` сам разбирает
 * форматы, зашитые в бакет `packaging-photos` (jpeg/png/heic/heif, см.
 * 20260810110000_photo_storage.sql).
 */
export async function prepareImageForUpload(file: File): Promise<Blob> {
  const bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' })
  try {
    const { w, h } = targetSize(bitmap.width, bitmap.height)
    const canvas = document.createElement('canvas')
    canvas.width = w
    canvas.height = h
    const ctx = canvas.getContext('2d')
    if (!ctx) throw new Error('canvas_context_unavailable')
    ctx.drawImage(bitmap, 0, 0, w, h)
    return await new Promise<Blob>((resolve, reject) => {
      canvas.toBlob(
        (blob) => (blob ? resolve(blob) : reject(new Error('canvas_to_blob_failed'))),
        'image/jpeg',
        0.85,
      )
    })
  } finally {
    bitmap.close()
  }
}
