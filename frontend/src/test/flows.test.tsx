import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import type { Session } from '@supabase/supabase-js'
import { AuthContext } from '../hooks/auth-context'
import { PrivateRoute, PublicRoute } from '../components/RouteGuards'
import { AuthPage } from '../pages/AuthPage'
import { Dashboard } from '../pages/Dashboard'
import { Workspace } from '../pages/Workspace'
import { projectsService } from '../services/projects'
import { validateAuth, validateProject } from '../lib/validation'
import type { Project } from '../types/project'

const auth = vi.hoisted(() => ({
  signUp: vi.fn(),
  signInWithPassword: vi.fn(),
  signOut: vi.fn(),
}))
vi.mock('../lib/supabase', () => ({ getSupabase: () => ({ auth }) }))
vi.mock('../services/projects', () => ({
  projectsService: {
    list: vi.fn(),
    get: vi.fn(),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
  },
}))
const session = { user: { id: 'user-a', email: 'ana@example.org' } } as Session
const project: Project = {
  id: 'project-a',
  user_id: 'user-a',
  name: 'Mi investigación',
  description: 'Objetivo de estudio',
  project_type: 'thesis',
  created_at: '2026-11-15T12:00:00Z',
  updated_at: '2026-11-15T12:00:00Z',
}
function wrapper(
  node: React.ReactNode,
  path = '/',
  loggedIn = true,
  loading = false,
) {
  return render(
    <AuthContext.Provider
      value={{ session: loggedIn ? session : null, loading, error: null }}
    >
      <MemoryRouter initialEntries={[path]}>{node}</MemoryRouter>
    </AuthContext.Provider>,
  )
}
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(projectsService.list).mockResolvedValue([])
  auth.signOut.mockResolvedValue({ error: null })
})

