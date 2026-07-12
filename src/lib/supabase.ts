import { createClient } from '@supabase/supabase-js'
import type { Database } from './database.types'

/**
 * Дефолты — ПУБЛИЧНЫЕ клиентские реквизиты (URL + publishable key):
 * они в любом случае попадают в собранный JS каждому посетителю,
 * доступ к данным ограничивает серверный RLS. Зашиты, чтобы деплой
 * (Vercel) работал без настройки переменных окружения; .env локально
 * может их переопределить (например, на staging-проект).
 */
const supabaseUrl =
  import.meta.env.VITE_SUPABASE_URL || 'https://kcjlrvgjtoefqgzxuizz.supabase.co'
const supabaseKey =
  import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY ||
  'sb_publishable_ngXsHHKb-TWw0UcB_o_V5w_jcSOMBsD'

export const supabase = createClient<Database>(supabaseUrl, supabaseKey)
