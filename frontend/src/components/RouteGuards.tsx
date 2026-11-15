import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '../hooks/auth-context'
import { Alert, Loading } from './ui'
export function PrivateRoute() {
  const { session, loading, error } = useAuth()
  if (loading) return <Loading />
  if (error)
    return (
      <Alert>
        {error}{' '}
        <button onClick={() => window.location.reload()}>Reintentar</button>
      </Alert>
    )
  return session ? (
    <Outlet key={session.user.id} />
  ) : (
    <Navigate to="/login" replace />
  )
}
export function PublicRoute() {
  const { session, loading, error } = useAuth()
  if (loading) return <Loading />
  return session ? (
    <Navigate to="/dashboard" replace />
  ) : (
    <>
      {error && <Alert>{error}</Alert>}
      <Outlet />
    </>
  )
}
