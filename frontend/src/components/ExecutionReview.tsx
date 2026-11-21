import { useEffect, useRef, useState } from 'react'
import { analysisService } from '../services/analysis'
import type { ProjectFile, Proposal } from '../types/chat'
import type {
  ExecuteRequest,
  ExecutionComponent,
  ExecutionSpec,
  ProcedureInfo,
  StatisticalType,
} from '../types/analysis'
import { Alert, Loading } from './ui'
import { Modal } from './Modal'

const types: [StatisticalType, string][] = [
  ['continuous', 'Cuantitativa continua'],
  ['discrete', 'Cuantitativa discreta'],
  ['ordinal', 'Ordinal'],
  ['nominal', 'Nominal'],
  ['binary', 'Binaria'],
  ['temporal', 'Temporal'],
  ['identifier', 'Identificador'],
]
const variableKey = (v: { file_id: string; sheet: string; column: string }) =>
  JSON.stringify([v.file_id, v.sheet, v.column])

function pendingExecution(storageKey: string): ExecuteRequest | null {
  try {
    const value = JSON.parse(
      sessionStorage.getItem(storageKey) || 'null',
    ) as ExecuteRequest | null
    return value?.specification?.schema_version === 1 &&
      Array.isArray(value.specification.components) &&
      Array.isArray(value.specification.decisions)
      ? value
      : null
  } catch {
    return null
  }
}