describe('validaciones', () => {
  it('rechaza correo, contraseña corta y confirmación diferente', () => {
    expect(validateAuth('correo', 'password')).toMatch(/correo/)
    expect(validateAuth('ana@example.org', 'a', 'a')).toMatch(/caracteres/)
    expect(validateAuth('ana@example.org', 'abcdefgh', 'abcdefghi')).toMatch(
      /coinciden/,
    )
    expect(validateAuth('ana@example.org', 'abcdefgh', 'abcdefgh')).toBeNull()
  })
  it('exige nombre, tipo y límites coherentes con SQL', () => {
    expect(
      validateProject({ name: '   ', description: '', project_type: 'thesis' }),
    ).toMatch(/nombre/)
    expect(
      validateProject({
        name: 'Tesis',
        description: 'a'.repeat(2001),
        project_type: 'general',
      }),
    ).toMatch(/2000/)
  })
})
describe('rutas de autenticación', () => {
  const routes = (
    <Routes>
      <Route element={<PrivateRoute />}>
        <Route path="/dashboard" element={<p>Privado</p>} />
      </Route>
      <Route element={<PublicRoute />}>
        <Route path="/login" element={<p>Ingreso</p>} />
      </Route>
    </Routes>
  )
  it('redirige a login sin sesión', async () => {
    wrapper(routes, '/dashboard', false)
    expect(await screen.findByText('Ingreso')).toBeInTheDocument()
    expect(screen.queryByText('Privado')).not.toBeInTheDocument()
  })
  it('no redirige mientras inicializa', () => {
    wrapper(routes, '/dashboard', false, true)
    expect(screen.getByRole('status')).toHaveTextContent('Cargando')
    expect(screen.queryByText('Ingreso')).not.toBeInTheDocument()
  })
  it('redirige del login al dashboard con sesión', async () => {
    wrapper(routes, '/login')
    expect(await screen.findByText('Privado')).toBeInTheDocument()
  })
})
describe('formularios de autenticación', () => {
  it('informa confirmación por correo sin asumir sesión', async () => {
    auth.signUp.mockResolvedValue({ data: { session: null }, error: null })
    wrapper(<AuthPage register />, '/', false)
    const user = userEvent.setup()
    await user.type(
      screen.getByLabelText('Correo electrónico'),
      'ana@example.org',
    )
    await user.type(
      screen.getByLabelText('Contraseña', { exact: true }),
      'abcdefgh',
    )
    await user.type(screen.getByLabelText('Confirmar contraseña'), 'abcdefgh')
    await user.click(screen.getByRole('button', { name: 'Crear cuenta' }))
    expect(await screen.findByRole('status')).toHaveTextContent(
      'Revisa tu correo',
    )
    expect(auth.signUp).toHaveBeenCalledOnce()
  })
  it('muestra errores comprensibles del login', async () => {
    auth.signInWithPassword.mockResolvedValue({
      error: { code: 'invalid_credentials' },
    })
    wrapper(<AuthPage />, '/', false)
    const user = userEvent.setup()
    await user.type(
      screen.getByLabelText('Correo electrónico'),
      'ana@example.org',
    )
    await user.type(screen.getByLabelText('Contraseña'), 'incorrecta')
    await user.click(screen.getByRole('button', { name: 'Iniciar sesión' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('incorrectos')
  })
})
describe('proyectos', () => {
  it('crea y abre el proyecto guardado', async () => {
    vi.mocked(projectsService.create).mockResolvedValue(project)
    wrapper(
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route
          path="/proyectos/:projectId/asistente"
          element={<p>Proyecto abierto</p>}
        />
      </Routes>,
    )
    const user = userEvent.setup()
    await user.click(
      await screen.findByRole('button', { name: 'Crear mi primer proyecto' }),
    )
    await user.type(screen.getByLabelText('Nombre del proyecto'), project.name)
    await user.click(screen.getByRole('radio', { name: /Análisis para tesis/ }))
    await user.click(screen.getByRole('button', { name: 'Crear proyecto' }))
    expect(await screen.findByText('Proyecto abierto')).toBeInTheDocument()
    expect(projectsService.create).toHaveBeenCalledWith(
      expect.objectContaining({ project_type: 'thesis' }),
      'user-a',
    )
  })
  it('edita, mantiene tipo fijo y elimina con confirmación', async () => {
    vi.mocked(projectsService.list).mockResolvedValue([project])
    vi.mocked(projectsService.update).mockResolvedValue({
      ...project,
      name: 'Nombre editado',
    })
    vi.mocked(projectsService.remove).mockResolvedValue({ id: project.id })
    wrapper(<Dashboard />)
    const user = userEvent.setup()
    await user.click(
      await screen.findByRole('button', { name: `Editar ${project.name}` }),
    )
    expect(
      screen
        .getAllByRole('radio')
        .every((r) => (r as HTMLInputElement).disabled),
    ).toBe(true)
    await user.clear(screen.getByLabelText('Nombre del proyecto'))
    await user.type(
      screen.getByLabelText('Nombre del proyecto'),
      'Nombre editado',
    )
    await user.click(screen.getByRole('button', { name: 'Guardar cambios' }))
    expect(
      await screen.findByRole('heading', { name: 'Nombre editado' }),
    ).toBeInTheDocument()
    await user.click(
      screen.getByRole('button', { name: 'Eliminar Nombre editado' }),
    )
    expect(projectsService.remove).not.toHaveBeenCalled()
    expect(screen.getByRole('dialog')).toHaveTextContent('Nombre editado')
    await user.click(screen.getByRole('button', { name: 'Eliminar proyecto' }))
    expect(
      await screen.findByText('Un nuevo espacio para tus ideas'),
    ).toBeInTheDocument()
  })
  it('permite reintentar una consulta fallida', async () => {
    vi.mocked(projectsService.list).mockRejectedValueOnce(new Error('network'))
    wrapper(<Dashboard />)
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Reintentar' }))
    expect(
      await screen.findByText('Un nuevo espacio para tus ideas'),
    ).toBeInTheDocument()
  })
  it('cierra sesión mediante Supabase', async () => {
    wrapper(<Dashboard />)
    await userEvent.click(screen.getByRole('button', { name: 'Cerrar sesión' }))
    expect(auth.signOut).toHaveBeenCalledOnce()
  })
})
describe('espacio de trabajo', () => {
  function workspace() {
    return (
      <Routes>
        <Route path="/proyectos/:projectId/:module" element={<Workspace />} />
      </Routes>
    )
  }
  it('ofrece los cuatro módulos de tesis', async () => {
    vi.mocked(projectsService.get).mockResolvedValue(project)
    wrapper(workspace(), '/proyectos/project-a/asistente')
    expect(
      await screen.findByRole('link', { name: 'Contexto' }),
    ).toBeInTheDocument()
    for (const name of ['Datos', 'Resultados', 'Asistente Estadístico'])
      expect(screen.getByRole('link', { name })).toBeInTheDocument()
  })
  it('bloquea Contexto por URL en proyectos generales', async () => {
    vi.mocked(projectsService.get).mockResolvedValue({
      ...project,
      project_type: 'general',
    })
    wrapper(workspace(), '/proyectos/project-a/contexto')
    expect(
      await screen.findByRole('heading', { name: 'Asistente Estadístico' }),
    ).toBeInTheDocument()
    expect(
      screen.queryByRole('link', { name: 'Contexto' }),
    ).not.toBeInTheDocument()
  })
  it('informa acceso a proyecto inexistente o ajeno', async () => {
    vi.mocked(projectsService.get).mockResolvedValue(null)
    wrapper(workspace(), '/proyectos/project-b/asistente')
    await waitFor(() =>
      expect(screen.getByText('Proyecto no disponible')).toBeInTheDocument(),
    )
  })
})
