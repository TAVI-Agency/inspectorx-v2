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
  if (typeof createImageBitmap !== 'function') throw new Error('create_image_bitmap_unsupported')
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

/** Расширение и MIME по имени/типу файла — только форматы, зашитые в бакет `packaging-photos`. */
const PHOTO_FORMATS: Record<string, string> = {
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  png: 'image/png',
  heic: 'image/heic',
  heif: 'image/heif',
}

/**
 * Кадр к заливке с деградацией: пытаемся конвертировать в JPEG на клиенте
 * (быстрее и меньше трафика), а если браузер формат не декодирует — например,
 * HEIC с айфона в Chrome/Firefox — грузим ОРИГИНАЛ как есть: бакет принимает
 * heic/heif, а воркер разворачивает их сам через pillow-heif (это и есть
 * «вторая страховка» плана §2Б шаг 3). Ошибка `unsupported_image` — только
 * когда файл не входит в форматы бакета и конвертация тоже не удалась.
 */
export async function preparePhotoForUpload(
  file: File,
): Promise<{ blob: Blob; ext: string; contentType: string }> {
  try {
    const blob = await prepareImageForUpload(file)
    return { blob, ext: 'jpg', contentType: 'image/jpeg' }
  } catch {
    const extFromName = file.name.split('.').pop()?.toLowerCase() ?? ''
    const extFromType = Object.keys(PHOTO_FORMATS).find((e) => PHOTO_FORMATS[e] === file.type)
    const ext = PHOTO_FORMATS[extFromName] ? extFromName : extFromType
    if (!ext) throw new Error('unsupported_image')
    return { blob: file, ext, contentType: PHOTO_FORMATS[ext] }
  }
}