export function ExecutionReview({
  projectId,
  conversationId,
  proposal,
  files,
  busy,
  onClose,
  onExecute,
  initialSpecification,
}: {
  projectId: string
  conversationId: string
  proposal: Proposal
  files: ProjectFile[]
  busy: boolean
  onClose: () => void
  onExecute: (body: ExecuteRequest) => Promise<void>
  initialSpecification?: ExecutionSpec | null
}) {
  const plan = proposal.analysis_plan
  const filters = plan.filters?.length
    ? plan.filters
    : plan.comparison?.filters || []
  const sources = plan.procedure === 'integral' ? plan.components || [] : [plan]
  const storageKey = `statia:execution:${projectId}:${conversationId}:${proposal.id}`
  const [saved] = useState(
    () =>
      pendingExecution(storageKey) ||
      (initialSpecification
        ? {
            request_id: crypto.randomUUID(),
            specification: initialSpecification,
          }
        : null),
  )
  const [catalog, setCatalog] = useState<ProcedureInfo[] | null>(null)
  const [error, setError] = useState('')
  const [attempt, setAttempt] = useState(0)
  const [methods, setMethods] = useState<string[]>(() =>
    sources.map(
      (_, i) =>
        saved?.specification.components.find((c) => c.source_index === i)
          ?.method || '',
    ),
  )
  const [independent, setIndependent] = useState(
    () =>
      saved?.specification.components.some((c) => c.design === 'independent') ||
      false,
  )
  const [paired, setPaired] = useState(
    () =>
      saved?.specification.components.some((c) => c.design === 'paired') ||
      false,
  )
  const [posthoc, setPosthoc] = useState<('none' | 'welch_holm')[]>(() =>
    sources.map(
      (_, i) =>
        saved?.specification.components.find((c) => c.source_index === i)
          ?.posthoc || 'none',
    ),
  )
  const [equal, setEqual] = useState(
    () =>
      saved?.specification.components.some(
        (c) => c.equal_variances_confirmed,
      ) || false,
  )
  const [confidence, setConfidence] = useState(
    saved?.specification.confidence_level || 0.95,
  )
  const [multiplicity, setMultiplicity] = useState<'none' | 'holm'>(
    saved?.specification.multiplicity ||
      (plan.comparison?.multiplicity === 'holm' ? 'holm' : 'none'),
  )
  const [confirmed, setConfirmed] = useState(false)
  const [decisions, setDecisions] = useState(() =>
    plan.variables.map((variable) => {
      const decision = saved?.specification.decisions.find(
        (d) => variableKey(d.variable) === variableKey(variable),
      )
      const column = files
        .find((f) => f.id === variable.file_id)
        ?.metadata.profile?.columns.find((c) => c.name === variable.column)
      const known = Object.keys({
        ...column?.ambiguous_missing,
        ...column?.missing_markers,
      })
      return {
        variable,
        type: decision?.statistical_type || '',
        unit: decision?.unit || '',
        extraMarkers: (decision?.missing_markers || [])
          .filter((m) => !known.includes(m))
          .join('\n'),
        extraRetained: (decision?.retained_markers || [])
          .filter((m) => !known.includes(m))
          .join('\n'),
        ordinal: decision?.ordinal_order.join('\n') || '',
        markers: Object.fromEntries(
          [
            ...(decision?.missing_markers || []).map((m) => [m, 'missing']),
            ...(decision?.retained_markers || []).map((m) => [m, 'retained']),
          ].filter(([marker]) => known.includes(marker)),
        ) as Record<string, 'missing' | 'retained' | ''>,
      }
    }),
  )
  const pending = useRef<ExecuteRequest | null>(saved)
  const submitting = useRef(false)
  useEffect(() => {
    let active = true
    analysisService
      .catalog(projectId)
      .then((value) => {
        if (active) setCatalog(value)
      })
      .catch((caught) => {
        if (active)
          setError(
            caught instanceof Error
              ? caught.message
              : 'No se pudo cargar el catálogo.',
          )
      })
    return () => {
      active = false
    }
  }, [projectId, attempt])

  function changeDecision(
    index: number,
    update: Partial<(typeof decisions)[number]>,
  ) {
    setDecisions((current) =>
      current.map((decision, i) =>
        i === index ? { ...decision, ...update } : decision,
      ),
    )
    setConfirmed(false)
  }

  async function submit(event: React.SubmitEvent<HTMLFormElement>) {
    event.preventDefault()
    if (submitting.current || busy || !catalog) return
    setError('')
    if (!sources.length) {
      setError(
        'El plan antiguo no declara componentes. Solicita una propuesta actualizada.',
      )
      return
    }
    if (decisions.some((d) => !d.type) || methods.some((m) => !m)) {
      setError(
        'Selecciona cada procedimiento y el tipo de todas las variables.',
      )
      return
    }
    for (const decision of decisions) {
      const column = files
        .find((f) => f.id === decision.variable.file_id)
        ?.metadata.profile?.columns.find(
          (c) => c.name === decision.variable.column,
        )
      if (
        Object.keys(
          column?.missing_markers || column?.ambiguous_missing || {},
        ).some((marker) => !decision.markers[marker])
      ) {
        setError(
          `Resuelve todos los marcadores de «${decision.variable.column}».`,
        )
        return
      }
    }
    const components: ExecutionComponent[] = sources.map((_, index) => ({
      source_index: index,
      descriptive_intervals: false,
      method: methods[index] as ExecutionComponent['method'],
      design: ['paired_t', 'wilcoxon'].includes(methods[index])
        ? paired
          ? 'paired'
          : 'not_applicable'
        : independent
          ? 'independent'
          : 'not_applicable',
      equal_variances_confirmed: equal,
      group_values:
        plan.comparison &&
        ['student_t', 'welch_t', 'mann_whitney'].includes(methods[index])
          ? plan.comparison.groups
          : [],
      posthoc: ['anova', 'welch_anova'].includes(methods[index])
        ? posthoc[index]
        : 'none',
    }))
    const specification: ExecutionSpec = {
      schema_version: 1,
      components,
      decisions: decisions.map((d) => ({
        variable: d.variable,
        statistical_type: d.type as StatisticalType,
        unit: d.unit,
        ordinal_order: d.ordinal
          .split('\n')
          .map((s) => s.trim())
          .filter(Boolean),
        missing_markers: [
          ...new Set([
            ...Object.entries(d.markers)
              .filter(([, choice]) => choice === 'missing')
              .map(([marker]) => marker),
            ...d.extraMarkers
              .split('\n')
              .map((m) => m.trim())
              .filter(Boolean),
          ]),
        ],
        retained_markers: [
          ...new Set([
            ...Object.entries(d.markers)
              .filter(([, choice]) => choice === 'retained')
              .map(([marker]) => marker),
            ...d.extraRetained
              .split('\n')
              .map((m) => m.trim())
              .filter(Boolean),
          ]),
        ],
      })),
      filters,
      confidence_level: confidence,
      alternative: 'two-sided',
      missing_policy: 'available_cases_per_procedure',
      multiplicity,
      decisions_confirmed: confirmed,
    }
    // Conserva el UUID ante errores de red y al recargar esta pestaña; no guarda archivos originales.
    try {
      const stored = sessionStorage.getItem(storageKey)
      if (stored) pending.current = JSON.parse(stored) as ExecuteRequest
    } catch {
      /* La API sigue protegiendo el UUID del intento en memoria. */
    }
    if (
      !pending.current ||
      JSON.stringify(pending.current.specification) !==
        JSON.stringify(specification)
    ) {
      pending.current = { request_id: crypto.randomUUID(), specification }
    }
    try {
      sessionStorage.setItem(storageKey, JSON.stringify(pending.current))
    } catch {
      /* Almacenamiento opcional. */
    }
    submitting.current = true
    try {
      await onExecute(pending.current)
      try {
        sessionStorage.removeItem(storageKey)
      } catch {
        /* Almacenamiento opcional. */
      }
      onClose()
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : 'La ejecución falló. Puedes reintentar la misma solicitud.',
      )
    } finally {
      submitting.current = false
    }
  }

  return (
    <Modal
      title="Opciones avanzadas de ejecución"
      onClose={onClose}
      busy={busy}
      className="analysis-modal"
    >
      {!catalog && !error ? (
        <Loading />
      ) : (
        <form onSubmit={submit} className="execution-review">
          <p>
            Confirma las decisiones definitivas de <strong>{plan.title}</strong>
            . Los cálculos leerán los originales; se conservarán el plan, los
            filtros y las exclusiones.
          </p>
          {error && (
            <Alert>
              {error}{' '}
              {!catalog && (
                <button
                  type="button"
                  onClick={() => {
                    setError('')
                    setAttempt((n) => n + 1)
                  }}
                >
                  Reintentar catálogo
                </button>
              )}
            </Alert>
          )}
          {sources.map((source, index) => {
            const available =
              catalog?.filter((p) => p.families.includes(source.procedure)) ||
              []
            const chosen = available.find((p) => p.code === methods[index])
            return (
              <fieldset key={index} disabled={busy}>
                <legend>
                  Componente {index + 1}:{' '}
                  {source.variables.map((v) => v.column).join(', ')}
                </legend>
                <p className="muted">Propuesta aceptada: {source.method}</p>
                <label>
                  Procedimiento confirmado
                  <select
                    required
                    value={methods[index]}
                    onChange={(e) => {
                      setMethods((current) =>
                        current.map((m, i) =>
                          i === index ? e.target.value : m,
                        ),
                      )
                      setConfirmed(false)
                    }}
                  >
                    <option value="">Selecciona un método</option>
                    {available.map((p) => (
                      <option value={p.code} key={p.code}>
                        {p.name} · grupos: {p.groups}
                      </option>
                    ))}
                  </select>
                </label>
                {!available.length && (
                  <p>
                    No hay procedimientos implementados para esta familia.
                    Solicita un plan compatible.
                  </p>
                )}
                {source.procedure === 'group_comparison' && (
                  <p>
                    Para grupos independientes, Welch permite varianzas
                    distintas y es una opción a considerar si no justificas
                    igualdad. Confirma el número de grupos, el diseño y las
                    distribuciones; el método no se elige por el valor p.
                  </p>
                )}
                {['anova', 'welch_anova'].includes(methods[index]) && (
                  <label>
                    Comparaciones por pares preespecificadas
                    <select
                      value={posthoc[index]}
                      onChange={(e) => {
                        setPosthoc((current) =>
                          current.map((p, i) =>
                            i === index
                              ? (e.target.value as 'none' | 'welch_holm')
                              : p,
                          ),
                        )
                        setConfirmed(false)
                      }}
                    >
                      <option value="none">Solo contraste global</option>
                      <option value="welch_holm">
                        Todas las parejas: Welch + Holm (familia separada)
                      </option>
                    </select>
                    <span>
                      Selección previa al cálculo; los IC de las diferencias son
                      individuales, no simultáneos.
                    </span>
                  </label>
                )}
                {chosen && (
                  <>
                    <p>
                      {chosen.variable_types}. Diseño: {chosen.design}.
                    </p>
                    <ul>
                      {[...chosen.assumptions, ...chosen.limitations].map(
                        (s, i) => (
                          <li key={i}>{s}</li>
                        ),
                      )}
                    </ul>
                  </>
                )}
              </fieldset>
            )
          })}
          <details open>
            <summary>Tipos y ausencias por archivo y variable</summary>
            {decisions.map((decision, index) => {
              const file = files.find((f) => f.id === decision.variable.file_id)
              const column = file?.metadata.profile?.columns.find(
                (c) => c.name === decision.variable.column,
              )
              const markers = Object.keys(
                column?.missing_markers || column?.ambiguous_missing || {},
              )
              return (
                <fieldset key={variableKey(decision.variable)} disabled={busy}>
                  <legend>
                    {file?.original_name || 'Archivo no disponible'}
                    {file?.file_type === 'xlsx' &&
                      ` / ${decision.variable.sheet}`}{' '}
                    / {decision.variable.column}
                  </legend>
                  <p className="muted">
                    Perfil tentativo:{' '}
                    {column?.statistical_type || 'desconocido'}; representación:{' '}
                    {column?.physical_type || 'desconocida'}. Confirma su
                    significado en este estudio.
                  </p>
                  <label>
                    Tipo de {decision.variable.column}
                    <select
                      value={decision.type}
                      required
                      onChange={(e) =>
                        changeDecision(index, { type: e.target.value })
                      }
                    >
                      <option value="">Selecciona el tipo estadístico</option>
                      {types.map(([value, title]) => (
                        <option key={value} value={value}>
                          {title}
                        </option>
                      ))}
                    </select>
                  </label>
                  {decision.type === 'ordinal' && (
                    <label>
                      Orden de menor a mayor (una categoría por línea)
                      <textarea
                        required
                        value={decision.ordinal}
                        onChange={(e) =>
                          changeDecision(index, { ordinal: e.target.value })
                        }
                      />
                    </label>
                  )}
                  {['continuous', 'discrete'].includes(decision.type) && (
                    <label>
                      Unidad, si se conoce
                      <input
                        value={decision.unit}
                        maxLength={60}
                        onChange={(e) =>
                          changeDecision(index, { unit: e.target.value })
                        }
                      />
                    </label>
                  )}
                  {markers.map((marker) => (
                    <label key={marker}>
                      Marcador «{marker}» en {decision.variable.column}
                      <select
                        required
                        value={decision.markers[marker] || ''}
                        onChange={(e) =>
                          changeDecision(index, {
                            markers: {
                              ...decision.markers,
                              [marker]: e.target.value as
                                'missing' | 'retained',
                            },
                          })
                        }
                      >
                        <option value="">Decisión pendiente</option>
                        <option value="missing">Es una ausencia</option>
                        <option value="retained">
                          Es un valor legítimo; conservar
                        </option>
                      </select>
                    </label>
                  ))}
                  <label>
                    Otros marcadores de ausencia de {decision.variable.column}{' '}
                    (opcional, uno por línea)
                    <textarea
                      value={decision.extraMarkers}
                      maxLength={6000}
                      onChange={(e) =>
                        changeDecision(index, { extraMarkers: e.target.value })
                      }
                    />
                    <span>
                      Solo para esta variable y ejecución. Se ignoran espacios
                      exteriores del marcador; en medidas cuantitativas, -999 y
                      -999.0 representan el mismo valor. El original permanece
                      intacto.
                    </span>
                  </label>
                  <label>
                    Otros marcadores que deben conservarse en{' '}
                    {decision.variable.column} (opcional, uno por línea)
                    <textarea
                      value={decision.extraRetained}
                      maxLength={6000}
                      onChange={(e) =>
                        changeDecision(index, { extraRetained: e.target.value })
                      }
                    />
                  </label>
                  {!markers.length && (
                    <p>
                      Los nulos y las celdas vacías cuentan como ausencias.
                      Otros valores se conservan; un valor incompatible
                      bloqueará el cálculo.
                    </p>
                  )}
                </fieldset>
              )
            })}
          </details>
          <fieldset disabled={busy}>
            <legend>Alcance y supuestos</legend>
            {filters.map((f, i) => (
              <p key={i}>
                Filtro conservado: {f.variable.column} ∈ {f.values.join(', ')}.
              </p>
            ))}
            {plan.comparison?.strata && (
              <p>
                Estratos conservados: {plan.comparison.strata.variable.column} ∈{' '}
                {plan.comparison.strata.values.join(', ')}.
              </p>
            )}
            {!!plan.comparison?.groups.length && (
              <p>Orden de grupos: {plan.comparison.groups.join(' − ')}.</p>
            )}
            <p>
              Se usan casos disponibles por variable o parejas/casos completos
              por procedimiento. No se imputan valores ni se eliminan atípicos.
              Los códigos numéricos y ordinales no se convierten automáticamente
              en medidas continuas.
            </p>
            <label>
              Nivel de confianza
              <input
                type="number"
                min={0.8}
                max={0.99}
                step={0.01}
                value={confidence}
                required
                onChange={(e) => {
                  setConfidence(Number(e.target.value))
                  setConfirmed(false)
                }}
              />
            </label>
            <p>
              α = {(1 - confidence).toFixed(2)}. Alternativa bilateral. IC de
              media y diferencia con t; Pearson con Fisher z; IC de d/g y
              Spearman no disponibles. d/g usan SD combinada y J exacto.
            </p>
            <label>
              Ajuste de valores p
              <select
                value={multiplicity}
                disabled={
                  !!plan.comparison &&
                  plan.comparison.multiplicity !== 'pending'
                }
                onChange={(e) => {
                  setMultiplicity(e.target.value as 'none' | 'holm')
                  setConfirmed(false)
                }}
              >
                <option value="none">Sin ajuste (decisión explícita)</option>
                <option value="holm">
                  Holm: todos los contrastes inferenciales de esta ejecución
                </option>
              </select>
            </label>
            {methods.some((m) =>
              [
                'student_t',
                'welch_t',
                'anova',
                'welch_anova',
                'mann_whitney',
                'kruskal',
                'chi_square',
                'fisher_exact',
                'pearson',
                'spearman',
              ].includes(m),
            ) && (
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  required
                  checked={independent}
                  onChange={(e) => {
                    setIndependent(e.target.checked)
                    setConfirmed(false)
                  }}
                />
                Declaro un diseño de grupos independientes. Confirmo que he
                revisado muestreo, repeticiones y conglomerados y que las
                observaciones son independientes según la recolección informada.
              </label>
            )}
            {methods.some((m) => ['student_t', 'anova'].includes(m)) && (
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  required
                  checked={equal}
                  onChange={(e) => {
                    setEqual(e.target.checked)
                    setConfirmed(false)
                  }}
                />
                Justifico el supuesto de igualdad de varianzas requerido por el
                método clásico.
              </label>
            )}
            {methods.some((m) => ['paired_t', 'wilcoxon'].includes(m)) && (
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  required
                  checked={paired}
                  onChange={(e) => {
                    setPaired(e.target.checked)
                    setConfirmed(false)
                  }}
                />
                Confirmo que cada fila contiene dos mediciones del mismo par,
                con identificador único declarado en el plan y pares
                independientes entre sí.
              </label>
            )}
            <label className="checkbox-label">
              <input
                type="checkbox"
                required
                checked={confirmed}
                onChange={(e) => setConfirmed(e.target.checked)}
              />
              Confirmo los métodos, tipos, ausencias, filtros y multiplicidad.
              Comprendo los supuestos y las limitaciones indicadas.
            </label>
          </fieldset>
          <button
            className="btn primary"
            disabled={busy || !catalog || !sources.length || !confirmed}
          >
            {busy ? 'Calculando y guardando…' : 'Ejecutar análisis confirmado'}
          </button>
          {busy && (
            <p role="status">
              Python está calculando y guardando los recursos privados. Mantén
              esta ventana abierta; el chat seguirá disponible al finalizar.
            </p>
          )}
        </form>
      )}
    </Modal>
  )
}
