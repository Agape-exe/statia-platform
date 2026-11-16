import { Link } from 'react-router-dom'
import { componentStatus, type ComponentPreparation } from '../types/analysis'
const methodNames: Record<string, string> = {
  descriptive: 'Estadística descriptiva',
  pearson: 'Correlación de Pearson (inferencia)',
  spearman: 'Correlación de Spearman (inferencia)',
  student_t: 't de Student',
  welch_t: 't de Welch',
  anova: 'ANOVA',
  welch_anova: 'ANOVA de Welch',
  paired_t: 't pareada',
  mann_whitney: 'Mann–Whitney',
  wilcoxon: 'Wilcoxon',
  kruskal: 'Kruskal–Wallis',
  chi_square: 'Chi-cuadrado',
  fisher_exact: 'Fisher exacto',
}

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
