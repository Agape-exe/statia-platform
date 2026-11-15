import { useEffect, useState, type ReactNode } from 'react'
import type { Session } from '@supabase/supabase-js'
import { supabase } from '../lib/supabase'
import { errorMessage } from '../lib/errors'
import { AuthContext } from '../hooks/auth-context'

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  useEffect(() => {
    if (!supabase) return
    let active = true
    let receivedEvent = false
    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, next) => {
      receivedEvent = true
      if (active) {
        setSession(next)
        setLoading(false)
        setError(null)
      }
    })
    supabase.auth
      .getSession()
      .then(({ data, error }) => {
        if (!active || receivedEvent) return
        setSession(data.session)
        setLoading(false)
        if (error) setError(errorMessage(error))
      })
      .catch((error: unknown) => {
        if (active && !receivedEvent) {
          setError(errorMessage(error))
          setLoading(false)
        }
      })
    return () => {
      active = false
      subscription.unsubscribe()
    }
  }, [])
  return (
    <AuthContext.Provider value={{ session, loading, error }}>
      {children}
    </AuthContext.Provider>
  )
}
