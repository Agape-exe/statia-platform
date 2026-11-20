import { useEffect, useState } from 'react'
import { chatService } from '../services/chat'
import type { DataPage, ProjectFile } from '../types/chat'
import { Alert, Loading } from './ui'

export function DatasetRows({
  projectId,
  file,
  sheet,
}: {
  projectId: string
  file: ProjectFile
  sheet?: string
}) {
  const [offset, setOffset] = useState(0)
  const [page, setPage] = useState<DataPage | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    let active = true
    const query =
      file.file_type === 'xlsx'
        ? chatService.rows(projectId, file.id, offset, sheet)
        : chatService.rows(projectId, file.id, offset)
    query
      .then((result) => {
        if (active) setPage(result)
      })
      .catch((err: unknown) => {
        if (active)
          setError(
            err instanceof Error
              ? err.message
              : 'No se pudieron consultar los registros.',
          )
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [projectId, file.id, file.file_type, offset, retry, sheet])
  function goTo(next: number) {
    setLoading(true)
    setError('')
    setOffset(next)
  }
  function reload() {
    setLoading(true)
    setError('')
    setRetry((n) => n + 1)
  }
  return (
    <section
      className="original-rows"
      aria-label={`Datos originales de ${file.original_name}`}
    >
      <p>
        Registros originales; vacíos y ausentes se conservan. Esta vista no
        comparte registros con la IA.
      </p>
      {error && (
        <Alert>
          {error} <button onClick={reload}>Reintentar consulta</button>
        </Alert>
      )}
      {loading ? (
        <Loading />
      ) : (
        !error &&
        page && (
          <>
            <p role="status">
              {page.sheet ? `Hoja: ${page.sheet}. ` : ''}
              {page.rows.length
                ? `Filas ${page.offset + 1}–${page.offset + page.rows.length} de ${page.total_rows}`
                : `No hay registros en esta página. Total: ${page.total_rows}`}
              . {page.columns.length} columnas.
            </p>
            {file.file_type === 'xlsx' && (
              <p className="muted">
                Las fórmulas se muestran sin ejecutarlas; las fechas se
                presentan en formato ISO.
              </p>
            )}
            <div
              className="table-scroll"
              role="region"
              aria-label="Tabla de registros originales"
              tabIndex={0}
            >
              <table>
                <caption>{file.original_name} · Registros originales</caption>
                <thead>
                  <tr>
                    <th scope="col">Fila</th>
                    {page.columns.map((column, i) => (
                      <th scope="col" key={i}>
                        {column}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {page.rows.map((row, index) => (
                    <tr key={page.offset + index}>
                      <th scope="row">{page.offset + index + 1}</th>
                      {row.map((value, i) => (
                        <td className="original-cell" key={i}>
                          {value === null ? (
                            <span className="muted">Ausente</span>
                          ) : value === '' ? (
                            <span className="muted">Vacío</span>
                          ) : (
                            value
                          )}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )
      )}
      <div className="chat-actions">
        <button
          className="btn secondary"
          disabled={loading || offset === 0}
          onClick={() => goTo(Math.max(0, offset - 50))}
        >
          Página anterior
        </button>
        <button
          className="btn secondary"
          disabled={loading || !!error || !page?.has_more}
          onClick={() => goTo(offset + 50)}
        >
          Página siguiente
        </button>
      </div>
    </section>
  )
}
