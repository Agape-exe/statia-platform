import { useEffect, useState } from 'react'
import { chatService } from '../services/chat'
import type { ProjectFile } from '../types/chat'
import { DatasetRows } from './DatasetRows'
import { DatasetCard } from './DatasetCard'
import { Alert, Loading } from './ui'

export function ProjectData({ projectId }: { projectId: string }) {
  const [files, setFiles] = useState<ProjectFile[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  const [busy, setBusy] = useState<string | null>(null)
  const [rowsId, setRowsId] = useState<string | null>(null)
  const [opened, setOpened] = useState<string | null>(null)
  const [loaded, setLoaded] = useState<Set<string>>(new Set())
  const [visualSheets, setVisualSheets] = useState<Record<string, string>>({})
  useEffect(() => {
    let active = true
    chatService
      .files(projectId)
      .then((items) => {
        if (!active) return
        setFiles([...new Map(items.map((file) => [file.id, file])).values()])
        setLoaded(new Set())
        setOpened(null)
        setRowsId(null)
        setVisualSheets({})
        setError('')
      })
      .catch((err: unknown) => {
        if (active)
          setError(
            err instanceof Error
              ? err.message
              : 'No se pudieron cargar los archivos.',
          )
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [projectId, retry])

  async function inspect(file: ProjectFile, rows = false) {
    if (rows && rowsId === file.id) {
      setRowsId(null)
      return
    }
    if (!rows && opened === file.id) {
      setOpened(null)
      return
    }
    if (loaded.has(file.id)) {
      if (rows) setRowsId(file.id)
      else setOpened(file.id)
      return
    }
    setBusy(file.id)
    setError('')
    try {
      const metadata = await chatService.profile(projectId, file.id)
      setFiles((items) =>
        items.map((item) =>
          item.id === file.id ? { ...item, metadata } : item,
        ),
      )
      setLoaded((ids) => new Set([...ids, file.id]))
      const initial =
        metadata.selected_sheet ||
        metadata.sheet_profiles?.find((entry) => entry.status === 'available')
          ?.sheet ||
        metadata.sheets[0]
      if (initial)
        setVisualSheets((sheets) => ({ ...sheets, [file.id]: initial }))
      if (rows) setRowsId(file.id)
      else setOpened(file.id)
    } catch (err) {
      setError(
        err instanceof Error ? err.message : 'No se pudo consultar el perfil.',
      )
    } finally {
      setBusy(null)
    }
  }
  function visualFile(file: ProjectFile): ProjectFile {
    const sheet = visualSheets[file.id]
    const entry = file.metadata.sheet_profiles?.find(
      (item) => item.sheet === sheet,
    )
    if (!entry) return file
    const sheetWarnings = new Set(
      file.metadata.sheet_profiles?.flatMap((item) => item.warnings),
    )
    return {
      ...file,
      metadata: {
        ...file.metadata,
        selected_sheet: sheet,
        profile: entry.profile,
        needs_sheet_selection: false,
        warnings: [
          ...(file.metadata.warnings || []).filter(
            (warning) => !sheetWarnings.has(warning),
          ),
          ...entry.warnings,
        ],
      },
    }
  }
  async function download(file: ProjectFile) {
    setBusy(file.id)
    setError('')
    try {
      await chatService.download(projectId, file)
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : 'No se pudo descargar el original.',
      )
    } finally {
      setBusy(null)
    }
  }
  if (loading) return <Loading />
  return (
    <section aria-label="Archivos del proyecto" className="project-data">
      <p>
        Archivos de todas las conversaciones de este proyecto. Los originales se
        conservan privados e intactos.
      </p>
      {error && <Alert>{error}</Alert>}
      <button
        className="btn secondary"
        disabled={!!busy}
        onClick={() => {
          setLoading(true)
          setRetry((n) => n + 1)
        }}
      >
        Actualizar archivos
      </button>
      {!files.length && !error && (
        <p>
          Aún no hay archivos. Adjunta datasets o instrumentos PDF desde el
          asistente.
        </p>
      )}
      {files.map((file) => (
        <article className="flow-card" key={file.id}>
          <h2>{file.original_name}</h2>
          <p>
            {file.file_role === 'dataset' ? 'Dataset' : 'Instrumento'} ·{' '}
            {file.file_type.toUpperCase()} ·{' '}
            {(file.file_size / 1024).toFixed(1)} KB
          </p>
          <div className="chat-actions">
            <button
              className="btn secondary"
              disabled={!!busy}
              aria-expanded={opened === file.id}
              onClick={() => void inspect(file)}
            >
              {busy === file.id
                ? 'Cargando…'
                : opened === file.id
                  ? 'Ocultar metadatos y perfil'
                  : 'Consultar metadatos y perfil'}
            </button>
            {file.file_role === 'dataset' && (
              <button
                className="btn secondary"
                disabled={!!busy}
                aria-expanded={rowsId === file.id}
                onClick={() =>
                  file.file_type === 'xlsx'
                    ? void inspect(file, true)
                    : setRowsId((id) => (id === file.id ? null : file.id))
                }
              >
                {rowsId === file.id ? 'Ocultar datos' : 'Ver datos'}
              </button>
            )}
            {opened !== file.id && (
              <button
                className="btn secondary"
                disabled={!!busy}
                onClick={() => void download(file)}
              >
                Descargar original
              </button>
            )}
          </div>
          {file.file_type === 'xlsx' && loaded.has(file.id) && (
            <label>
              Hoja visible de {file.original_name}
              <select
                value={visualSheets[file.id] || ''}
                onChange={(event) =>
                  setVisualSheets((sheets) => ({
                    ...sheets,
                    [file.id]: event.target.value,
                  }))
                }
              >
                {file.metadata.sheets.map((sheet) => (
                  <option key={sheet}>{sheet}</option>
                ))}
              </select>
              <span className="muted">
                Esta selección solo cambia la vista de Datos; conserva las hojas
                de conversaciones y planes.
              </span>
            </label>
          )}
          {rowsId === file.id && (
            <DatasetRows
              key={`${file.id}:${visualSheets[file.id] || ''}`}
              projectId={projectId}
              file={visualFile(file)}
              sheet={visualSheets[file.id]}
            />
          )}
          {opened === file.id && (
            <DatasetCard
              file={visualFile(file)}
              busy={!!busy}
              expanded
              onDownload={() => void download(file)}
            />
          )}
        </article>
      ))}
    </section>
  )
}
