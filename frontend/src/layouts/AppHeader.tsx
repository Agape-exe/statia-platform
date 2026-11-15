import { useState } from 'react'
import { LogOut } from 'lucide-react'
import { useAuth } from '../hooks/auth-context'
import { getSupabase } from '../lib/supabase'
import { errorMessage } from '../lib/errors'
import { Alert, Brand } from '../components/ui'
export function AppHeader() {
  const { session } = useAuth()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  async function logout() {
    setBusy(true)
    setError(null)
    try {
      const { error } = await getSupabase().auth.signOut()
      if (error) throw error
    } catch (error) {
      setError(errorMessage(error))
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <header className="app-header">
        <Brand />
        <div className="user-menu">
          <span className="avatar">
            {session?.user.email?.[0]?.toUpperCase() || 'U'}
          </span>
          <span className="user-email">{session?.user.email}</span>
          <button
            className="btn secondary logout"
            onClick={logout}
            disabled={busy}
          >
            <LogOut size={17} />
            <span>{busy ? 'Saliendo…' : 'Cerrar sesión'}</span>
          </button>
        </div>
      </header>
      {error && <Alert>{error}</Alert>}
    </>
  )
}
