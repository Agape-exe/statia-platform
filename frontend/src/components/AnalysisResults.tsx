import { useEffect, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { analysisService } from '../services/analysis'
import { chatService } from '../services/chat'
import type { AnalysisRun } from '../types/analysis'
import { runStatus } from '../types/analysis'
import type { Conversation } from '../types/chat'
import { AnalysisResultCard } from './AnalysisResultCard'
import { Alert, Loading } from './ui'

export function AnalysisResults({ projectId }: { projectId: string }) {
  const [params, setParams] = useSearchParams()
  const [runs, setRuns] = useState<AnalysisRun[]>([])
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [more, setMore] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const [paging, setPaging] = useState(false)
  const selected = params.get('run')
  useEffect(() => {
    let active = true
    Promise.all([analysisService.list(projectId), chatService.list(projectId)])
      .then(([list, chats]) => {
        if (active) {
          setRuns(list)
          setConversations(chats)
          setMore(list.length === 50)
          setError('')
        }
      })
      .catch((caught) => {
        if (active)
          setError(
            caught instanceof Error
              ? caught.message
              : 'No se pudieron cargar los resultados.',
          )
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [projectId, attempt])

  async function next() {
    if (paging) return
    setPaging(true)
    try {
      const page = await analysisService.list(projectId, undefined, runs.length)
      setRuns((current) => [
        ...current,
        ...page.filter(
          (r) => !current.some((existing) => existing.id === r.id),
        ),
      ])
      setMore(page.length === 50)
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : 'No se pudo cargar la página.',
      )
    } finally {
      setPaging(false)
    }
  }

  if (loading) return <Loading />
  const groups = new Map<string, AnalysisRun[]>()
  for (const item of runs)
    groups.set(item.conversation_id, [
      ...(groups.get(item.conversation_id) || []),
      item,
    ])
  return (
    <section className="results-module" aria-label="Resultados del proyecto">
      {error && <Alert>{error}</Alert>}
      <button
        className="btn secondary"
        onClick={() => setAttempt((n) => n + 1)}
      >
        Actualizar resultados
      </button>
      {!runs.length && !error && (
        <div className="module-placeholder">
          <h2>Aún no hay ejecuciones</h2>
          <p>
            Acepta una propuesta y revisa sus decisiones con «Ejecutar análisis»
            en el asistente.
          </p>
          <Link
            className="btn primary"
            to={`/proyectos/${projectId}/asistente`}
          >
            Abrir asistente
          </Link>
        </div>
      )}
      {selected && (
        <div>
          <button className="btn secondary" onClick={() => setParams({})}>
            Cerrar detalle
          </button>
          <AnalysisResultCard
            key={selected}
            projectId={projectId}
            runId={selected}
            expanded
          />
        </div>
      )}
      {Array.from(groups).map(([id, items]) => (
        <section key={id} className="results-conversation">
          <h2>
            {conversations.find((c) => c.id === id)?.title || 'Conversación'}
          </h2>
          {items.map((item) => (
            <article className="result-row" key={item.id}>
              <div>
                <h3>{item.title}</h3>
                <p>{item.methods.join(' · ')}</p>
                <p className="muted">
                  {new Date(item.created_at).toLocaleString('es-PE')} ·{' '}
                  {runStatus[item.status]} · {item.artifact_count} recursos
                </p>
                {item.error && <p>{item.error}</p>}
              </div>
              <button
                className="btn secondary"
                onClick={() => setParams({ run: item.id })}
              >
                Consultar y descargar
              </button>
            </article>
          ))}
        </section>
      ))}
      {more && (
        <button
          className="btn secondary"
          disabled={paging}
          onClick={() => void next()}
        >
          {paging ? 'Cargando…' : 'Cargar más resultados'}
        </button>
      )}
    </section>
  )
}
