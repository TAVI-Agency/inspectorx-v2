// Общий слой api/vision/*: админ-клиент, аутентификация, проверки путей.
// SUPABASE_SERVICE_ROLE_KEY живёт только в process.env на сервере (вне src/),
// Vite этот файл не собирает — в клиентский бандл он не попадает.
//
// Единственный писатель в photo_* — эти функции под service_role через
// SECURITY DEFINER RPC. Воркер в базу не ходит: он получает подписанные
// ссылки и отдаёт результат телом ответа.
import type { VercelRequest, VercelResponse } from '@vercel/node'
import { createClient, type SupabaseClient } from '@supabase/supabase-js'
import type { Database } from '../../src/lib/database.types.js'

// Дословная копия списка refundable из finalize_photo_inspection
// (supabase/migrations/20260810100000_photo_runtime.sql). Возврат квоты решает
// RPC, здесь список нужен, чтобы отличать «наша инфраструктура подвела» от
// «данные не годятся» при выборе кода ответа и в тестах — расхождение с
// миграцией ловится тестом.
export const REFUNDABLE_REASONS: ReadonlySet<string> = new Set([
  'worker_unreachable', 'worker_timeout', 'dispatch_lost',
  'ruleset_drift', 'ocr_unavailable', 'vlm_unavailable',
])

/**
 * Отсутствие обязательной переменной окружения. Отдельный класс, чтобы
 * обёртка withVisionGuards отвечала машинным кодом, а не пятисоткой без
 * объяснения: VISION_WORKER_URL/VISION_WORKER_SECRET появляются только в
 * Волне 3, до тех пор эндпоинты обязаны внятно говорить, чего им не хватает.
 */
export class VisionConfigError extends Error {
  constructor(
    readonly reason: 'server_misconfigured' | 'worker_not_configured',
    message: string,
  ) {
    super(message)
    this.name = 'VisionConfigError'
  }
}

export function adminClient(): SupabaseClient<Database> {
  // SUPABASE_URL — серверная переменная, VITE_SUPABASE_URL — запасной
  // вариант (значение публичное, секрета в нём нет), как в api/calendar.
  const url = process.env.SUPABASE_URL ?? process.env.VITE_SUPABASE_URL
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY
  if (!url || !key) {
    throw new VisionConfigError(
      'server_misconfigured',
      'missing SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY',
    )
  }
  // Клиент создаётся на каждый вызов намеренно: переменные окружения читаются
  // в момент обращения, кэш на уровне модуля пережил бы их подмену.
  return createClient<Database>(url, key, { auth: { persistSession: false } })
}

export async function getUserFromRequest(
  req: VercelRequest,
): Promise<{ id: string } | null> {
  const header = req.headers.authorization ?? ''
  const jwt = header.startsWith('Bearer ') ? header.slice(7) : ''
  if (!jwt) return null
  const { data, error } = await adminClient().auth.getUser(jwt)
  if (error || !data.user) return null
  return { id: data.user.id }
}

export function requireWorkerSecret(req: VercelRequest): boolean {
  const secret = process.env.VISION_WORKER_SECRET
  return Boolean(secret) && req.headers['x-worker-secret'] === secret
}

/**
 * Все пути обязаны лежать под собственным префиксом пользователя. Пустой
 * список — тоже отказ: нечего подписывать. `..` запрещён целиком, а не
 * нормализуется: путь в Storage мы формируем сами, легальных `..` в нём нет.
 */
export function assertOwnPrefix(paths: string[], userId: string): boolean {
  if (paths.length === 0) return false
  return paths.every(
    (p) => p.startsWith(`${userId}/`) && !p.includes('..'),
  )
}

export function bucketFor(kind: 'photo' | 'master_pdf'): string {
  return kind === 'master_pdf' ? 'packaging-artwork' : 'packaging-photos'
}

/** Бакет кропов-доказательств: пишет только сервер, пользователь читает своё. */
export const EVIDENCE_BUCKET = 'evidence-crops'

export function workerUrl(): string {
  const url = process.env.VISION_WORKER_URL
  if (!url) {
    throw new VisionConfigError('worker_not_configured', 'missing VISION_WORKER_URL')
  }
  return url.replace(/\/$/, '')
}

/** Секрет исходящего запроса к воркеру. Без него воркер ответит 401. */
export function workerSecret(): string {
  const secret = process.env.VISION_WORKER_SECRET
  if (!secret) {
    throw new VisionConfigError('worker_not_configured', 'missing VISION_WORKER_SECRET')
  }
  return secret
}

export type VisionHandler = (req: VercelRequest, res: VercelResponse) => Promise<void>

/**
 * Обёртка эндпоинтов: непойманное исключение никогда не должно уходить
 * пользователю стектрейсом. Нехватка конфигурации — 503 (воркер не подключён)
 * или 500 (нет доступа к своей же базе), всё прочее — 500 internal.
 */
export function withVisionGuards(handler: VisionHandler): VisionHandler {
  return async (req, res) => {
    try {
      await handler(req, res)
    } catch (err) {
      if (err instanceof VisionConfigError) {
        console.error('vision: конфигурация неполна', err.message)
        res.status(err.reason === 'worker_not_configured' ? 503 : 500)
          .json({ reason: err.reason })
        return
      }
      console.error('vision: необработанная ошибка', err)
      res.status(500).json({ reason: 'internal' })
    }
  }
}
