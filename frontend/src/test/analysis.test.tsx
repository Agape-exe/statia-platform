// Contratos y comportamiento de interfaz con servicios controlados, sin Supabase remoto.
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { ExecutionReview } from '../components/ExecutionReview'
import { ExecutionPreparationCard } from '../components/ExecutionPreparationCard'
import { ProposalCard } from '../components/ProposalCard'
import { AnalysisResultCard } from '../components/AnalysisResultCard'
import { AnalysisResults } from '../components/AnalysisResults'
import { analysisService } from '../services/analysis'
import { chatService } from '../services/chat'
import { formatResult } from '../lib/analysis-format'
import type { ProjectFile, Proposal } from '../types/chat'
import type {
  AnalysisRun,
  ExecutionPreparation,
  ProcedureInfo,
} from '../types/analysis'

vi.mock('../services/analysis', () => ({
  analysisService: {
    catalog: vi.fn(),
    get: vi.fn(),
    list: vi.fn(),
    execute: vi.fn(),
    artifact: vi.fn(),
    downloadZip: vi.fn(),
    downloadArtifact: vi.fn(),
  },
}))
vi.mock('../services/chat', () => ({ chatService: { list: vi.fn() } }))

const variables = [
  { file_id: 'archivo', sheet: 'tabla', column: 'medida', role: 'outcome' },
  { file_id: 'archivo', sheet: 'tabla', column: 'grupo', role: 'group' },
]
const proposal: Proposal = {
  id: 'propuesta',
  title: 'Comparar medidas',
  objective: 'Comparar mediciones',
  status: 'accepted',
  analysis_plan: {
    schema_version: 1,
    title: 'Comparar medidas',
    objective: 'Comparar mediciones',
    procedure: 'group_comparison',
    method: 'Student o Welch por confirmar',
    variables,
    justification: 'Grupos independientes',
    requirements: ['Revisar supuestos'],
    limitations: ['Sin causalidad'],
    expected_outputs: ['Tablas'],
    joins: [],
  },
}
const files: ProjectFile[] = [
  {
    id: 'archivo',
    original_name: 'mediciones.csv',
    file_type: 'csv',
    file_role: 'dataset',
    file_size: 100,
    metadata: {
      sheets: ['tabla'],
      selected_sheet: 'tabla',
      profile: {
        row_count: 6,
        column_count: 2,
        missing_count: 1,
        duplicate_rows: 0,
        columns: [
          {
            name: 'medida',
            physical_type: 'numeric',
            statistical_type: 'quantitative',
            semantic_hint: '',
            missing: 1,
            unique: 5,
            missing_markers: { NA: 1 },
          },
          {
            name: 'grupo',
            physical_type: 'text',
            statistical_type: 'categorical',
            semantic_hint: '',
            missing: 0,
            unique: 2,
          },
        ],
      },
    },
  },
]
const catalog: ProcedureInfo[] = [
  {
    code: 'welch_t',
    name: 't de Welch',
    families: ['group_comparison'],
    variable_types: 'Cuantitativa y categórica',
    design: 'Independiente',
    groups: '2',
    assumptions: ['Independencia pendiente de diseño'],
    parameters: [],
    statistics: ['t', 'p'],
    effects: ['d', 'g'],
    limitations: ['Sin IC de d/g'],
  },
]
const run = {
  id: 'ejecucion',
  project_id: 'proyecto',
  conversation_id: 'chat',
  proposal_id: 'propuesta',
  request_id: 'solicitud',
  title: 'Comparar medidas',
  status: 'completed',
  created_at: '2026-11-15T18:00:00Z',
  finished_at: '2026-11-15T18:00:03Z',
  error: null,
  artifact_count: 1,
  methods: ['t de Welch'],
  artifacts: [],
  result: {
    title: 'Comparar medidas',
    summary:
      '1 de 1 componentes con resultados. ¿Tienes alguna duda o pregunta respecto a los resultados que hemos obtenido?',
    files: [],
    dependencies: { scipy: '1.18.1' },
    specification: {},
    components: [
      {
        source_index: 0,
        method: 'welch_t',
        title: 't de Welch',
        status: 'completed',
        error: null,
        scope: {},
        sample: { initial: 6, used: 5 },
        statistics: {},
        assumptions: [
          {
            name: 'Independencia',
            status: 'pending',
            detail: 'Revisar el diseño.',
          },
        ],
        warnings: ['Sin IC de d/g'],
        charts: [],
        interpretation: 'No demuestra causalidad ni prueba ausencia de efecto.',
        tables: [
          {
            title: 'Contraste calculado',
            columns: ['Medida', 'Valor'],
            rows: [
              { Medida: 'p', Valor: 0.00000012 },
              { Medida: 'd de Cohen', Valor: null },
            ],
          },
        ],
      },
    ],
  },
} as unknown as AnalysisRun

