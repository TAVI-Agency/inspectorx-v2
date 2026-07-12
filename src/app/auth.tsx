import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from 'react'
import type { Session } from '@supabase/supabase-js'
import { supabase } from '@/lib/supabase'

interface Profile {
  fullName: string
  company?: string
  isSubscribed: boolean
}

interface AuthCtx {
  session: Session | null
  profile: Profile | null
  /** Auth ещё инициализируется — не дёргать редиректы */
  loading: boolean
  realSubscriber: boolean
  signIn: (email: string, password: string) => Promise<{ error?: string }>
  signUp: (
    email: string,
    password: string,
    fullName: string,
  ) => Promise<{ error?: string; needsConfirmation?: boolean }>
  /** Повторно отправить письмо подтверждения регистрации */
  resendConfirmation: (email: string) => Promise<{ error?: string }>
  /** Письмо со ссылкой на смену пароля */
  requestPasswordReset: (email: string) => Promise<{ error?: string }>
  /** Смена пароля у текущей (recovery) сессии */
  updatePassword: (password: string) => Promise<{ error?: string }>
  signOut: () => Promise<void>
}

/** Ссылки в письмах должны вести на текущий домен, а не на Site URL проекта */
const emailRedirect = (path: string) => `${window.location.origin}${path}`

const Ctx = createContext<AuthCtx | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [profile, setProfile] = useState<Profile | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session)
      setLoading(false)
    })
    const { data: sub } = supabase.auth.onAuthStateChange((_event, s) => {
      setSession(s)
    })
    return () => sub.subscription.unsubscribe()
  }, [])

  useEffect(() => {
    let cancelled = false
    if (!session) {
      setProfile(null)
      return
    }
    supabase
      .from('profiles')
      .select('full_name, company, is_subscribed')
      .eq('id', session.user.id)
      .maybeSingle()
      .then(({ data }) => {
        if (cancelled) return
        setProfile(
          data
            ? {
                fullName: data.full_name,
                company: data.company ?? undefined,
                isSubscribed: data.is_subscribed,
              }
            : null,
        )
      })
    return () => {
      cancelled = true
    }
  }, [session])

  const signIn = useCallback(async (email: string, password: string) => {
    const { error } = await supabase.auth.signInWithPassword({ email, password })
    return error ? { error: error.message } : {}
  }, [])

  const signUp = useCallback(
    async (email: string, password: string, fullName: string) => {
      const { data, error } = await supabase.auth.signUp({
        email,
        password,
        options: {
          data: { full_name: fullName },
          emailRedirectTo: emailRedirect('/auth/confirm'),
        },
      })
      if (error) return { error: error.message }
      // При включённом подтверждении почты Supabase не выдаёт ошибку на занятый
      // email (анти-перечисление), а возвращает пользователя без identities.
      if (data.user && data.user.identities?.length === 0)
        return { error: 'already registered' }
      return { needsConfirmation: !data.session }
    },
    [],
  )

  const resendConfirmation = useCallback(async (email: string) => {
    const { error } = await supabase.auth.resend({
      type: 'signup',
      email,
      options: { emailRedirectTo: emailRedirect('/auth/confirm') },
    })
    return error ? { error: error.message } : {}
  }, [])

  const requestPasswordReset = useCallback(async (email: string) => {
    const { error } = await supabase.auth.resetPasswordForEmail(email, {
      redirectTo: emailRedirect('/auth/reset'),
    })
    return error ? { error: error.message } : {}
  }, [])

  const updatePassword = useCallback(async (password: string) => {
    const { error } = await supabase.auth.updateUser({ password })
    return error ? { error: error.message } : {}
  }, [])

  const signOut = useCallback(async () => {
    await supabase.auth.signOut()
  }, [])

  return (
    <Ctx.Provider
      value={{
        session,
        profile,
        loading,
        realSubscriber: profile?.isSubscribed ?? false,
        signIn,
        signUp,
        resendConfirmation,
        requestPasswordReset,
        updatePassword,
        signOut,
      }}
    >
      {children}
    </Ctx.Provider>
  )
}

export function useAuth(): AuthCtx {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useAuth outside AuthProvider')
  return ctx
}
