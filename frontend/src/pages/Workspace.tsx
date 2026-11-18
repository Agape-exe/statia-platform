import { lazy, Suspense, useEffect, useState } from 'react'
import {
  Link,
  Navigate,
  NavLink,
  useLocation,
  useParams,
} from 'react-router-dom'
import {
  ArrowLeft,
  BookOpen,
  Database,
  FlaskConical,
  Menu,
  MessageSquare,
  Sparkles,
} from 'lucide-react'
import { AppHeader } from '../layouts/AppHeader'
import { useAuth } from '../hooks/auth-context'
import { projectsService } from '../services/projects'
import { errorMessage } from '../lib/errors'
import type { Project } from '../types/project'
import { typeLabel } from '../types/project'
import { Alert, Loading } from '../components/ui'
const StatisticalChat = lazy(() =>
  import('../components/StatisticalChat').then((module) => ({
    default: module.StatisticalChat,
  })),
)

const AnalysisResults = lazy(() =>
  import('../components/AnalysisResults').then((module) => ({
    default: module.AnalysisResults,
  })),
)
const ThesisContext = lazy(() =>
  import('../components/ThesisContext').then((module) => ({
    default: module.ThesisContext,
  })),
)
const ProjectData = lazy(() =>
  import('../components/ProjectData').then((module) => ({
    default: module.ProjectData,
  })),
)
const modules = [
  // Los módulos de chat y resultados se cargan bajo demanda.
  {
    path: 'asistente',
    title: 'Asistente Estadístico',
    icon: MessageSquare,
    text: 'Un espacio para hacer preguntas y orientar tu análisis.',
    detail:
      'Comprende tus datasets y prepara planes estadísticos en una conversación persistente.',
  },
  {
    path: 'contexto',
    title: 'Contexto',
    icon: BookOpen,
    text: 'La metodología que da sentido a tus datos.',
    detail:
      'Registra, importa y confirma la información metodológica que orientará al asistente.',
  },
  {
    path: 'datos',
    title: 'Datos',
    icon: Database,
    text: 'El punto de partida de cada descubrimiento.',
    detail:
      'Carga datasets e instrumentos desde el Asistente Estadístico. Allí puedes revisar sus perfiles y reutilizarlos entre conversaciones del proyecto.',
  },
  {
    path: 'resultados',
    title: 'Resultados',
    icon: FlaskConical,
    text: 'Tus hallazgos, organizados en un solo lugar.',
    detail:
      'Aquí aparecerán los análisis y recursos exportables vinculados a tus ejecuciones. Estarán disponibles al integrar el motor estadístico.',
  },
]
export function Workspace() {
  const { projectId = '', module = 'asistente' } = useParams()
  const { session } = useAuth()
  const userId = session!.user.id
  const location = useLocation()
  const [state, setState] = useState<{
    id: string
    project: Project | null
    error: string | null
    loading: boolean
  }>({ id: '', project: null, error: null, loading: true })
  const [retry, setRetry] = useState(0)
  const [mobileOpen, setMobileOpen] = useState(false)
  useEffect(() => {
    let active = true
    projectsService
      .get(projectId, userId)
      .then((project) => {
        if (active)
          setState({ id: projectId, project, loading: false, error: null })
      })
      .catch((error) => {
        if (active)
          setState({
            id: projectId,
            project: null,
            loading: false,
            error: errorMessage(error),
          })
      })
    return () => {
      active = false
    }
  }, [projectId, userId, retry])
  if (state.loading || state.id !== projectId) return <Loading />
  if (state.error)
    return (
      <>
        <AppHeader />
        <main className="dashboard">
          <Alert>
            {state.error}{' '}
            <button onClick={() => setRetry((n) => n + 1)}>Reintentar</button>
          </Alert>
          <Link to="/dashboard">Volver al dashboard</Link>
        </main>
      </>
    )
  const project = state.project
  if (!project)
    return (
      <>
        <AppHeader />
        <main className="dashboard">
          <h1>Proyecto no disponible</h1>
          <p>No existe o no tienes acceso a este proyecto.</p>
          <Link to="/dashboard">Volver al dashboard</Link>
        </main>
      </>
    )
  const current = modules.find((item) => item.path === module)
  if (!current || (module === 'contexto' && project.project_type !== 'thesis'))
    return <Navigate to={`/proyectos/${project.id}/asistente`} replace />
  const Icon = current.icon
  return (
    <div
      className={
        module === 'asistente' ? 'workspace-shell assistant-shell' : undefined
      }
    >
      <AppHeader />
      <div className="workspace">
        <aside className="sidebar">
          <div className="sidebar-project">
            <span className={`badge ${project.project_type}`}>
              {typeLabel(project.project_type)}
            </span>
            <h2>{project.name}</h2>
          </div>
          <button
            className="btn secondary mobile-toggle"
            aria-expanded={mobileOpen}
            aria-controls="module-nav"
            onClick={() => setMobileOpen(!mobileOpen)}
          >
            <Menu size={18} />
            Módulos del proyecto
          </button>
          <nav
            id="module-nav"
            className={mobileOpen ? 'open' : ''}
            aria-label="Módulos del proyecto"
          >
            {modules
              .filter(
                (item) =>
                  item.path !== 'contexto' || project.project_type === 'thesis',
              )
              .map((item) => (
                <NavLink
                  key={item.path}
                  to={`/proyectos/${project.id}/${item.path}`}
                  onClick={() => setMobileOpen(false)}
                >
                  <item.icon size={19} />
                  {item.title}
                </NavLink>
              ))}
          </nav>
          <Link className="back-link" to="/dashboard">
            <ArrowLeft size={17} />
            Todos los proyectos
          </Link>
          <div className="sidebar-note">
            <Sparkles size={18} />
            <p>Las buenas preguntas abren nuevas posibilidades.</p>
          </div>
        </aside>
        <main className="workspace-main">
          {module === 'asistente' && (
            <h1 className="sr-only">Asistente Estadístico</h1>
          )}
          {module !== 'asistente' && (
            <div className="breadcrumb">
              {project.name} <span>/</span> {current.title}
            </div>
          )}
          {location.state?.created && (
            <div className="notice" role="status">
              Proyecto creado correctamente.
            </div>
          )}
          {module !== 'asistente' && (
            <header className="module-heading">
              <span className="eyebrow">ESPACIO DE TRABAJO</span>
              <h1>{current.title}</h1>
              <p className="muted">{current.text}</p>
            </header>
          )}
          {module === 'asistente' ? (
            <Suspense fallback={<Loading />}>
              <StatisticalChat key={project.id} project={project} />
            </Suspense>
          ) : module === 'contexto' ? (
            <Suspense fallback={<Loading />}>
              <ThesisContext key={project.id} projectId={project.id} />
            </Suspense>
          ) : module === 'datos' ? (
            <Suspense fallback={<Loading />}>
              <ProjectData key={project.id} projectId={project.id} />
            </Suspense>
          ) : module === 'resultados' ? (
            <Suspense fallback={<Loading />}>
              <AnalysisResults key={project.id} projectId={project.id} />
            </Suspense>
          ) : (
            <section className="module-placeholder">
              <span className="empty-icon">
                <Icon size={34} />
              </span>
              <span className="badge neutral">
                {module === 'datos'
                  ? 'Disponible en el asistente'
                  : 'Próximamente'}
              </span>
              <h2>{current.text}</h2>
              <p className="muted">{current.detail}</p>
              {module === 'datos' && (
                <Link
                  className="btn primary"
                  to={`/proyectos/${project.id}/asistente`}
                >
                  Abrir asistente y archivos
                </Link>
              )}
              <div className="module-status">
                <span />
                {module === 'datos'
                  ? 'Archivos privados de tu proyecto'
                  : 'Módulo preparado para una próxima sesión'}
              </div>
            </section>
          )}
        </main>
      </div>
    </div>
  )
}
