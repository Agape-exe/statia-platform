import { Link } from 'react-router-dom'
import { componentStatus, type ComponentPreparation } from '../types/analysis'
import { methodNames } from '../lib/analysis-methods'

export function ComponentStates({
  components,
  projectId,
}: {
  components: ComponentPreparation[]
  projectId?: string
}) {
  if (!components.length) return null
  return (
    <section aria-label="Estados por componente" className="component-states">
      <h4>Procedimientos del plan</h4>
      <ul>
        {components.map((component) => (
          <li key={component.id}>
            <strong>
              {component.source_index + 1}.{' '}
              {methodNames[component.method] || component.method}
            </strong>{' '}
            · {componentStatus[component.status]}
            <p>{component.variables.map((v) => v.column).join(', ')}</p>
            {component.blockers.filter(Boolean).map((reason, i) => (
              <p className="muted" key={i}>
                {reason}
              </p>
            ))}
            {component.warnings.filter(Boolean).map((warning, i) => (
              <p className="notice" key={i}>
                {warning}
              </p>
            ))}
            {component.completed_run_id && projectId && (
              <Link
                to={`/proyectos/${projectId}/resultados?run=${component.completed_run_id}`}
              >
                Consultar resultado conservado
              </Link>
            )}
          </li>
        ))}
      </ul>
    </section>
  )
}
