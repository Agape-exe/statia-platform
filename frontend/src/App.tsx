import { BrowserRouter, Link, Navigate, Route, Routes } from 'react-router-dom'
import { lazy, Suspense } from 'react'
import { AuthProvider } from './components/AuthProvider'
import { PrivateRoute, PublicRoute } from './components/RouteGuards'
import { AuthPage } from './pages/AuthPage'
import { Dashboard } from './pages/Dashboard'
import { supabase } from './lib/supabase'
import { Brand, Loading } from './components/ui'

const Workspace = lazy(() =>
  import('./pages/Workspace').then((module) => ({ default: module.Workspace })),
)

export default function App() {
  return (
    <BrowserRouter>
      {!supabase ? (
        <main className="setup-page">
          <Brand />
          <h1>Conecta tu espacio de trabajo</h1>
          <p>
            Configura <code>frontend/.env.local</code> con{' '}
            <code>VITE_SUPABASE_URL</code> y{' '}
            <code>VITE_SUPABASE_PUBLISHABLE_KEY</code>, y reinicia Vite.
          </p>
          <p>
            Consulta docs/SETUP.md para ejecutar la migración y activar la
            autenticación real.
          </p>
        </main>
      ) : (
        <AuthProvider>
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route element={<PublicRoute />}>
              <Route path="/login" element={<AuthPage key="login" />} />
              <Route
                path="/registro"
                element={<AuthPage key="register" register />}
              />
            </Route>
            <Route element={<PrivateRoute />}>
              <Route path="/dashboard" element={<Dashboard />} />
              <Route
                path="/proyectos/:projectId"
                element={
                  <Suspense fallback={<Loading />}>
                    <Workspace />
                  </Suspense>
                }
              />
              <Route
                path="/proyectos/:projectId/:module"
                element={
                  <Suspense fallback={<Loading />}>
                    <Workspace />
                  </Suspense>
                }
              />
            </Route>
            <Route
              path="*"
              element={
                <main className="setup-page">
                  <h1>Página no encontrada</h1>
                  <Link to="/dashboard">Ir al dashboard</Link>
                </main>
              }
            />
          </Routes>
        </AuthProvider>
      )}
    </BrowserRouter>
  )
}
