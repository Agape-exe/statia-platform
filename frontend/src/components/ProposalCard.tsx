import type { ProjectFile, Proposal } from '../types/chat'
import { visibleChatText } from '../lib/chat-text'

export function ProposalCard({
  proposal,
  files,
  busy,
  onDecide,
  onExecute,
}: {
  proposal: Proposal
  files: ProjectFile[]
  busy: boolean
  onDecide: (status: 'accepted' | 'rejected') => void
  onExecute?: () => void
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
      ).map(([title, values]) => (
        <details key={title}>
          <summary>{title}</summary>
          <ul>
            {values.map((value, index) => (
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
            <strong>Independencia:</strong> {visible(comparison.independence)}
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
            {visible(comparison.effect_size.correction)}{' '}
            {visible(comparison.effect_size.confidence_interval)}
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
              Plan aceptado. Revisa el procedimiento, los tipos y las ausencias
              antes de calcular.
            </p>
            <button
              className="btn primary"
              disabled={busy || !onExecute}
              onClick={onExecute}
            >
              Ejecutar análisis
            </button>
          </div>
        )
      )}
    </article>
  )
}
