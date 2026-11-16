import { useState } from 'react'
import type {
  AnalysisRun,
  ComponentPreparation,
  ExecutionPreparation,
  PreparationClarification,
} from '../types/analysis'
import { ComponentStates } from './ComponentStates'

export function PendingComponentsReview({
  run,
  preparation,
  busy = false,
  onPrepare,
  onAnswer,
}: {
  run: AnalysisRun
  preparation?: ExecutionPreparation | null
  busy?: boolean
  onPrepare?: (proposalId: string) => void
  onAnswer?: (
    proposalId: string,
    questionId: string,
    answer: string,
    label: string,
  ) => void
}) {
  const [answers, setAnswers] = useState<Record<string, string>>({})
  const recorded = run.result?.component_states || []
  const states: ComponentPreparation[] = recorded.length
    ? recorded
    : (run.result?.specification.components || [])
        .filter(
          (c) =>
            !run.result?.components.some(
              (r) =>
                r.source_index === c.source_index && r.status === 'completed',
            ),
        )
        .map((c) => ({
          id: `component:${c.source_index}`,
          source_index: c.source_index,
          method: c.method,
          variables:
            run.result?.components.find(
              (r) => r.source_index === c.source_index,
            )?.variables || [],
          status: 'NEEDS_CLARIFICATION',
          fingerprint: '',
          question_ids: [],
          blockers: [
            'Esta ejecución histórica no registra el estado metodológico del componente. Revisa sus decisiones antes de preparar.',
          ],
          warnings: [],
          completed_run_id: null,
          depends_on: [],
        }))
  const pending = states.filter((c) => c.status !== 'COMPLETED')
  const questions = new Map<string, PreparationClarification>()
  for (const component of pending)
    for (const q of component.assumptions || []) questions.set(q.id, q)
  for (const q of preparation?.clarifications || []) questions.set(q.id, q)
  return (
    <section
      className="flow-card"
      aria-label="Revisión de componentes pendientes"
    >
      <h4>Componentes pendientes — {pending.length}</h4>
      <p>
        Estado registrado en esta ejecución. Consultar estos detalles conserva
        tus resultados y respuestas.
      </p>
      <ComponentStates components={pending} projectId={run.project_id} />
      {!pending.length && (
        <p>No hay componentes pendientes registrados en esta ejecución.</p>
      )}
      {!!questions.size && (
        <details open>
          <summary>Revisar respuestas anteriores y aclaraciones</summary>
          {[...questions.values()].map((q) => (
            <div key={q.id} className="clarification-review">
              <p>
                <strong>{q.prompt}</strong>
              </p>
              <p>
                {q.status === 'unknown'
                  ? 'Respuesta: No lo sé'
                  : q.status === 'answered'
                    ? `Respuesta: ${q.choices.find((c) => c.value === q.answer)?.label || 'Registrada'}`
                    : 'Respuesta pendiente'}
              </p>
              <p className="muted">
                {q.status === 'unknown'
                  ? q.limitation || q.explanation
                  : q.explanation}
              </p>
              {onAnswer &&
                preparation?.clarifications?.some(
                  (current) => current.id === q.id,
                ) && (
                  <>
                    <label>
                      Nueva respuesta
                      <select
                        aria-label={`Nueva respuesta: ${q.prompt}`}
                        disabled={busy}
                        value={answers[q.id] ?? q.answer ?? ''}
                        onChange={(e) =>
                          setAnswers((current) => ({
                            ...current,
                            [q.id]: e.target.value,
                          }))
                        }
                      >
                        <option value="">Selecciona una respuesta</option>
                        {q.choices.map((c) => (
                          <option key={c.value} value={c.value}>
                            {c.label}
                          </option>
                        ))}
                      </select>
                    </label>
                    <button
                      className="btn secondary"
                      disabled={
                        busy || !answers[q.id] || answers[q.id] === q.answer
                      }
                      onClick={() =>
                        onAnswer(
                          run.proposal_id,
                          q.id,
                          answers[q.id],
                          q.choices.find((c) => c.value === answers[q.id])
                            ?.label || '',
                        )
                      }
                    >
                      Guardar respuesta y preparar pendientes
                    </button>
                  </>
                )}
            </div>
          ))}
        </details>
      )}
      {!questions.size && (
        <p>
          El registro no conserva aclaraciones relacionadas. Puedes volver a
          preparar explícitamente para obtener las preguntas vigentes.
        </p>
      )}
      {onPrepare && (
        <button
          className="btn secondary"
          disabled={busy}
          onClick={() => onPrepare(run.proposal_id)}
        >
          Volver a preparar componentes pendientes
        </button>
      )}
    </section>
  )
}
