import { getSupabase } from './supabase'

export class ApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

export async function api<T>(
  path: string,
  init: RequestInit = {},
  blob = false,
): Promise<T> {
  const auth = getSupabase().auth
  const { data, error } = await auth.getSession()
  if (error || !data.session)
    throw new ApiError('Tu sesión venció. Vuelve a iniciar sesión.', 401)
  let token = data.session.access_token
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 165000)
  try {
    for (let attempt = 0; attempt < 2; attempt++) {
      const response = await fetch(
        `${(import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')}${path}`,
        {
          ...init,
          signal: controller.signal,
          headers: {
            ...(init.body && !(init.body instanceof FormData)
              ? { 'Content-Type': 'application/json' }
              : {}),
            ...init.headers,
            Authorization: `Bearer ${token}`,
          },
        },
      )
      if (response.status === 401 && attempt === 0) {
        const refreshed = await auth.refreshSession()
        if (refreshed.error || !refreshed.data.session) {
          await auth.signOut({ scope: 'local' })
          throw new ApiError('Tu sesión venció. Vuelve a iniciar sesión.', 401)
        }
        token = refreshed.data.session.access_token
        continue
      }
      if (!response.ok) {
        const body = (await response.json().catch(() => null)) as {
          detail?: unknown
        } | null
        throw new ApiError(
          typeof body?.detail === 'string'
            ? body.detail
            : 'No se pudo completar la solicitud. Comprueba los datos e inténtalo de nuevo.',
          response.status,
        )
      }
      return (
        response.status === 204
          ? undefined
          : blob
            ? await response.blob()
            : await response.json()
      ) as T
    }
    throw new ApiError('Tu sesión venció. Vuelve a iniciar sesión.', 401)
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError(
      'No se pudo conectar con el asistente o se agotó el tiempo de espera. Comprueba que la API esté disponible y reintenta.',
      0,
    )
  } finally {
    clearTimeout(timer)
  }
}
