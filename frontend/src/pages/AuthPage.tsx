import { useState, type FormEvent } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRight, ShieldCheck, Sparkles } from 'lucide-react'
import { getSupabase } from '../lib/supabase'
import { errorMessage } from '../lib/errors'
import { minimumPasswordLength, validateAuth } from '../lib/validation'
import { Alert, Brand } from '../components/ui'

export function AuthPage({ register = false }: { register?: boolean }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmation, setConfirmation] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(null)
    setMessage('')
    const validation = validateAuth(
      email,
      password,
      register ? confirmation : undefined,
    )
    if (validation) {
      setError(validation)
      return
    }
    setBusy(true)
    try {
      if (register) {
        const { data, error } = await getSupabase().auth.signUp({
          email: email.trim(),
          password,
          options: { emailRedirectTo: `${window.location.origin}/dashboard` },
        })
        if (error) throw error
        if (!data.session) {
          setMessage(
            'Revisa tu correo para confirmar la cuenta. Si ya tienes una cuenta, inicia sesión.',
          )
          setPassword('')
          setConfirmation('')
        }
      } else {
        const { error } = await getSupabase().auth.signInWithPassword({
          email: email.trim(),
          password,
        })
        if (error) throw error
      }
    } catch (error) {
      setError(errorMessage(error))
    } finally {
      setBusy(false)
    }
  }
  return (
    <main className="auth-shell">
      <section className="auth-story">
        <Brand />
        <div>
          <span className="eyebrow light">
            <Sparkles size={16} /> INVESTIGA CON CLARIDAD
          </span>
          <h1>
            Tus datos.
            <br />
            Nuevas
            <br />
            <span>perspectivas.</span>
          </h1>
          <p>
            Un espacio para organizar tu investigación y dar el siguiente paso
            en tu análisis estadístico.
          </p>
        </div>
        <div className="story-footer">
          <ShieldCheck size={18} /> Tu investigación, en tu propio espacio.
        </div>
      </section>
      <section className="auth-form-side">
        <div className="auth-form">
          <span className="eyebrow">BIENVENIDO A STATIA</span>
          <h2>{register ? 'Crea tu cuenta' : 'Continúa tu investigación'}</h2>
          <p className="muted">
            {register
              ? 'Empieza a organizar tus proyectos en un solo lugar.'
              : 'Ingresa a tu espacio de trabajo.'}
          </p>
          <form onSubmit={submit} noValidate>
            {error && <Alert>{error}</Alert>}
            {message && (
              <div className="notice" role="status">
                {message}
              </div>
            )}
            <label>
              Correo electrónico
              <input
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="tu@universidad.edu"
              />
            </label>
            <label>
              Contraseña
              <input
                type="password"
                autoComplete={register ? 'new-password' : 'current-password'}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </label>
            {register && (
              <>
                <small className="muted">
                  Al menos {minimumPasswordLength} caracteres. Se aplican
                  también los requisitos de Supabase.
                </small>
                <label>
                  Confirmar contraseña
                  <input
                    type="password"
                    autoComplete="new-password"
                    required
                    value={confirmation}
                    onChange={(e) => setConfirmation(e.target.value)}
                  />
                </label>
              </>
            )}
            <button className="btn primary w-full" disabled={busy}>
              {busy
                ? 'Procesando…'
                : register
                  ? 'Crear cuenta'
                  : 'Iniciar sesión'}
              <ArrowRight size={18} />
            </button>
          </form>
          <p className="auth-switch">
            {register ? '¿Ya tienes una cuenta?' : '¿Es tu primera vez aquí?'}{' '}
            <Link to={register ? '/login' : '/registro'}>
              {register ? 'Inicia sesión' : 'Crea una cuenta'}
            </Link>
          </p>
        </div>
        <small className="muted">
          STATIA PLATFORM · UN ESPACIO PARA DESCUBRIR
        </small>
      </section>
    </main>
  )
}
