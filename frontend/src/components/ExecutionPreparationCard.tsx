import { useRef, useState } from 'react'
import type { ExecuteRequest, ExecutionPreparation } from '../types/analysis'
import type { Proposal } from '../types/chat'
import { Alert } from './ui'
import { ComponentStates } from './ComponentStates'

export function ExecutionPreparationCard({
  preparation,
  proposal,
  projectId,
  conversationId,
  busy,
  onAnswer,
  onReview,
  onDescriptive,
  onCancel,
  onAdvanced,
  onExecute,
}: {
  preparation: ExecutionPreparation
  proposal: Proposal
  projectId: string
  conversationId: string
  busy: boolean
  onAnswer: (questionId: string, answer: string, label: string) => void
  onReview: (questionId: string) => void
  onDescriptive: () => void
  onCancel: () => void
  onAdvanced: () => void
  onExecute: (body: ExecuteRequest) => Promise<void>
}) {
  const [error, setError] = useState('')
  const [completed, setCompleted] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const active = useRef(false)
  const pending = useRef<ExecuteRequest | null>(null)
  const question = preparation.questions[0]
  const uncertainties =
    preparation.clarifications?.filter((q) => q.status === 'unknown') || []
  const spec = preparation.specification
  function evidenceSubject(subject: string) {
    const match = subject.match(/^(\[[\s\S]*\])(?::marker:(.*)|:type)?$/)
    if (match) {
      try {
        const reference: unknown = JSON.parse(match[1])
        if (
          Array.isArray(reference) &&
          reference.length === 3 &&
          reference.every((v) => typeof v === 'string')
        ) {
          return `${preparation.files.find((f) => f.id === reference[0])?.name || 'Archivo del proyecto'} / ${reference[1]} / ${reference[2]}${match[2] ? ` · Marcador: ${match[2]}` : ''}`
        }
      } catch {
        /* Un asunto histórico no estructurado conserva su descripción. */
      }
    }
    return subject
  }
  async function execute() {
    if (
      !spec ||
      busy ||
      active.current ||
      completed ||
      !['READY', 'PARTIALLY_READY'].includes(preparation.status)
    )
      return
    active.current = true
    setSubmitting(true)
    setError('')
    const storageKey = `statia:execution:${projectId}:${conversationId}:${proposal.id}`
    const specification = { ...spec, decisions_confirmed: true }
    try {
      const stored = JSON.parse(
        sessionStorage.getItem(storageKey) || 'null',
      ) as ExecuteRequest | null
      if (
        stored?.preparation_fingerprint === preparation.fingerprint &&
        JSON.stringify(stored.specification) === JSON.stringify(specification)
      )
        pending.current = stored
    } catch {
      /* El UUID en memoria conserva el reintento si no hay almacenamiento. */
    }
    if (
      !pending.current ||
      pending.current.preparation_fingerprint !== preparation.fingerprint
    ) {
      pending.current = {
        request_id: preparation.request_id,
        specification,
        preparation_fingerprint: preparation.fingerprint,
      }
    }
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(pending.current))
    } catch {
      /* Almacenamiento opcional. */
    }
    try {
      await onExecute(pending.current)
      setCompleted(true)
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : 'No se pudo ejecutar. Puedes reintentar la misma solicitud.',
      )
    } finally {
      active.current = false
      setSubmitting(false)
    }
  }
  return (
    <article
      className="flow-card execution-preparation"
      aria-label="Preparación del análisis"
      aria-busy={busy || submitting}
    >
      <h3>
        {completed
          ? 'Análisis ejecutado'
          : preparation.status === 'COMPLETED'
            ? 'Análisis completado'
            : preparation.status === 'PARTIALLY_READY'
              ? 'Componentes disponibles para ejecución parcial'
              : preparation.status === 'READY'
                ? preparation.components?.some((c) => c.status === 'COMPLETED')
                  ? 'Componentes pendientes preparados'
                  : 'Análisis preparado'
                : preparation.status === 'UNSUPPORTED'
                  ? 'Este plan necesita revisión'
                  : preparation.status === 'BLOCKED_UNCERTAINTY'
                    ? 'Preparación detenida por incertidumbre'
                    : 'Una aclaración antes de continuar'}
      </h3>
      {preparation.status === 'PARTIALLY_READY' && (
        <p>
          Algunos procedimientos pueden ejecutarse; otros necesitan información
          adicional. La ejecución requiere tu confirmación y conservará los
          componentes pendientes.
        </p>
      )}
      <ComponentStates
        components={preparation.components || []}
        projectId={projectId}
      />
      <p>
        <strong>Objetivo:</strong> {proposal.objective}
      </p>
      {preparation.status !== 'NEEDS_CLARIFICATION' &&
        !!preparation.methods.length && (
          <p>
            <strong>Análisis:</strong> {preparation.methods.join(' · ')}
          </p>
        )}
      {preparation.status !== 'NEEDS_CLARIFICATION' && (
        <p>
          <strong>Datos:</strong>{' '}
          {preparation.files.map((f) => `${f.name} / ${f.sheet}`).join(', ')}
        </p>
      )}
      {spec && ['READY', 'PARTIALLY_READY'].includes(preparation.status) && (
        <>
          {spec.components.every(
            (c) =>
              c.method === 'descriptive' && c.descriptive_intervals === false,
          ) ? (
            <p>
              Se describirán los registros observados, sin valores p ni
              intervalos de confianza. Los procedimientos pendientes no se
              calcularán.
            </p>
          ) : (
            <p>
              <strong>Confianza:</strong>{' '}
              {Math.round(spec.confidence_level * 100)} %. Se usarán los
              registros compatibles con las decisiones de datos confirmadas.
            </p>
          )}
          {spec.multiplicity === 'holm' &&
            spec.components.some((c) => c.method !== 'descriptive') && (
              <p>
                Se controlarán conjuntamente los falsos positivos de los
                contrastes con Holm. Los intervalos serán individuales.
              </p>
            )}
          {spec.filters.map((filter, i) => (
            <p key={i}>
              <strong>Filtro:</strong> {filter.variable.column} ={' '}
              {filter.values.join(', ')}
            </p>
          ))}
          {spec.components
            .filter((c) => c.group_values.length)
            .map((c) => (
              <p key={c.source_index}>
                <strong>Grupos:</strong> {c.group_values.join(' / ')}
              </p>
            ))}
        </>
      )}
      {preparation.blockers.map((blocker, i) => (
        <Alert key={i}>{blocker}</Alert>
      ))}
      {preparation.status === 'BLOCKED_UNCERTAINTY' && (
        <div>
          <p>
            Tu respuesta «No lo sé» está guardada. Esta decisión no volverá a
            preguntarse automáticamente.
          </p>
          {uncertainties.map((q) => (
            <div key={q.id}>
              <p>{q.limitation || q.explanation}</p>
              <button
                type="button"
                className="btn secondary"
                disabled={busy || submitting}
                onClick={() => onReview(q.id)}
              >
                Revisar respuesta y cambiarla
              </button>
            </div>
          ))}
          <p>
            Puedes solicitar una nueva propuesta descriptiva con estos archivos
            y el mismo alcance. Tendrás que aceptarla antes de ejecutarla; tu
            análisis original se conserva.
          </p>
          <button
            type="button"
            className="btn primary"
            disabled={busy || submitting}
            onClick={onDescriptive}
          >
            Solicitar propuesta descriptiva alternativa
          </button>
        </div>
      )}
      {['NEEDS_CLARIFICATION', 'PARTIALLY_READY'].includes(
        preparation.status,
      ) &&
        question && (
          <fieldset disabled={busy || submitting}>
            <legend>{question.prompt}</legend>
            <p>{question.explanation}</p>
            <div className="chat-actions">
              {question.choices.map((choice) => (
                <button
                  type="button"
                  className="btn secondary"
                  key={choice.value}
                  onClick={() =>
                    onAnswer(question.id, choice.value, choice.label)
                  }
                >
                  {choice.label}
                </button>
              ))}
            </div>
            <p className="muted">
              Puedes responder aquí o escribir la opción en el chat. Si no lo
              sabes, te explicaremos cómo continuar sin inventar supuestos.
            </p>
          </fieldset>
        )}
      {preparation.status !== 'NEEDS_CLARIFICATION' &&
        !!preparation.warnings.length && (
          <p className="notice">{preparation.warnings.at(-1)}</p>
        )}
      <details>
        <summary>Ver detalles</summary>
        {preparation.reasons.map((reason, i) => (
          <p key={i}>{reason}</p>
        ))}
        <ul>
          {preparation.evidence.map((item, i) => (
            <li key={i}>
              <strong>{evidenceSubject(item.subject)}</strong> (
              {
                {
                  verified: 'verificado',
                  inferred: 'decisión automática',
                  user: 'confirmado por ti',
                }[item.origin]
              }
              ): {item.detail}
            </li>
          ))}
        </ul>
        {!!preparation.clarifications?.length && (
          <details>
            <summary>Revisar respuestas anteriores</summary>
            {preparation.clarifications
              .filter((q) => q.status !== 'pending')
              .map((q) => (
                <div key={q.id}>
                  <p>
                    {q.prompt} —{' '}
                    {q.status === 'unknown'
                      ? 'Información desconocida'
                      : q.choices.find((c) => c.value === q.answer)?.label}
                  </p>
                  <button
                    type="button"
                    className="btn secondary"
                    disabled={busy || submitting}
                    onClick={() => onReview(q.id)}
                  >
                    Cambiar respuesta
                  </button>
                </div>
              ))}
          </details>
        )}
        <ul>
          {preparation.warnings.map((warning, i) => (
            <li key={i}>{warning}</li>
          ))}
        </ul>
        <p>
          Python validará de nuevo el plan y los originales antes de calcular.
          No se modifican archivos ni se imputan datos.
        </p>
      </details>
      {error && <Alert>{error}</Alert>}
      <div className="chat-actions">
        {['READY', 'PARTIALLY_READY'].includes(preparation.status) &&
          !completed && (
            <button
              type="button"
              className="btn primary"
              disabled={busy || submitting}
              onClick={() => void execute()}
            >
              {submitting
                ? 'Calculando y guardando…'
                : preparation.status === 'PARTIALLY_READY'
                  ? 'Ejecutar componentes disponibles'
                  : spec?.partial_execution
                    ? 'Ejecutar componentes pendientes'
                    : 'Ejecutar análisis'}
            </button>
          )}
        {preparation.status === 'PARTIALLY_READY' &&
          uncertainties.length > 0 && (
            <button
              className="btn secondary"
              disabled={busy || submitting}
              onClick={() => onReview(uncertainties[0].id)}
            >
              Revisar componentes pendientes
            </button>
          )}
        <button
          type="button"
          className="btn secondary"
          disabled={busy || submitting}
          onClick={onAdvanced}
        >
          Opciones avanzadas
        </button>
        <button
          type="button"
          className="btn secondary"
          disabled={busy || submitting}
          onClick={onCancel}
        >
          {preparation.status === 'PARTIALLY_READY'
            ? 'Dejar pendiente todo el análisis'
            : preparation.status === 'BLOCKED_UNCERTAINTY'
              ? 'Dejar pendiente y volver al chat'
              : 'Volver al chat'}
        </button>
      </div>
    </article>
  )
}
