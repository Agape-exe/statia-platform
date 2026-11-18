import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { analysisService } from '../services/analysis'
import {
  runStatus,
  type AnalysisArtifact,
  type AnalysisRun,
  type ResultTable,
  type ExecutionPreparation,
} from '../types/analysis'
import { Alert, Loading } from './ui'
import { formatResult } from '../lib/analysis-format'
import { ComponentStates } from './ComponentStates'
import { PendingComponentsReview } from './PendingComponentsReview'

function StatisticalTable({ table }: { table: ResultTable }) {
  return (
    <div
      className="statistical-table"
      tabIndex={0}
      role="region"
      aria-label={table.title}
    >
      <table>
        <caption>{table.title}</caption>
        <thead>
          <tr>
            {table.columns.map((c) => (
              <th scope="col" key={c}>
                {c}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row, index) => (
            <tr key={index}>
              {table.columns.map((c) => (
                <td key={c}>
                  {formatResult(row[c], row.Medida === 'p' ? 'p' : c)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function PrivateChart({
  projectId,
  runId,
  artifact,
}: {
  projectId: string
  runId: string
  artifact: AnalysisArtifact
}) {
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  useEffect(() => {
    let active = true
    let objectUrl = ''
    analysisService
      .artifact(projectId, runId, artifact.id)
      .then((blob) => {
        if (!active) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
      })
      .catch((caught) => {
        if (active)
          setError(
            caught instanceof Error ? caught.message : 'Gráfico no disponible.',
          )
      })
    return () => {
      active = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [projectId, runId, artifact.id])
  return (
    <figure className="statistical-chart">
      {error ? (
        <Alert>{error}</Alert>
      ) : url ? (
        <img
          src={url}
          alt={`Gráfico estadístico: ${artifact.name}`}
          loading="lazy"
        />
      ) : (
        <p role="status">Cargando gráfico privado…</p>
      )}
      <figcaption>{artifact.name}</figcaption>
    </figure>
  )
}

const assumptionStatus = {
  evaluated: 'Evaluado',
  pending: 'Pendiente',
  violated: 'Incumplido',
  not_applicable: 'No aplicable',
}

export function AnalysisResultCard({
  projectId,
  runId,
  initialRun,
  expanded = false,
  onPrepare,
  onAnswer,
  preparation,
  busy = false,
  onLoaded,
}: {
  projectId: string
  runId: string
  initialRun?: AnalysisRun
  expanded?: boolean
  onPrepare?: (proposalId: string) => void
  onAnswer?: (
    proposalId: string,
    questionId: string,
    answer: string,
    label: string,
  ) => void
  preparation?: ExecutionPreparation | null
  busy?: boolean
  onLoaded?: (run: AnalysisRun) => void
}) {
  const [run, setRun] = useState<AnalysisRun | null>(initialRun || null)
  const [loading, setLoading] = useState(!initialRun)
  const [open, setOpen] = useState(expanded)
  const [pendingOpen, setPendingOpen] = useState(false)
  const [error, setError] = useState('')
  const [downloading, setDownloading] = useState(false)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    let active = true
    if (!initialRun || attempt) {
      analysisService
        .get(projectId, runId)
        .then((value) => {
          if (active) {
            setRun(value)
            setError('')
          }
        })
        .catch((caught) => {
          if (active)
            setError(
              caught instanceof Error
                ? caught.message
                : 'No se pudo consultar el resultado.',
            )
        })
        .finally(() => {
          if (active) setLoading(false)
        })
    }
    return () => {
      active = false
    }
  }, [projectId, runId, initialRun, attempt])
  useEffect(() => {
    if (!loading && run) onLoaded?.(run)
  }, [loading, run, onLoaded])

  async function download(artifact?: AnalysisArtifact) {
    if (downloading) return
    setDownloading(true)
    setError('')
    try {
      if (artifact)
        await analysisService.downloadArtifact(projectId, runId, artifact)
      else await analysisService.downloadZip(projectId, runId)
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : 'No se pudo descargar el recurso.',
      )
    } finally {
      setDownloading(false)
    }
  }

  if (loading) return <Loading />
  return (
    <article
      className="analysis-card"
      aria-label={`Resultado: ${run?.title || 'No disponible'}`}
    >
      {error && (
        <Alert>
          {error}{' '}
          <button onClick={() => setAttempt((n) => n + 1)}>
            Volver a consultar
          </button>
        </Alert>
      )}
      {run && (
        <>
          <div className="analysis-card-heading">
            <span className="eyebrow">RESULTADO ESTADÍSTICO</span>
            <span className={`badge analysis-${run.status}`}>
              {runStatus[run.status]}
            </span>
          </div>
          <h3>{run.title}</h3>
          <p role="status">
            {run.status === 'partial'
              ? 'Análisis ejecutado parcialmente'
              : run.status === 'completed'
                ? 'Análisis completado'
                : runStatus[run.status]}
          </p>
          {!pendingOpen && (
            <ComponentStates
              components={run.result?.component_states || []}
              projectId={projectId}
            />
          )}
          <p className="muted">
            {new Date(run.created_at).toLocaleString('es-PE')} ·{' '}
            {run.artifact_count} recursos
          </p>
          {run.result && (
            <p>{run.result.components.map((c) => c.title).join(' · ')}</p>
          )}
          {run.error && <Alert>{run.error}</Alert>}
          {run.result && <p>{run.result.summary}</p>}
          {run.status === 'running' && (
            <p role="status">
              Esta ejecución está en curso. Puedes consultar su estado; si se
              interrumpe, se informará el fallo al vencer su concesión.
            </p>
          )}
          <div className="chat-actions">
            {run.status === 'partial' && (
              <button
                className="btn secondary"
                aria-expanded={pendingOpen}
                onClick={() => setPendingOpen((value) => !value)}
              >
                Revisar componentes pendientes
              </button>
            )}
            <button
              className="btn secondary"
              onClick={() => setOpen((value) => !value)}
              aria-expanded={open}
            >
              {open ? 'Ocultar detalle' : 'Ver tablas y gráficos'}
            </button>
            <Link
              className="btn secondary"
              to={`/proyectos/${projectId}/resultados?run=${runId}`}
            >
              Abrir en Resultados
            </Link>
            {!!run.result && (
              <button
                className="btn primary"
                disabled={downloading}
                onClick={() => void download()}
              >
                {downloading ? 'Descargando…' : 'Descargar ZIP'}
              </button>
            )}
            {run.status === 'running' && (
              <button
                className="btn secondary"
                onClick={() => setAttempt((n) => n + 1)}
              >
                Consultar estado
              </button>
            )}
          </div>
          {pendingOpen && (
            <PendingComponentsReview
              run={run}
              preparation={preparation}
              busy={busy}
              onPrepare={onPrepare}
              onAnswer={onAnswer}
            />
          )}
          {open && run.result && (
            <div className="analysis-detail">
              {run.result.components.map((component, index) => (
                <section key={index} className="analysis-component">
                  <h4>
                    {component.title} · {runStatus[component.status]}
                  </h4>
                  {!!Object.keys(component.scope).length && (
                    <p>
                      Ámbito:{' '}
                      {Object.entries(component.scope)
                        .map(([k, v]) => `${k}: ${v}`)
                        .join(' · ')}
                    </p>
                  )}
                  {component.error && <Alert>{component.error}</Alert>}
                  <p>{component.interpretation}</p>
                  <details>
                    <summary>Muestra y exclusiones</summary>
                    <dl>
                      {Object.entries(component.sample).map(([k, v]) => (
                        <div key={k}>
                          <dt>
                            {(
                              {
                                initial: 'Observaciones iniciales',
                                after_filters: 'Después de filtros',
                                excluded_filters:
                                  'Excluidas por filtros/estrato',
                                used: 'N utilizado',
                                excluded_missing: 'Excluidas por ausencias',
                                excluded_unselected_groups: 'Otros grupos',
                                groups: 'N por grupo',
                                sheet: 'Hoja',
                                file_id: 'Archivo (referencia)',
                              } as Record<string, string>
                            )[k] || k}
                          </dt>
                          <dd>{formatResult(v)}</dd>
                        </div>
                      ))}
                    </dl>
                  </details>
                  {component.tables.map((item, i) => (
                    <StatisticalTable key={i} table={item} />
                  ))}
                  <details>
                    <summary>Supuestos y advertencias</summary>
                    <ul>
                      {component.assumptions.map((a, i) => (
                        <li
                          key={i}
                          className={
                            a.origin === 'user'
                              ? 'evidence-user'
                              : `assumption-${a.status}`
                          }
                        >
                          <strong>
                            {a.name}:{' '}
                            {a.origin === 'user'
                              ? 'confirmación del investigador'
                              : a.origin === 'verified'
                                ? 'verificación automática'
                                : assumptionStatus[a.status]}
                            .
                          </strong>{' '}
                          {a.detail}
                        </li>
                      ))}
                      {component.warnings.map((warning, i) => (
                        <li key={`w${i}`}>{warning}</li>
                      ))}
                    </ul>
                  </details>
                  <div className="statistical-charts">
                    {component.charts.map((name) => {
                      const artifact = run.artifacts.find(
                        (a) => a.name === name,
                      )
                      return artifact ? (
                        <PrivateChart
                          key={artifact.id}
                          projectId={projectId}
                          runId={runId}
                          artifact={artifact}
                        />
                      ) : (
                        <p key={name}>Gráfico no disponible: {name}</p>
                      )
                    })}
                  </div>
                </section>
              ))}
              <details>
                <summary>Recursos individuales y trazabilidad</summary>
                <ul className="analysis-downloads">
                  {run.artifacts.map((artifact) => (
                    <li key={artifact.id}>
                      <button
                        disabled={downloading}
                        onClick={() => void download(artifact)}
                      >
                        {artifact.name}
                      </button>{' '}
                      <small>
                        ({Math.ceil(artifact.size_bytes / 1024)} KB)
                      </small>
                    </li>
                  ))}
                </ul>
                <p>Originales utilizados (SHA-256):</p>
                <ul>
                  {run.result.files.map((file) => (
                    <li key={file.id}>
                      {file.name} / {file.sheet}
                      <code className="file-hash">{file.sha256}</code>
                    </li>
                  ))}
                </ul>
                <p>
                  Dependencias:{' '}
                  {Object.entries(run.result.dependencies)
                    .map(([k, v]) => `${k} ${v}`)
                    .join('; ')}
                  .
                </p>
                <pre className="analysis-spec">
                  {JSON.stringify(run.result.specification, null, 2)}
                </pre>
              </details>
            </div>
          )}
        </>
      )}
    </article>
  )
}