beforeEach(() => {
  vi.resetAllMocks()
  sessionStorage.clear()
  vi.mocked(analysisService.catalog).mockResolvedValue(catalog)
  vi.mocked(analysisService.get).mockResolvedValue(run)
  vi.mocked(analysisService.list).mockResolvedValue([run])
  vi.mocked(chatService.list).mockResolvedValue([])
})

describe('revisión y ejecución', () => {
  it('aceptar no ejecuta y la acción abre la revisión', async () => {
    const execute = vi.fn()
    render(
      <ProposalCard
        proposal={proposal}
        files={files}
        busy={false}
        onDecide={vi.fn()}
        onExecute={execute}
      />,
    )
    expect(execute).not.toHaveBeenCalled()
    await userEvent.click(
      screen.getByRole('button', { name: 'Ejecutar análisis' }),
    )
    expect(execute).toHaveBeenCalledOnce()
    expect(analysisService.execute).not.toHaveBeenCalled()
  })

  it('confirma método/tipos/ausencias/diseño y conserva UUID al reintentar', async () => {
    const execute = vi
      .fn()
      .mockRejectedValueOnce(new Error('Fallo temporal de Storage.'))
      .mockResolvedValueOnce(undefined)
    const close = vi.fn()
    const view = render(
      <ExecutionReview
        projectId="proyecto"
        conversationId="chat"
        proposal={proposal}
        files={files}
        busy={false}
        onClose={close}
        onExecute={execute}
      />,
    )
    await screen.findByRole('option', { name: /t de Welch/ })
    expect(
      screen.getByRole('button', { name: 'Ejecutar análisis confirmado' }),
    ).toBeDisabled()
    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: 'Procedimiento confirmado' }),
      'welch_t',
    )
    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: 'Tipo de medida' }),
      'continuous',
    )
    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: 'Tipo de grupo' }),
      'nominal',
    )
    await userEvent.selectOptions(
      screen.getByRole('combobox', { name: /Marcador «NA»/ }),
      'missing',
    )
    await userEvent.type(
      screen.getByRole('textbox', {
        name: /Otros marcadores de ausencia de medida/,
      }),
      '-999',
    )
    await userEvent.click(
      screen.getByRole('checkbox', { name: /Declaro un diseño/ }),
    )
    await userEvent.click(
      screen.getByRole('checkbox', { name: /Confirmo los métodos/ }),
    )
    await userEvent.click(
      screen.getByRole('button', { name: 'Ejecutar análisis confirmado' }),
    )
    await screen.findByText('Fallo temporal de Storage.')
    expect(close).not.toHaveBeenCalled()
    const first = execute.mock.calls[0][0]
    expect(first.specification.components[0].method).toBe('welch_t')
    expect(first.specification.decisions[0].missing_markers).toEqual([
      'NA',
      '-999',
    ])
    view.unmount()
    render(
      <ExecutionReview
        projectId="proyecto"
        conversationId="chat"
        proposal={proposal}
        files={files}
        busy={false}
        onClose={close}
        onExecute={execute}
      />,
    )
    await screen.findByRole('option', { name: /t de Welch/ })
    expect(
      screen.getByRole('combobox', { name: 'Tipo de medida' }),
    ).toHaveValue('continuous')
    expect(
      screen.getByRole('checkbox', { name: /Confirmo los métodos/ }),
    ).not.toBeChecked()
    await userEvent.click(
      screen.getByRole('checkbox', { name: /Confirmo los métodos/ }),
    )
    await userEvent.click(
      screen.getByRole('button', { name: 'Ejecutar análisis confirmado' }),
    )
    expect(execute.mock.calls[1][0]).toEqual(first)
    await waitFor(() => expect(close).toHaveBeenCalledOnce())
  })

  it('el fallo del catálogo es explícito y permite reintentar', async () => {
    vi.mocked(analysisService.catalog).mockRejectedValueOnce(
      new Error('API no disponible'),
    )
    render(
      <ExecutionReview
        projectId="proyecto"
        conversationId="chat"
        proposal={proposal}
        files={files}
        busy={false}
        onClose={vi.fn()}
        onExecute={vi.fn()}
      />,
    )
    await screen.findByText(/API no disponible/)
    await userEvent.click(
      screen.getByRole('button', { name: 'Reintentar catálogo' }),
    )
    await screen.findByRole('option', { name: /t de Welch/ })
  })
})

