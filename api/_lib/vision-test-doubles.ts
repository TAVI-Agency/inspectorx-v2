// Тестовые дублёры для api/vision/*: поддельный клиент Supabase и объект
// ответа Vercel. Живой сети и живой базы в этих тестах нет — проверяется
// проводка: какие запросы уходят, какой код и тело возвращаются.
//
// Файл лежит в api/_lib/ (директория с подчёркиванием), поэтому Vercel его в
// деплой не берёт; суффикс имени не .test.ts — значит и vitest его не запускает.
import type { VercelRequest, VercelResponse } from '@vercel/node'

export interface FakeResult {
  data?: unknown
  error?: unknown
}

/**
 * Маршруты ответов поддельной базы. Ключ — `<таблица>.<операция>`,
 * `rpc.<имя>`, `storage.<бакет>.<операция>` или `auth.getUser`.
 * Массив значений разбирается по очереди (последнее залипает) — так
 * различаются два обращения к одной таблице внутри одного эндпоинта.
 */
export type FakeRoutes = Record<string, FakeResult | FakeResult[]>

export interface RecordedCall {
  key: string
  table: string
  op: string
  columns?: string
  payload?: unknown
  filters: Array<{ method: string; column: string; value: unknown }>
  args?: unknown
}

const EMPTY: FakeResult = { data: null, error: null }

class FakeQuery implements PromiseLike<FakeResult> {
  constructor(
    private readonly db: FakeDb,
    private readonly call: RecordedCall,
  ) {}

  private setOp(op: string): void {
    // select после insert/update не должен подменять операцию вызова
    if (!this.call.op) this.call.op = op
  }

  select(columns?: string): this {
    this.call.columns = columns
    this.setOp('select')
    return this
  }

  insert(payload: unknown): this {
    this.call.op = 'insert'
    this.call.payload = payload
    return this
  }

  update(payload: unknown): this {
    this.call.op = 'update'
    this.call.payload = payload
    return this
  }

  upsert(payload: unknown): this {
    this.call.op = 'upsert'
    this.call.payload = payload
    return this
  }

  eq(column: string, value: unknown): this {
    this.call.filters.push({ method: 'eq', column, value })
    return this
  }

  neq(column: string, value: unknown): this {
    this.call.filters.push({ method: 'neq', column, value })
    return this
  }

  order(column: string): this {
    this.call.filters.push({ method: 'order', column, value: null })
    return this
  }

  limit(n: number): this {
    this.call.filters.push({ method: 'limit', column: '', value: n })
    return this
  }

  maybeSingle(): Promise<FakeResult> {
    return this.settle()
  }

  single(): Promise<FakeResult> {
    return this.settle()
  }

  then<TResult1 = FakeResult, TResult2 = never>(
    onfulfilled?: ((value: FakeResult) => TResult1 | PromiseLike<TResult1>) | null,
    onrejected?: ((reason: unknown) => TResult2 | PromiseLike<TResult2>) | null,
  ): PromiseLike<TResult1 | TResult2> {
    return this.settle().then(onfulfilled, onrejected)
  }

  private settle(): Promise<FakeResult> {
    this.call.key = `${this.call.table}.${this.call.op}`
    this.db.record(this.call)
    return Promise.resolve(this.db.take(this.call.key))
  }
}

export class FakeDb {
  readonly calls: RecordedCall[] = []
  private readonly queues = new Map<string, FakeResult[]>()

  constructor(routes: FakeRoutes = {}) {
    for (const [key, value] of Object.entries(routes)) {
      this.queues.set(key, Array.isArray(value) ? [...value] : [value])
    }
  }

  record(call: RecordedCall): void {
    this.calls.push(call)
  }

  take(key: string): FakeResult {
    const queue = this.queues.get(key)
    if (!queue || queue.length === 0) return EMPTY
    // последний ответ залипает: повторный вызов вернёт то же самое
    return queue.length === 1 ? queue[0] : (queue.shift() as FakeResult)
  }

  /** Все вызовы по ключу `<таблица>.<операция>`. */
  callsFor(key: string): RecordedCall[] {
    return this.calls.filter((c) => c.key === key)
  }

  from(table: string): FakeQuery {
    return new FakeQuery(this, { key: '', table, op: '', filters: [] })
  }

  rpc(name: string, args?: unknown): Promise<FakeResult> {
    const key = `rpc.${name}`
    this.record({ key, table: 'rpc', op: name, filters: [], args })
    return Promise.resolve(this.take(key))
  }

  readonly auth = {
    getUser: (jwt: string): Promise<{ data: { user: { id: string } | null }; error: unknown }> => {
      const key = 'auth.getUser'
      this.record({ key, table: 'auth', op: 'getUser', filters: [], args: jwt })
      const result = this.take(key)
      const user = (result.data ?? null) as { id: string } | null
      return Promise.resolve({ data: { user }, error: result.error ?? null })
    },
  }

  readonly storage = {
    from: (bucket: string) => ({
      createSignedUrls: (paths: string[], ttl: number): Promise<FakeResult> => {
        const key = `storage.${bucket}.createSignedUrls`
        this.record({ key, table: bucket, op: 'createSignedUrls', filters: [], args: { paths, ttl } })
        return Promise.resolve(this.take(key))
      },
      upload: (path: string, body: unknown, options?: unknown): Promise<FakeResult> => {
        const key = `storage.${bucket}.upload`
        this.record({ key, table: bucket, op: 'upload', filters: [], args: { path, body, options } })
        return Promise.resolve(this.take(key))
      },
    }),
  }
}

export function makeFakeDb(routes: FakeRoutes = {}): FakeDb {
  return new FakeDb(routes)
}

export interface FakeResponse {
  statusCode: number
  body: unknown
  headers: Record<string, string>
  res: VercelResponse
}

/** Минимальный VercelResponse: запоминает код, заголовки и тело. */
export function makeFakeResponse(): FakeResponse {
  const captured: FakeResponse = {
    statusCode: 0,
    body: undefined,
    headers: {},
    res: undefined as unknown as VercelResponse,
  }
  const res = {
    status(code: number) {
      captured.statusCode = code
      return this
    },
    json(body: unknown) {
      captured.body = body
      return this
    },
    send(body: unknown) {
      captured.body = body
      return this
    },
    setHeader(name: string, value: string) {
      captured.headers[name.toLowerCase()] = value
      return this
    },
  }
  captured.res = res as unknown as VercelResponse
  return captured
}

export function makeRequest(init: {
  method?: string
  headers?: Record<string, string>
  body?: unknown
  query?: Record<string, string>
}): VercelRequest {
  return {
    method: init.method ?? 'POST',
    headers: init.headers ?? {},
    body: init.body,
    query: init.query ?? {},
  } as unknown as VercelRequest
}
