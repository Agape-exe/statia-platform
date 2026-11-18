import type { ProjectFile, Proposal } from '../types/chat'
import { visibleChatText } from '../lib/chat-text'

export function ProposalCard({
  proposal,
  files,
  busy,
  onDecide,
  onExecute,
  prepared = false,
}: {
  proposal: Proposal
  files: ProjectFile[]
  busy: boolean
  onDecide: (status: 'accepted' | 'rejected') => void
  onExecute?: () => void
  prepared?: boolean
}) {
  const plan = proposal.analysis_plan
  const visible = (text: string) => visibleChatText(text, files)
  const comparison = plan.comparison
  return (
    <article
      className="proposal-card"
      aria-label={`Propuesta: ${visible(proposal.title)}`}
    >
      <span className="eyebrow">
        {proposal.status === 'accepted'
          ? 'PLAN ACEPTADO'
          : proposal.status === 'rejected'
            ? 'PROPUESTA RECHAZADA'
            : 'PROPUESTA PARA CONFIRMAR'}
      </span>
      <h3>{visible(proposal.title)}</h3>
      <p>{visible(proposal.objective)}</p>
      <p>
        <strong>Procedimiento:</strong> {visible(plan.method)}
      </p>
      <ul>
        {plan.variables.map((variable, index) => (
          <li key={index}>
            {files.find((f) => f.id === variable.file_id)?.original_name ||
              'Archivo no disponible'}{' '}
            / {variable.sheet}: <strong>{variable.column}</strong>
          </li>
        ))}
      </ul>
      <p>
        <strong>Justificación:</strong> {visible(plan.justification)}
      </p>
      {(
        [
          ['Requisitos y supuestos', plan.requirements],
          ['Limitaciones', plan.limitations],
          ['Productos esperados', plan.expected_outputs],
        ] as const
      )
        .filter(([, values]) => values.some((value) => value.trim()))
        .map(([title, values]) => (
          <details key={title}>
            <summary>{title}</summary>
            <ul>
              {values
                .filter((value) => value.trim())
                .map((value, index) => (
                  <li key={index}>{visible(value)}</li>
                ))}
            </ul>
          </details>
        ))}
      {!!plan.components?.length && (
        <details>
          <summary>Procedimientos del plan integral</summary>
          <ul>
            {plan.components.map((step, index) => (
              <li key={index}>
                {visible(step.method)}:{' '}
                {step.variables.map((variable) => variable.column).join(', ')}
              </li>
            ))}
          </ul>
        </details>
      )}
      {!!plan.filters?.length && (
        <details>
          <summary>Alcance conservado</summary>
          {plan.filters.map((filter, i) => (
            <p key={i}>
              <strong>Filtro:</strong> {filter.variable.column} ={' '}
              {filter.values.join(', ')}
            </p>
          ))}
        </details>
      )}
      {!!plan.type_confirmations?.length && (
        <div className="notice">
          <strong>Confirmación del investigador</strong>
          {plan.type_confirmations.map((decision) => (
            <p key={`${decision.variable.file_id}:${decision.variable.column}`}>
              {decision.variable.column}: cuantitativa{' '}
              {decision.statistical_type === 'discrete'
                ? 'discreta'
                : 'continua'}
              . El perfil original se conserva.
            </p>
          ))}
        </div>
      )}
      {comparison && (
        <details>
          <summary>Alcance y decisiones metodológicas</summary>
          <p>
            <strong>Diseño:</strong>{' '}
            {comparison.design === 'independent'
              ? 'Muestras independientes'
              : comparison.design === 'paired'
                ? 'Mediciones pareadas'
                : 'Por aclarar'}
            . Grupos: {comparison.groups.join(' / ')}.
          </p>
          {comparison.filters.map((filter, index) => (
            <p key={index}>
              <strong>Filtro:</strong> {filter.variable.column} ={' '}
              {filter.values.join(', ')}
            </p>
          ))}
          {comparison.strata && (
            <p>
              <strong>Comparaciones por estrato:</strong>{' '}
              {comparison.strata.variable.column}:{' '}
              {comparison.strata.values.join(', ')}
            </p>
          )}
          <p>
            <strong>Independencia requerida:</strong> debe justificarse con el
            diseño de recolección antes de ejecutar inferencia. El texto de la
            propuesta no confirma este supuesto; se revisará en la preparación.
          </p>
          <p>
            <strong>Observaciones válidas:</strong>{' '}
            {visible(comparison.valid_observations)}
          </p>
          <p>
            <strong>Datos ausentes:</strong> {visible(comparison.missing_data)}
          </p>
          <p>
            <strong>Atípicos:</strong> {visible(comparison.outliers)}
          </p>
          <p>
            <strong>Normalidad:</strong> {visible(comparison.normality)}
          </p>
          {comparison.variance_assumption === 'unequal_allowed' && (
            <p>
              Welch admite varianzas distintas; no se exige igualdad de
              varianzas.
            </p>
          )}
          <p>
            <strong>Tamaño del efecto:</strong>{' '}
            {visible(comparison.effect_size.definition)}
          </p>
          <p>
            {visible(comparison.effect_size.correction)} Los intervalos
            disponibles se limitarán a los implementados y metodológicamente
            validados en la preparación.
          </p>
          <p>
            <strong>Comparaciones múltiples:</strong>{' '}
            {comparison.multiplicity === 'holm'
              ? 'Holm'
              : comparison.multiplicity === 'none'
                ? 'Sin ajuste propuesto'
                : 'Decisión pendiente'}
            . {visible(comparison.multiplicity_reason)}
          </p>
        </details>
      )}
      {!!plan.joins?.length && (
        <div>
          <strong>Relaciones a verificar antes de ejecutar:</strong>
          <ul>
            {plan.joins.map((join, index) => (
              <li key={index}>
                {join.left.column} ↔ {join.right.column}:{' '}
                {visible(join.justification)}
              </li>
            ))}
          </ul>
        </div>
      )}
      {proposal.status === 'proposed' ? (
        <div className="chat-actions">
          <button
            className="btn primary"
            disabled={busy}
            onClick={() => onDecide('accepted')}
          >
            Aceptar plan
          </button>
          <button
            className="btn secondary"
            disabled={busy}
            onClick={() => onDecide('rejected')}
          >
            Rechazar
          </button>
        </div>
      ) : (
        proposal.status === 'accepted' && (
          <div className="chat-actions">
            <p>
              Plan aceptado. Statia preparará el análisis y te preguntará solo
              por las decisiones pendientes. Podrás revisarlo antes de calcular.
            </p>
            <button
              className="btn primary"
              disabled={busy || !onExecute}
              onClick={onExecute}
            >
              {prepared ? 'Volver a preparar análisis' : 'Ejecutar análisis'}
            </button>
          </div>
        )
      )}
    </article>
  )
}