const preparation: ExecutionPreparation = {
  request_id: '00000000-0000-4000-8000-000000000099',
  status: 'READY',
  specification: {
    schema_version: 1,
    components: [
      {
        source_index: 0,
        method: 'welch_t',
        design: 'independent',
        equal_variances_confirmed: false,
        group_values: ['A', 'B'],
        posthoc: 'none',
      },
    ],
    decisions: variables.map((variable, i) => ({
      variable,
      statistical_type: i === 0 ? 'continuous' : 'nominal',
      missing_markers: i === 0 ? ['NA'] : [],
      retained_markers: [],
      ordinal_order: [],
      unit: '',
    })),
    filters: [],
    confidence_level: 0.95,
    alternative: 'two-sided',
    missing_policy: 'available_cases_per_procedure',
    multiplicity: 'none',
    decisions_confirmed: false,
  },
  methods: ['t de Welch'],
  reasons: ['Se conserva el método aceptado.'],
  evidence: [
    {
      subject: 'Medida',
      origin: 'inferred',
      detail: 'Perfil numérico consistente.',
    },
  ],
  warnings: ['El diseño procede de lo informado por el usuario.'],
  blockers: [],
  questions: [],
  files: [
    {
      id: 'archivo',
      name: 'mediciones.csv',
      sheet: 'tabla',
      sha256: 'a'.repeat(64),
      rows: 6,
    },
  ],
  fingerprint: 'b'.repeat(64),
}

describe('preparación conversacional', () => {
  function prepared(
    props: Partial<React.ComponentProps<typeof ExecutionPreparationCard>> = {},
  ) {
    return render(
      <ExecutionPreparationCard
        preparation={preparation}
        proposal={proposal}
        projectId="proyecto"
        conversationId="chat"
        busy={false}
        onAnswer={vi.fn()}
        onCancel={vi.fn()}
        onAdvanced={vi.fn()}
        onExecute={vi.fn()}
        {...props}
      />,
    )
  }
  it('presenta un resumen y calcula únicamente tras la confirmación final', async () => {
    const execute = vi.fn().mockResolvedValue(undefined)
    prepared({ onExecute: execute })
    expect(
      screen.getByRole('heading', { name: 'Análisis preparado' }),
    ).toBeInTheDocument()
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    expect(execute).not.toHaveBeenCalled()
    await userEvent.click(
      screen.getByRole('button', { name: 'Ejecutar análisis' }),
    )
    expect(execute).toHaveBeenCalledOnce()
    expect(execute.mock.calls[0][0].specification.decisions_confirmed).toBe(
      true,
    )
    expect(execute.mock.calls[0][0].preparation_fingerprint).toBe(
      preparation.fingerprint,
    )
    expect(preparation.specification?.decisions_confirmed).toBe(false)
    expect(
      await screen.findByRole('heading', { name: 'Análisis ejecutado' }),
    ).toBeInTheDocument()
  })
  it('conserva el UUID y las decisiones al fallar y reabrir', async () => {
    const execute = vi
      .fn()
      .mockRejectedValueOnce(new Error('Storage temporalmente no disponible'))
      .mockResolvedValue(undefined)
    const first = prepared({ onExecute: execute })
    await userEvent.click(
      screen.getByRole('button', { name: 'Ejecutar análisis' }),
    )
    await screen.findByText('Storage temporalmente no disponible')
    const body = execute.mock.calls[0][0]
    first.unmount()
    prepared({ onExecute: execute })
    await userEvent.click(
      screen.getByRole('button', { name: 'Ejecutar análisis' }),
    )
    expect(execute.mock.calls[1][0]).toEqual(body)
  })
  it('pregunta con opciones claras y nunca ejecuta con aclaraciones pendientes', async () => {
    const answer = vi.fn()
    prepared({
      onAnswer: answer,
      preparation: {
        ...preparation,
        status: 'NEEDS_CLARIFICATION',
        questions: [
          {
            id: 'q1',
            prompt: '¿Qué significa NA en grupo?',
            explanation: 'Puede ser información ausente o una categoría.',
            choices: [
              { value: 'missing', label: 'Representa información faltante' },
              { value: 'unknown', label: 'No lo sé' },
            ],
          },
        ],
      },
    })
    expect(
      screen.queryByRole('button', { name: 'Ejecutar análisis' }),
    ).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'No lo sé' }))
    expect(answer).toHaveBeenCalledWith('q1', 'unknown', 'No lo sé')
    expect(screen.getByText(/sin inventar supuestos/)).toBeInTheDocument()
  })
  it('muestra impedimentos y conserva el acceso a las opciones avanzadas', async () => {
    const advanced = vi.fn()
    prepared({
      onAdvanced: advanced,
      preparation: {
        ...preparation,
        status: 'UNSUPPORTED',
        blockers: ['El método requiere una tabla 2×2.'],
      },
    })
    expect(screen.getByRole('alert')).toHaveTextContent('2×2')
    expect(
      screen.queryByRole('button', { name: 'Ejecutar análisis' }),
    ).not.toBeInTheDocument()
    await userEvent.click(
      screen.getByRole('button', { name: 'Opciones avanzadas' }),
    )
    expect(advanced).toHaveBeenCalledOnce()
  })
  it('deshabilita controles durante la preparación o el cálculo', () => {
    prepared({ busy: true })
    for (const button of screen.getAllByRole('button'))
      expect(button).toBeDisabled()
  })
  it('precarga decisiones preparadas en el modo avanzado sin confirmar ni calcular', async () => {
    const execute = vi.fn()
    render(
      <ExecutionReview
        projectId="proyecto"
        conversationId="chat"
        proposal={proposal}
        files={files}
        busy={false}
        initialSpecification={preparation.specification}
        onClose={vi.fn()}
        onExecute={execute}
      />,
    )
    await screen.findByRole('option', { name: /t de Welch/ })
    expect(
      screen.getByRole('combobox', { name: 'Procedimiento confirmado' }),
    ).toHaveValue('welch_t')
    expect(
      screen.getByRole('combobox', { name: 'Tipo de medida' }),
    ).toHaveValue('continuous')
    expect(
      screen.getByRole('checkbox', { name: /Confirmo los métodos/ }),
    ).not.toBeChecked()
    expect(execute).not.toHaveBeenCalled()
  })
})

