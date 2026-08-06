import { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { AlertTriangle, ArrowLeft, FileText, ImagePlus, Upload, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Tabs, TabsIndicator, TabsList, TabsPanel, TabsTab } from '@/components/ui/tabs'
import { useAuth } from '@/app/auth'
import { useRequestPackagingInspection, useStartInspection } from '@/data/hooks'
import type { PackagingLevel } from '@/data'
import { ru } from '@/i18n/ru'
import { CCard, CEyebrow } from '../ui'

const t = ru.packagingCheck

/** Грани кадра — те же значения, что распознаёт воркер (`face_name`), см. `src/data/vision.ts`. */
const FACES = ['front_panel', 'back_panel', 'side_panel', 'top', 'bottom'] as const
type Face = (typeof FACES)[number]
type SourceKind = 'photo' | 'master_pdf'

/**
 * Загрузка макета (PDF) или кадров (фото) и запуск проверки. Сабмит бьёт по
 * `useRequestPackagingInspection` (Storage + RPC `request_photo_inspection`),
 * затем — не дожидаясь ответа — `useStartInspection` (`POST /api/vision/check`,
 * синхронный и долгий): экран ожидания на `/checks/packaging/:id` живёт
 * поллингом (`useInspectionBundle`, Задача 13), а не этим промисом.
 */
export function CPackagingUpload({
  productId,
  level,
  hints,
  onBack,
}: {
  productId: string
  level: PackagingLevel
  hints?: string | string[]
  onBack: () => void
}) {
  const navigate = useNavigate()
  const { session } = useAuth()
  const request = useRequestPackagingInspection()
  const start = useStartInspection()

  const [tab, setTab] = useState<SourceKind>('photo')
  const [pdfFile, setPdfFile] = useState<File | null>(null)
  const [photos, setPhotos] = useState<{ file: File; face: Face }[]>([])
  const [errorReason, setErrorReason] = useState<string | null>(null)

  const pdfInputRef = useRef<HTMLInputElement>(null)
  const photoInputRef = useRef<HTMLInputElement>(null)

  const canStart = tab === 'master_pdf' ? Boolean(pdfFile) : photos.length >= 4

  function addPhotos(list: FileList | null) {
    if (!list || list.length === 0) return
    setPhotos((prev) => [
      ...prev,
      ...Array.from(list).map((file) => ({ file, face: 'front_panel' as Face })),
    ])
  }

  function removePhoto(i: number) {
    setPhotos((prev) => prev.filter((_, idx) => idx !== i))
  }

  function setFace(i: number, face: Face) {
    setPhotos((prev) => prev.map((p, idx) => (idx === i ? { ...p, face } : p)))
  }

  async function submit() {
    if (!canStart) return
    setErrorReason(null)
    try {
      const inspectionId = await request.mutateAsync({
        productId,
        level,
        sourceKind: tab,
        files: tab === 'master_pdf' ? (pdfFile ? [pdfFile] : []) : photos.map((p) => p.file),
        faces: tab === 'photo' ? photos.map((p) => p.face) : undefined,
      })
      // Не ждём: экран ожидания на /checks/packaging/:id живёт своим поллингом
      void start.mutateAsync(inspectionId).catch(() => {})
      navigate(`/checks/packaging/${inspectionId}`)
    } catch (e) {
      setErrorReason(reasonOf(e))
    }
  }

  if (!session) {
    return (
      <CCard className="p-8 text-center">
        <p className="text-sm leading-relaxed text-muted-foreground">{t.loginRequired}</p>
        <Button className="mt-4" nativeButton={false} render={<Link to="/login" />}>
          {ru.common.signIn}
        </Button>
      </CCard>
    )
  }

  const pending = request.isPending

  return (
    <div className="space-y-5">
      <Button variant="outline" size="sm" onClick={onBack} disabled={pending}>
        <ArrowLeft />
        {ru.common.back}
      </Button>

      {hints && (Array.isArray(hints) ? hints.length > 0 : hints.trim().length > 0) && (
        <CCard className="p-4">
          <CEyebrow>{t.shootingHints}</CEyebrow>
          {Array.isArray(hints) ? (
            <ul className="mt-2 space-y-1 text-sm leading-relaxed text-muted-foreground">
              {hints.map((h, i) => (
                <li key={i}>{h}</li>
              ))}
            </ul>
          ) : (
            <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{hints}</p>
          )}
        </CCard>
      )}

      <Tabs value={tab} onValueChange={(v) => setTab(v as SourceKind)}>
        <TabsList>
          <TabsIndicator />
          <TabsTab value="photo">{t.tabPhoto}</TabsTab>
          <TabsTab value="master_pdf">{t.tabPdf}</TabsTab>
        </TabsList>

        <TabsPanel value="photo" className="mt-4 space-y-4">
          <div>
            <p className="text-sm font-medium">{t.uploadPhotoTitle}</p>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{t.needFourFrames}</p>
          </div>
          <input
            ref={photoInputRef}
            type="file"
            accept="image/*,.heic,.heif"
            multiple
            capture="environment"
            className="hidden"
            onChange={(e) => {
              addPhotos(e.target.files)
              e.target.value = ''
            }}
          />
          <Button type="button" variant="outline" onClick={() => photoInputRef.current?.click()}>
            <ImagePlus />
            {t.uploadPhotoTitle}
          </Button>
          {photos.length > 0 && (
            <ul className="space-y-2">
              {photos.map((p, i) => (
                <li
                  key={i}
                  className="flex flex-wrap items-center gap-2.5 rounded-lg border border-border p-2.5"
                >
                  <span className="min-w-0 flex-1 truncate text-sm">
                    {t.frameLabel(i)} · {p.file.name}
                  </span>
                  <select
                    value={p.face}
                    onChange={(e) => setFace(i, e.target.value as Face)}
                    aria-label={t.faceLabel}
                    className="h-8 shrink-0 rounded-md border border-input bg-transparent px-2 text-xs outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
                  >
                    {FACES.map((f) => (
                      <option key={f} value={f}>
                        {t.faces[f]}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    onClick={() => removePhoto(i)}
                    aria-label={t.removeFile}
                    className="shrink-0 text-muted-foreground transition-colors hover:text-destructive"
                  >
                    <X className="size-4" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </TabsPanel>

        <TabsPanel value="master_pdf" className="mt-4 space-y-4">
          <div>
            <p className="text-sm font-medium">{t.uploadPdfTitle}</p>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{t.uploadPdfHint}</p>
          </div>
          <input
            ref={pdfInputRef}
            type="file"
            accept="application/pdf"
            className="hidden"
            onChange={(e) => {
              setPdfFile(e.target.files?.[0] ?? null)
              e.target.value = ''
            }}
          />
          {pdfFile ? (
            <div className="flex items-center gap-2.5 rounded-lg border border-border p-2.5">
              <FileText className="size-4 shrink-0 text-muted-foreground" aria-hidden />
              <span className="min-w-0 flex-1 truncate text-sm">{pdfFile.name}</span>
              <button
                type="button"
                onClick={() => setPdfFile(null)}
                aria-label={t.removeFile}
                className="shrink-0 text-muted-foreground transition-colors hover:text-destructive"
              >
                <X className="size-4" />
              </button>
            </div>
          ) : (
            <Button type="button" variant="outline" onClick={() => pdfInputRef.current?.click()}>
              <Upload />
              {t.uploadPdfTitle}
            </Button>
          )}
        </TabsPanel>
      </Tabs>

      {errorReason && (
        <div className="flex flex-wrap items-center gap-2 text-sm text-destructive">
          <AlertTriangle className="size-4 shrink-0" aria-hidden />
          <span>{reasonText(errorReason)}</span>
          {errorReason === 'not_subscriber' && (
            <Link to="/pricing" className="underline underline-offset-2">
              {ru.paywall.cta}
            </Link>
          )}
        </div>
      )}

      <Button disabled={!canStart || pending} onClick={submit}>
        {pending ? t.uploading : t.startCheck}
      </Button>
    </div>
  )
}

function reasonOf(e: unknown): string {
  if (e instanceof Error) return e.message
  if (e && typeof e === 'object' && 'message' in e) {
    return String((e as { message: unknown }).message)
  }
  return 'unknown'
}

function reasonText(reason: string): string {
  if (reason === 'quota_exhausted') return t.quotaExhausted
  if (reason === 'not_subscriber') return t.notSubscriber
  return t.checkFailed
}
