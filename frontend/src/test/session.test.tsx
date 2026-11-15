import { render, screen, waitFor, act } from '@testing-library/react'
import { beforeEach, expect, it, vi } from 'vitest'
import { AuthProvider } from '../components/AuthProvider'
import { useAuth } from '../hooks/auth-context'
import type { Session } from '@supabase/supabase-js'
const auth = vi.hoisted(() => ({
  getSession: vi.fn(),
  onAuthStateChange: vi.fn(),
  unsubscribe: vi.fn(),
}))
vi.mock('../lib/supabase', () => ({ supabase: { auth } }))
function Probe() {
  const { session, loading } = useAuth()
  return (
    <p>{loading ? 'inicializando' : (session?.user.email ?? 'sin sesión')}</p>
  )
}
beforeEach(() => vi.resetAllMocks())
it('recupera sesión persistida y escucha cierre de sesión', async () => {
  let listener: (event: string, session: Session | null) => void = () => {}
  auth.onAuthStateChange.mockImplementation((callback) => {
    listener = callback
    return { data: { subscription: { unsubscribe: auth.unsubscribe } } }
  })
  auth.getSession.mockResolvedValue({
    data: { session: { user: { email: 'ana@example.org' } } },
    error: null,
  })
  const { unmount } = render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  )
  expect(await screen.findByText('ana@example.org')).toBeInTheDocument()
  act(() => listener('SIGNED_OUT', null))
  await waitFor(() =>
    expect(screen.getByText('sin sesión')).toBeInTheDocument(),
  )
  unmount()
  expect(auth.unsubscribe).toHaveBeenCalledOnce()
})