describe('resultados persistidos', () => {
  it('recupera tabla, interpretación, advertencias y ZIP sin depender de Gemini', async () => {
    render(
      <MemoryRouter>
        <AnalysisResultCard projectId="proyecto" runId="ejecucion" expanded />
      </MemoryRouter>,
    )
    await screen.findByRole('heading', { name: 'Comparar medidas' })
    expect(screen.getByRole('table')).toHaveTextContent('< 0.001')
    expect(screen.getByRole('table')).toHaveTextContent('No disponible')
    expect(screen.getByText(/No demuestra causalidad/)).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Descargar ZIP' }))
    expect(analysisService.downloadZip).toHaveBeenCalledWith(
      'proyecto',
      'ejecucion',
    )
    expect(
      screen.getByRole('link', { name: 'Abrir en Resultados' }),
    ).toHaveAttribute('href', '/proyectos/proyecto/resultados?run=ejecucion')
  })

  it('agrupa ejecuciones por conversación y abre el detalle', async () => {
    vi.mocked(chatService.list).mockResolvedValue([
      { id: 'chat', title: 'Mi estudio' },
    ] as never)
    render(
      <MemoryRouter>
        <AnalysisResults projectId="proyecto" />
      </MemoryRouter>,
    )
    await screen.findByRole('heading', { name: 'Mi estudio' })
    await userEvent.click(
      screen.getByRole('button', { name: 'Consultar y descargar' }),
    )
    const result = await screen.findByRole('article', {
      name: 'Resultado: Comparar medidas',
    })
    expect(within(result).getByRole('table')).toBeInTheDocument()
  })

  it('muestra vacío y error de acceso sin datos de otras cuentas', async () => {
    vi.mocked(analysisService.list).mockResolvedValue([])
    const view = render(
      <MemoryRouter>
        <AnalysisResults projectId="proyecto" />
      </MemoryRouter>,
    )
    await screen.findByText('Aún no hay ejecuciones')
    view.unmount()
    vi.mocked(analysisService.get).mockRejectedValue(
      new Error('El recurso no existe o no tienes acceso.'),
    )
    render(
      <MemoryRouter>
        <AnalysisResultCard projectId="otro" runId="ejecucion" />
      </MemoryRouter>,
    )
    await screen.findByText(/no tienes acceso/)
    expect(
      screen.queryByRole('button', { name: 'Descargar ZIP' }),
    ).not.toBeInTheDocument()
  })

  it('redondea p y representa medidas no disponibles sin ceros ficticios', () => {
    expect(formatResult(0.000000001, 'p')).toBe('< 0.001')
    expect(formatResult(0.0323242, 'p Holm')).toBe('0.0323')
    expect(formatResult(null)).toBe('No disponible')
    expect(formatResult(Infinity)).toBe('No calculable')
  })
})
