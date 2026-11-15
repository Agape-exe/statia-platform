import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import {
  ArrowUpRight,
  Database,
  FolderOpen,
  GraduationCap,
  Pencil,
  Plus,
  Trash2,
} from 'lucide-react'
import { useAuth } from '../hooks/auth-context'
import { projectsService } from '../services/projects'
import { errorMessage } from '../lib/errors'
import type { Project, ProjectInput } from '../types/project'
import { typeLabel } from '../types/project'
import { AppHeader } from '../layouts/AppHeader'
import { Alert, Loading } from '../components/ui'
import { Modal } from '../components/Modal'
import { ProjectForm } from '../components/ProjectForm'

export function Dashboard() {
  const { session } = useAuth()
  const userId = session!.user.id
  const navigate = useNavigate()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [modal, setModal] = useState<
    { mode: 'create' } | { mode: 'edit' | 'delete'; project: Project } | null
  >(null)
  const [message, setMessage] = useState('')
  const load = useCallback(
    (signal: { active: boolean }) =>
      projectsService
        .list(userId)
        .then((data) => {
          if (signal.active) setProjects(data)
        })
        .catch((error) => {
          if (signal.active) setError(errorMessage(error))
        })
        .finally(() => {
          if (signal.active) setLoading(false)
        }),
    [userId],
  )
  useEffect(() => {
    const signal = { active: true }
    void load(signal)
    return () => {
      signal.active = false
    }
  }, [load])
  function open(next: typeof modal) {
    setActionError(null)
    setModal(next)
  }
  function retryLoad() {
    setLoading(true)
    setError(null)
    void load({ active: true })
  }
  async function save(input: ProjectInput) {
    if (!modal || modal.mode === 'delete') return
    setBusy(true)
    setActionError(null)
    try {
      if (modal.mode === 'create') {
        const project = await projectsService.create(input, userId)
        navigate(`/proyectos/${project.id}/asistente`, {
          state: { created: true },
        })
      } else {
        const updated = await projectsService.update(
          modal.project.id,
          input,
          userId,
        )
        setProjects((previous) => [
          updated,
          ...previous.filter((p) => p.id !== updated.id),
        ])
        setModal(null)
        setMessage('Proyecto actualizado correctamente.')
      }
    } catch (error) {
      setActionError(errorMessage(error))
    } finally {
      setBusy(false)
    }
  }
  async function remove() {
    if (!modal || modal.mode !== 'delete') return
    setBusy(true)
    setActionError(null)
    try {
      await projectsService.remove(modal.project.id, userId)
      setProjects((previous) =>
        previous.filter((p) => p.id !== modal.project.id),
      )
      setModal(null)
      setMessage('Proyecto eliminado correctamente.')
    } catch (error) {
      setActionError(errorMessage(error))
    } finally {
      setBusy(false)
    }
  }
  return (
    <>
      <AppHeader />
      <main className="dashboard">
        <div className="page-intro">
          <div>
            <span className="eyebrow">TU ESPACIO DE INVESTIGACIÓN</span>
            <h1>Cada proyecto, un descubrimiento.</h1>
            <p className="muted">
              Organiza tus ideas y construye el camino hacia tus resultados.
            </p>
          </div>
          <button
            className="btn primary"
            onClick={() => open({ mode: 'create' })}
          >
            <Plus size={19} />
            Nuevo proyecto
          </button>
        </div>
        <div className="section-heading">
          <h2>
            Mis proyectos <span className="count">{projects.length}</span>
          </h2>
          <span className="muted">Tu investigación empieza aquí</span>
        </div>
        {message && (
          <div className="notice" role="status">
            {message}
          </div>
        )}
        {loading ? (
          <Loading />
        ) : error ? (
          <Alert>
            {error} <button onClick={retryLoad}>Reintentar</button>
          </Alert>
        ) : projects.length === 0 ? (
          <div className="empty-state">
            <span className="empty-icon">
              <FolderOpen size={34} />
            </span>
            <h2>Un nuevo espacio para tus ideas</h2>
            <p className="muted">
              Crea tu primer proyecto de tesis o de análisis de datos.
              <br />
              Todo tu trabajo estará organizado en un solo lugar.
            </p>
            <button
              className="btn primary"
              onClick={() => open({ mode: 'create' })}
            >
              <Plus size={18} />
              Crear mi primer proyecto
            </button>
          </div>
        ) : (
          <div className="project-grid">
            {projects.map((project) => (
              <article className="project-card" key={project.id}>
                <div className="card-top">
                  <span className={`project-symbol ${project.project_type}`}>
                    {project.project_type === 'thesis' ? (
                      <GraduationCap />
                    ) : (
                      <Database />
                    )}
                  </span>
                  <span className={`badge ${project.project_type}`}>
                    {typeLabel(project.project_type)}
                  </span>
                </div>
                <Link
                  className="project-link"
                  to={`/proyectos/${project.id}/asistente`}
                >
                  <h3>{project.name}</h3>
                  <p className="muted">
                    {project.description ||
                      'Sin descripción. Tu próximo descubrimiento comienza aquí.'}
                  </p>
                </Link>
                <div className="card-bottom">
                  <span className="muted">
                    Actualizado el{' '}
                    {new Intl.DateTimeFormat('es-PE', {
                      dateStyle: 'medium',
                    }).format(new Date(project.updated_at))}
                  </span>
                  <div>
                    <button
                      className="icon-btn"
                      aria-label={`Editar ${project.name}`}
                      onClick={() => open({ mode: 'edit', project })}
                    >
                      <Pencil size={16} />
                    </button>
                    <button
                      className="icon-btn danger-text"
                      aria-label={`Eliminar ${project.name}`}
                      onClick={() => open({ mode: 'delete', project })}
                    >
                      <Trash2 size={16} />
                    </button>
                    <Link
                      className="icon-btn"
                      aria-label={`Abrir ${project.name}`}
                      to={`/proyectos/${project.id}/asistente`}
                    >
                      <ArrowUpRight size={19} />
                    </Link>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
        <footer className="dashboard-footer">
          STATIA PLATFORM <span>De las preguntas a las perspectivas.</span>
        </footer>
      </main>
      {modal && (
        <Modal
          title={
            modal.mode === 'create'
              ? 'Nuevo proyecto'
              : modal.mode === 'edit'
                ? 'Editar proyecto'
                : 'Eliminar proyecto'
          }
          busy={busy}
          onClose={() => setModal(null)}
        >
          {modal.mode === 'delete' ? (
            <>
              <p>
                ¿Eliminar <strong>{modal.project.name}</strong>? Esta acción es
                permanente.
              </p>
              {actionError && <Alert>{actionError}</Alert>}
              <div className="form-actions">
                <button
                  className="btn secondary"
                  disabled={busy}
                  onClick={() => setModal(null)}
                >
                  Cancelar
                </button>
                <button
                  className="btn danger"
                  disabled={busy}
                  onClick={() => void remove()}
                >
                  {busy ? 'Eliminando…' : 'Eliminar proyecto'}
                </button>
              </div>
            </>
          ) : (
            <ProjectForm
              project={modal.mode === 'edit' ? modal.project : undefined}
              onSave={save}
              onCancel={() => setModal(null)}
              busy={busy}
              error={actionError}
            />
          )}
        </Modal>
      )}
    </>
  )
}
