import { useState, type FormEvent } from 'react'
import { GraduationCap, Database } from 'lucide-react'
import type { Project, ProjectInput, ProjectType } from '../types/project'
import { validateProject } from '../lib/validation'
import { Alert } from './ui'

export function ProjectForm({
  project,
  onSave,
  onCancel,
  busy,
  error,
}: {
  project?: Project
  onSave: (input: ProjectInput) => Promise<void>
  onCancel: () => void
  busy: boolean
  error: string | null
}) {
  const [name, setName] = useState(project?.name ?? '')
  const [description, setDescription] = useState(project?.description ?? '')
  const [type, setType] = useState<ProjectType | ''>(
    project?.project_type ?? '',
  )
  const [validation, setValidation] = useState<string | null>(null)
  function submit(e: FormEvent) {
    e.preventDefault()
    const input = { name, description, project_type: type as ProjectType }
    const invalid = validateProject(input)
    setValidation(invalid)
    if (!invalid) void onSave(input)
  }
  return (
    <form onSubmit={submit} noValidate className="project-form">
      {(validation || error) && <Alert>{validation || error}</Alert>}
      <fieldset disabled={busy}>
        <label>
          Nombre del proyecto
          <input
            autoFocus
            required
            maxLength={120}
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Ej. Factores del rendimiento académico"
          />
        </label>
        <fieldset className="type-picker">
          <legend>
            Uso del proyecto {project && <small>(no se puede modificar)</small>}
          </legend>
          {(['thesis', 'general'] as const).map((value) => (
            <label
              className={`type-option ${type === value ? 'selected' : ''}`}
              key={value}
            >
              <input
                type="radio"
                name="project-type"
                value={value}
                checked={type === value}
                disabled={!!project}
                onChange={() => setType(value)}
              />
              {value === 'thesis' ? (
                <GraduationCap size={23} />
              ) : (
                <Database size={23} />
              )}
              <span>
                {value === 'thesis'
                  ? 'Análisis para tesis'
                  : 'Datasets generales'}
                <small>
                  {value === 'thesis'
                    ? 'Investigación con contexto metodológico'
                    : 'Exploración de datos independiente'}
                </small>
              </span>
            </label>
          ))}
        </fieldset>
        <label>
          Descripción <span className="muted">(opcional)</span>
          <textarea
            rows={4}
            maxLength={2000}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="¿De qué trata tu proyecto?"
          />
        </label>
        <div className="form-actions">
          <button type="button" className="btn secondary" onClick={onCancel}>
            Cancelar
          </button>
          <button className="btn primary" disabled={busy}>
            {busy
              ? 'Guardando…'
              : project
                ? 'Guardar cambios'
                : 'Crear proyecto'}
          </button>
        </div>
      </fieldset>
    </form>
  )
}
