import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '../lib/api'

const auth = vi.hoisted(() => ({
  getSession: vi.fn(),
  refreshSession: vi.fn(),
  signOut: vi.fn(),
}))
vi.mock('../lib/supabase', () => ({ getSupabase: () => ({ auth }) }))
beforeEach(() => {
  vi.resetAllMocks()
  auth.getSession.mockResolvedValue({
    data: { session: { access_token: 'token-inicial' } },
    error: null,
  })
})
afterEach(() => vi.unstubAllGlobals())

describe('cliente autenticado de la API', () => {
  it('envía el JWT y renueva la sesión una sola vez ante 401', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValueOnce(new Response('{}', { status: 401 }))
      .mockResolvedValueOnce(new Response('{"ok":true}', { status: 200 }))
    vi.stubGlobal('fetch', fetcher)
    auth.refreshSession.mockResolvedValue({
      data: { session: { access_token: 'token-renovado' } },
      error: null,
    })
    expect(await api('/ruta')).toEqual({ ok: true })
    expect(fetcher.mock.calls[0][1].headers.Authorization).toBe(
      'Bearer token-inicial',
    )
    expect(fetcher.mock.calls[1][1].headers.Authorization).toBe(
      'Bearer token-renovado',
    )
    expect(auth.refreshSession).toHaveBeenCalledOnce()
  })

  it('permite recuperar autenticación cuando la renovación falla', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('{}', { status: 401 })),
    )
    auth.refreshSession.mockResolvedValue({
      data: { session: null },
      error: new Error('Vencido'),
    })
    await expect(api('/ruta')).rejects.toMatchObject({ status: 401 })
    expect(auth.signOut).toHaveBeenCalledWith({ scope: 'local' })
  })

  it('conserva el error del proveedor y no repite automáticamente el turno', async () => {
    const fetcher = vi
      .fn()
      .mockResolvedValue(
        new Response('{"detail":"Cuota agotada"}', { status: 429 }),
      )
    vi.stubGlobal('fetch', fetcher)
    await expect(
      api('/ruta', { method: 'POST', body: '{}' }),
    ).rejects.toMatchObject({ message: 'Cuota agotada', status: 429 })
    expect(fetcher).toHaveBeenCalledOnce()
  })

  it('informa fallos de red y no consulta sin sesión', async () => {
    const fetcher = vi.fn().mockRejectedValue(new TypeError('network'))
    vi.stubGlobal('fetch', fetcher)
    await expect(api('/ruta')).rejects.toMatchObject({ status: 0 })
    auth.getSession.mockResolvedValue({ data: { session: null }, error: null })
    await expect(api('/ruta')).rejects.toMatchObject({ status: 401 })
    expect(fetcher).toHaveBeenCalledOnce()
  })
})
