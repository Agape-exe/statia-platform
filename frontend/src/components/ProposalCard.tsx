import type { ProjectFile, Proposal } from '../types/chat'

export function ProposalCard({
  proposal,
  files,
  busy,
  onDecide,
}: {
  proposal: Proposal
  files: ProjectFile[]
  busy: boolean
  onDecide: (status: 'accepted' | 'rejected') => void
}) {
  const plan = proposal.analysis_plan
  return (
    <article
      className="proposal-card"
      aria-label={`Propuesta: ${proposal.title}`}
    >
      <span className="eyebrow">
        {proposal.status === 'accepted'
          ? 'PLAN ACEPTADO'
          : proposal.status === 'rejected'
            ? 'PROPUESTA RECHAZADA'
            : 'PROPUESTA PARA CONFIRMAR'}
      </span>
      <h3>{proposal.title}</h3>
      <p>{proposal.objective}</p>
      <p>
        <strong>Procedimiento:</strong> {plan.method}
      </p>
      <ul>
        {plan.variables.map((variable, index) => (
          <li key={index}>
            {files.find((f) => f.id === variable.file_id)?.original_name ||
              variable.file_id}{' '}
            / {variable.sheet}: <strong>{variable.column}</strong>
          </li>
        ))}
      </ul>
      <p>
        <strong>Justificación:</strong> {plan.justification}
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
              <li key={index}>{value}</li>
            ))}
          </ul>
        </details>
      ))}
      {!!plan.joins?.length && (
        <div>
          <strong>Relaciones a verificar antes de ejecutar:</strong>
          <ul>
            {plan.joins.map((join, index) => (
              <li key={index}>
                {join.left.column} ↔ {join.right.column}: {join.justification}
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
          <p className="notice">
            Plan preparado para la Sesión 03. Todavía no se ejecutaron pruebas
            estadísticas.
          </p>
        )
      )}
    </article>
  )
}
