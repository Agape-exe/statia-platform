import { beforeEach, describe, expect, it, vi } from 'vitest'
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { StatisticalChat } from '../components/StatisticalChat'
import { chatService } from '../services/chat'
import { ApiError } from '../lib/api'
import type { ConversationDetail, ProjectFile, Proposal } from '../types/chat'
import type { Project } from '../types/project'
import { analysisService } from '../services/analysis'
import type { AnalysisRun } from '../types/analysis'

vi.mock('../services/analysis', () => ({
  analysisService: {
    get: vi.fn(),
    list: vi.fn(),
    catalog: vi.fn(),
    execute: vi.fn(),
    artifact: vi.fn(),
    downloadZip: vi.fn(),
    downloadArtifact: vi.fn(),
  },
}))

vi.mock('../services/chat', () => ({
  chatService: {
    providers: vi.fn(),
    changeProvider: vi.fn(),
    list: vi.fn(),
    files: vi.fn(),
    create: vi.fn(),
    get: vi.fn(),
    earlier: vi.fn(),
    rename: vi.fn(),
    remove: vi.fn(),
    turn: vi.fn(),
    upload: vi.fn(),
    sheet: vi.fn(),
    decide: vi.fn(),
    download: vi.fn(),
  },
}))
const project = { id: 'p1', project_type: 'general' } as Project
let detail: ConversationDetail
const dataset: ProjectFile = {
  id: 'f1',
  original_name: 'mediciones.csv',
  file_type: 'csv',
  file_role: 'dataset',
  file_size: 50,
  metadata: {
    sheets: ['tabla'],
    selected_sheet: 'tabla',
    profile: {
      row_count: 3,
      column_count: 1,
      missing_count: 1,
      duplicate_rows: 1,
      columns: [
        {
          name: 'nota',
          physical_type: 'numeric',
          statistical_type: 'categorical_or_ordinal',
          semantic_hint: '',
          missing: 1,
          unique: 2,
          min: 10,
          max: 15,
        },
      ],
    },
  },
}
const proposal: Proposal = {
  id: 'pr1',
  title: 'Describir notas',
  objective: 'Conocer las mediciones',
  status: 'proposed',
  analysis_plan: {
    schema_version: 1,
    title: 'Describir notas',
    objective: 'Conocer las mediciones',
    procedure: 'descriptive',
    method: 'Descriptivos',
    variables: [
      { file_id: 'f1', sheet: 'tabla', column: 'nota', role: 'outcome' },
    ],
    justification: 'Medición disponible',
    requirements: ['Confirmar escala'],
    limitations: ['Sin causalidad'],
    expected_outputs: ['Tabla descriptiva'],
    joins: [],
  },
}

beforeEach(() => {
  vi.resetAllMocks()
  detail = {
    conversation: {
      id: 'c1',
      assistant_provider: 'gemini',
      project_id: 'p1',
      title: 'Nueva conversación',
      primary_goal: null,
      current_stage: 'instrument',
      updated_at: '',
      stage_data: {},
    },
    messages: [
      {
        id: 'm1',
        position: 1,
        role: 'assistant',
        content: 'Hola, puedo ayudarte a entender tus datos.',
        message_type: 'text',
        metadata: {},
      },
    ],
    files: [],
    proposals: [],
  }
  vi.mocked(chatService.list).mockImplementation(async () => [
    detail.conversation,
  ])
  vi.mocked(chatService.files).mockResolvedValue([])
  vi.mocked(chatService.providers).mockResolvedValue({
    default: 'gemini',
    providers: [
      {
        id: 'gemini',
        name: 'Gemini',
        model: 'gemini-test',
        experimental: false,
        enabled: true,
        configured: true,
      },
    ],
  })
  vi.mocked(chatService.get).mockImplementation(async () =>
    structuredClone(detail),
  )
  vi.mocked(chatService.turn).mockResolvedValue({ status: 'completed' })
})

function chat() {
  return render(
    <MemoryRouter>
      <StatisticalChat project={project} />
    </MemoryRouter>,
  )
}

describe('chat persistente y acciones', () => {
  it('consulta pendientes desde el resultado sin enviar un turno y mantiene el estado parcial al recargar', async () => {
    detail.conversation.current_stage = 'ready'
    detail.latest_analysis_run = {
      id: 'run',
      proposal_id: 'pr1',
      status: 'partial',
    }
    detail.messages.push({
      id: 'result-event',
      position: 2,
      role: 'assistant',
      content: 'Resultado parcial',
      message_type: 'event',
      metadata: { analysis_run_id: 'run', proposal_id: 'pr1' },
    })
    vi.mocked(analysisService.get).mockResolvedValue({
      id: 'run',
      project_id: 'p1',
      proposal_id: 'pr1',
      status: 'partial',
      title: 'Análisis parcial',
      created_at: '2026-11-16',
      artifact_count: 0,
      result: {
        summary: 'Descriptivos calculados.',
        components: [],
        component_states: [],
        specification: { components: [] },
      },
      artifacts: [],
    } as unknown as AnalysisRun)
    const view = chat()
    await userEvent.click(
      await screen.findByRole('button', {
        name: 'Revisar componentes pendientes',
      }),
    )
    expect(
      screen.getByRole('region', {
        name: 'Revisión de componentes pendientes',
      }),
    ).toBeInTheDocument()
    expect(chatService.turn).not.toHaveBeenCalled()
    expect(analysisService.execute).not.toHaveBeenCalled()
    expect(
      screen.getByText('Análisis parcialmente completado'),
    ).toBeInTheDocument()
    view.unmount()
    chat()
    await screen.findByText('Análisis parcialmente completado')
    await userEvent.click(
      await screen.findByRole('button', {
        name: 'Revisar componentes pendientes',
      }),
    )
    expect(chatService.turn).not.toHaveBeenCalled()
  })
  it('sitúa la propuesta junto al mensaje persistido y conserva propuestas antiguas sin inventar su posición', async () => {
    detail.conversation.current_stage = 'proposal'
    detail.proposals = [
      { ...structuredClone(proposal), source_message_id: 'm1' },
      {
        ...structuredClone(proposal),
        id: 'legacy',
        title: 'Propuesta anterior',
      },
    ]
    detail.messages.push({
      id: 'm2',
      position: 2,
      role: 'user',
      content: 'Respuesta posterior',
      message_type: 'text',
      metadata: {},
    })
    chat()
    const card = await screen.findByRole('article', {
      name: 'Propuesta: Describir notas',
    })
    const before = screen.getByText(
      'Hola, puedo ayudarte a entender tus datos.',
    )
    const after = screen.getByText('Respuesta posterior')
    expect(
      before.compareDocumentPosition(card) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
    expect(
      card.compareDocumentPosition(after) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
    expect(
      screen.getByText('Propuestas anteriores sin posición registrada'),
    ).toBeInTheDocument()
    expect(document.querySelectorAll('.proposal-card li:empty')).toHaveLength(0)
  })
  it('prepara la propuesta aceptada en el mismo chat sin abrir el formulario técnico', async () => {
    detail.conversation.current_stage = 'ready'
    detail.proposals = [{ ...structuredClone(proposal), status: 'accepted' }]
    detail.files = [dataset]
    chat()
    await userEvent.click(
      await screen.findByRole('button', { name: 'Ejecutar análisis' }),
    )
    await waitFor(() => expect(chatService.turn).toHaveBeenCalledOnce())
    expect(vi.mocked(chatService.turn).mock.calls[0][2]).toMatchObject({
      action: 'prepare_execution',
      proposal_id: 'pr1',
    })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /Mensaje/ })).toBeInTheDocument()
  })
  it('bloquea el selector mientras prepara un análisis y lo recupera al terminar', async () => {
    detail.conversation.current_stage = 'ready'
    detail.proposals = [{ ...structuredClone(proposal), status: 'accepted' }]
    let finish!: (value: unknown) => void
    vi.mocked(chatService.turn).mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve
        }),
    )
    chat()
    await userEvent.click(
      await screen.findByRole('button', { name: 'Ejecutar análisis' }),
    )
    expect(
      screen.getByRole('combobox', { name: 'Proveedor del asistente' }),
    ).toBeDisabled()
    expect(vi.mocked(chatService.turn).mock.calls[0][2].action).toBe(
      'prepare_execution',
    )
    await act(async () => finish({ status: 'completed' }))
    await waitFor(() => expect(screen.getByRole('combobox')).toBeEnabled())
  })
  it('bloquea el selector durante el cálculo Python y conserva la preparación tras un error', async () => {
    detail.conversation.current_stage = 'ready'
    detail.proposals = [{ ...structuredClone(proposal), status: 'accepted' }]
    detail.conversation.stage_data.execution_preparation = {
      proposal_id: 'pr1',
      result: {
        request_id: 'calculo-sintetico',
        status: 'READY',
        fingerprint: 'huella-sintetica',
        methods: ['Descriptivos'],
        reasons: [],
        evidence: [],
        warnings: [],
        blockers: [],
        questions: [],
        files: [],
        specification: {
          schema_version: 1,
          decisions: [],
          filters: [],
          confidence_level: 0.95,
          alternative: 'two-sided',
          missing_policy: 'available_cases_per_procedure',
          multiplicity: 'none',
          decisions_confirmed: false,
          components: [
            {
              source_index: 0,
              method: 'descriptive',
              design: 'not_applicable',
              equal_variances_confirmed: false,
              group_values: [],
              posthoc: 'none',
              descriptive_intervals: false,
            },
          ],
        },
      },
    }
    let fail!: (error: Error) => void
    vi.mocked(analysisService.execute).mockImplementation(
      () =>
        new Promise((_resolve, reject) => {
          fail = reject
        }),
    )
    chat()
    const preparation = await screen.findByRole('article', {
      name: 'Preparación del análisis',
    })
    await userEvent.click(
      within(preparation).getByRole('button', { name: 'Ejecutar análisis' }),
    )
    expect(screen.getByRole('combobox')).toBeDisabled()
    expect(screen.getByText(/Python está calculando/)).toBeInTheDocument()
    await act(async () =>
      fail(new Error('Cálculo interrumpido para la prueba')),
    )
    await waitFor(() => expect(screen.getByRole('combobox')).toBeEnabled())
    expect(
      screen.getByRole('article', { name: 'Preparación del análisis' }),
    ).toHaveTextContent('Cálculo interrumpido para la prueba')
    expect(analysisService.execute).toHaveBeenCalledOnce()
  })
  it('distingue texto CSV de números inferidos y avisa sobre NA ambiguos', async () => {
    detail.files = [structuredClone(dataset)]
    const profile = detail.files[0].metadata.profile!
    profile.ambiguous_missing_count = 11
    profile.columns[0] = {
      ...profile.columns[0],
      source_representation: 'csv_text',
      inferred_type: 'numeric',
      statistical_type: 'quantitative',
      ambiguous_missing: { NA: 11 },
    }
    chat()
    const user = userEvent.setup()
    await user.click(await screen.findByText('mediciones.csv'))
    expect(screen.getByRole('table')).toHaveTextContent('Texto CSV')
    expect(screen.getByRole('table')).toHaveTextContent('Numérico')
    expect(screen.getByRole('table')).toHaveTextContent('Cuantitativa probable')
    expect(screen.getByRole('table')).toHaveTextContent('11 por confirmar')
    expect(screen.getByText(/posibles ausencias ambiguas/)).toBeInTheDocument()
  })

  it('permite seleccionar una entre varias propuestas sin decidir las restantes', async () => {
    detail.conversation.current_stage = 'proposal'
    detail.files = [dataset]
    detail.proposals = [
      structuredClone(proposal),
      { ...structuredClone(proposal), id: 'pr2', title: 'Comparar grupos' },
    ]
    vi.mocked(chatService.decide).mockImplementation(
      async (_project, _chat, id, status) => {
        detail.proposals = detail.proposals.map((item) =>
          item.id === id ? { ...item, status } : item,
        )
        return {}
      },
    )
    chat()
    const user = userEvent.setup()
    const choice = await screen.findByRole('article', {
      name: 'Propuesta: Comparar grupos',
    })
    await user.click(
      within(choice).getByRole('button', { name: 'Aceptar plan' }),
    )
    await waitFor(() =>
      expect(
        within(
          screen.getByRole('article', { name: 'Propuesta: Comparar grupos' }),
        ).getByText('PLAN ACEPTADO'),
      ).toBeInTheDocument(),
    )
    expect(
      within(
        screen.getByRole('article', { name: 'Propuesta: Describir notas' }),
      ).getByRole('button', { name: 'Aceptar plan' }),
    ).toBeEnabled()
    expect(chatService.decide).toHaveBeenCalledExactlyOnceWith(
      'p1',
      'c1',
      'pr2',
      'accepted',
    )
  })

  it('continúa la reutilización con No y oculta UUID de texto legado', async () => {
    const uuid = '20000000-0000-0000-0000-000000000001'
    detail.files = [{ ...dataset, id: uuid }]
    detail.conversation.stage_data.awaiting_reuse_update = true
    detail.messages[0].content = `Utilizaremos ${uuid}. ¿Deseas agregar información?`
    chat()
    const user = userEvent.setup()
    expect(
      await screen.findByText(
        'Utilizaremos mediciones.csv. ¿Deseas agregar información?',
      ),
    ).toBeInTheDocument()
    expect(screen.queryByText(new RegExp(uuid))).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'No, continuar' }))
    expect(chatService.turn).toHaveBeenCalledWith(
      'p1',
      'c1',
      expect.objectContaining({ action: 'message', content: 'No' }),
    )
    expect(chatService.create).not.toHaveBeenCalled()
  })

  it('presenta filtros, efecto definido y multiplicidad en la propuesta', async () => {
    detail.files = [dataset]
    detail.proposals = [structuredClone(proposal)]
    detail.proposals[0].analysis_plan.comparison = {
      design: 'independent',
      groups: ['male', 'female'],
      filters: [
        {
          variable: {
            file_id: 'f1',
            sheet: 'tabla',
            column: 'species',
            role: 'description',
          },
          values: ['Adelie'],
        },
      ],
      strata: null,
      independence: 'Verificar independencia',
      valid_observations: 'Informar n por grupo',
      missing_data:
        'Excluir ausencias solo del cálculo, sin borrar el original',
      outliers: 'Revisar atípicos',
      normality: 'Revisar Q-Q por grupo',
      variance_assumption: 'unequal_allowed',
      effect_size: {
        name: 'cohen_d',
        standardizer: 'pooled_sd',
        definition: 'd = diferencia de medias / SD combinada ponderada',
        correction: 'Considerar Hedges y su corrección',
        confidence_interval: 'Estimar intervalo de confianza en Sesión 03',
      },
      purpose: 'exploratory',
      multiplicity: 'none',
      multiplicity_reason: 'Un solo contraste en Adelie',
    }
    chat()
    const user = userEvent.setup()
    await user.click(
      await screen.findByText('Alcance y decisiones metodológicas'),
    )
    expect(screen.getByText(/species = Adelie/)).toBeInTheDocument()
    expect(screen.getByText(/SD combinada ponderada/)).toBeInTheDocument()
    expect(
      screen.getByText(/no se exige igualdad de varianzas/),
    ).toBeInTheDocument()
    expect(screen.getByText(/Un solo contraste en Adelie/)).toBeInTheDocument()
  })
  it('solicita una sola comprensión automática al terminar una carga múltiple', async () => {
    detail.conversation.current_stage = 'upload_dataset'
    vi.mocked(chatService.upload).mockImplementation(async () => {
      detail.files = [dataset]
      return dataset
    })
    chat()
    const user = userEvent.setup()
    await screen.findByLabelText('Mensaje para Statia')
    await user.upload(screen.getByLabelText('Archivos para adjuntar'), [
      new File(['a\n1'], 'a.csv', { type: 'text/csv' }),
      new File(['a\n2'], 'b.csv', { type: 'text/csv' }),
    ])
    await waitFor(() => expect(chatService.turn).toHaveBeenCalledOnce())
    expect(chatService.turn).toHaveBeenCalledWith(
      'p1',
      'c1',
      expect.objectContaining({ action: 'files_ready' }),
    )
  })
  it('crea una conversación, recupera historial y responde sobre instrumentos', async () => {
    vi.mocked(chatService.list).mockResolvedValueOnce([])
    vi.mocked(chatService.create).mockResolvedValue(detail.conversation)
    chat()
    const user = userEvent.setup()
    await user.click(
      await screen.findByRole('button', { name: 'Crear conversación' }),
    )
    expect(
      await screen.findByText('Hola, puedo ayudarte a entender tus datos.'),
    ).toBeInTheDocument()
    await user.click(
      screen.getByRole('button', { name: 'No tengo instrumento' }),
    )
    expect(chatService.turn).toHaveBeenCalledWith(
      'p1',
      'c1',
      expect.objectContaining({
        action: 'instrument_no',
        request_id: expect.any(String),
      }),
    )
  })

  it('conserva la clave de idempotencia al reintentar un fallo de Gemini', async () => {
    detail.conversation.current_stage = 'goal'
    vi.mocked(chatService.turn)
      .mockRejectedValueOnce(new ApiError('Falta habilitar Gemini.', 503))
      .mockResolvedValueOnce({ status: 'completed' })
    chat()
    const user = userEvent.setup()
    await user.type(
      await screen.findByLabelText('Mensaje para Statia'),
      'Quiero explorar mis datos',
    )
    await user.click(screen.getByRole('button', { name: 'Enviar' }))
    expect(
      await screen.findByText('Falta habilitar Gemini.'),
    ).toBeInTheDocument()
    await user.click(
      screen.getByRole('button', { name: 'Reintentar solicitud' }),
    )
    await waitFor(() => expect(chatService.turn).toHaveBeenCalledTimes(2))
    expect(vi.mocked(chatService.turn).mock.calls[0][2]).toEqual(
      vi.mocked(chatService.turn).mock.calls[1][2],
    )
  })

  it('renombra y exige confirmar antes de eliminar', async () => {
    chat()
    const user = userEvent.setup()
    await user.click(await screen.findByRole('button', { name: 'Renombrar' }))
    await user.clear(screen.getByLabelText('Título de la conversación'))
    await user.type(
      screen.getByLabelText('Título de la conversación'),
      'Mi objetivo',
    )
    await user.click(screen.getByRole('button', { name: 'Guardar título' }))
    await waitFor(() =>
      expect(chatService.rename).toHaveBeenCalledWith(
        'p1',
        'c1',
        'Mi objetivo',
      ),
    )
    await user.click(screen.getByRole('button', { name: /^Eliminar$/ }))
    expect(chatService.remove).not.toHaveBeenCalled()
    await user.click(
      screen.getByRole('button', { name: 'Confirmar eliminación' }),
    )
    await waitFor(() =>
      expect(chatService.remove).toHaveBeenCalledWith('p1', 'c1'),
    )
  })

  it('adjunta múltiples archivos y presenta el perfil y la selección de hoja', async () => {
    detail.conversation.current_stage = 'upload_dataset'
    detail.files = [
      dataset,
      {
        id: 'f2',
        original_name: 'libro.xlsx',
        file_type: 'xlsx',
        file_role: 'dataset',
        file_size: 100,
        metadata: {
          sheets: ['Pretest', 'Postest'],
          needs_sheet_selection: true,
        },
      },
    ]
    chat()
    const user = userEvent.setup()
    await screen.findByText('mediciones.csv')
    await user.click(screen.getByText('mediciones.csv'))
    expect(screen.getByRole('table')).toHaveTextContent('nota')
    expect(screen.getByText(/1 celdas ausentes/)).toBeInTheDocument()
    await user.click(screen.getByText('libro.xlsx'))
    await user.selectOptions(
      screen.getByLabelText('Hoja de libro.xlsx'),
      'Postest',
    )
    expect(chatService.sheet).toHaveBeenCalledWith('p1', 'f2', 'Postest')
    await waitFor(() =>
      expect(
        screen.getByRole('button', { name: 'Adjuntar archivos' }),
      ).toBeEnabled(),
    )
    await user.upload(screen.getByLabelText('Archivos para adjuntar'), [
      new File(['a\n1'], 'nuevo.csv', { type: 'text/csv' }),
      new File(['%PDF-'], 'instrumento.pdf', { type: 'application/pdf' }),
    ])
    await waitFor(() => expect(chatService.upload).toHaveBeenCalledTimes(2))
    expect(
      vi.mocked(chatService.upload).mock.calls.map((call) => call[3]),
    ).toEqual(['dataset', 'instrument'])
  })

  it('acepta un plan estructurado y muestra sus limitaciones', async () => {
    detail.conversation.current_stage = 'proposal'
    detail.files = [dataset]
    detail.proposals = [proposal]
    chat()
    const user = userEvent.setup()
    await user.click(await screen.findByText('Limitaciones'))
    expect(screen.getByText('Sin causalidad')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Aceptar plan' }))
    expect(chatService.decide).toHaveBeenCalledWith(
      'p1',
      'c1',
      'pr1',
      'accepted',
    )
  })

  it('ofrece reutilización y no crea otra conversación sin la acción del usuario', async () => {
    detail.conversation.current_stage = 'reuse'
    detail.conversation.stage_data = {
      reuse_file_ids: ['f1'],
      goal_change: {
        goal: 'Otra investigación',
        reason: 'Es una finalidad diferente.',
        title: null,
      },
    }
    vi.mocked(chatService.files).mockResolvedValue([dataset])
    vi.mocked(chatService.create).mockResolvedValue({
      ...detail.conversation,
      id: 'c2',
    })
    chat()
    const user = userEvent.setup()
    expect(await screen.findByText('mediciones.csv')).toBeInTheDocument()
    expect(chatService.create).not.toHaveBeenCalled()
    await user.click(
      screen.getByRole('button', { name: 'Reutilizar archivos' }),
    )
    expect(chatService.turn).toHaveBeenCalledWith(
      'p1',
      'c1',
      expect.objectContaining({ action: 'reuse' }),
    )
    await waitFor(() =>
      expect(
        screen.getByRole('button', {
          name: 'Crear chat para la nueva finalidad',
        }),
      ).toBeEnabled(),
    )
    await user.click(
      screen.getByRole('button', {
        name: 'Crear chat para la nueva finalidad',
      }),
    )
    expect(chatService.create).toHaveBeenCalledTimes(1)
  })

  it('recupera un turno fallido al abrir el historial e informa sesión vencida', async () => {
    detail.retry_turn = {
      request_id: 'request-previo',
      content: 'Explorar',
      action: 'message',
      file_ids: [],
      share_samples: false,
      share_instrument_text: false,
    }
    vi.mocked(chatService.turn).mockRejectedValue(
      new ApiError('Tu sesión venció.', 401),
    )
    chat()
    const user = userEvent.setup()
    await user.click(
      await screen.findByRole('button', { name: 'Reintentar solicitud' }),
    )
    expect(
      await screen.findByRole('link', { name: 'Recuperar acceso' }),
    ).toBeInTheDocument()
    expect(chatService.turn).toHaveBeenCalledWith('p1', 'c1', detail.retry_turn)
  })
})

describe('compositor y navegación accesibles', () => {
  it('recupera la altura compacta tras cambiar el ancho sin perder el borrador ni enviar', async () => {
    let notify!: (width: number) => void
    vi.stubGlobal(
      'ResizeObserver',
      class implements ResizeObserver {
        callback: ResizeObserverCallback
        constructor(callback: ResizeObserverCallback) {
          this.callback = callback
        }
        observe(target: Element) {
          if (target instanceof HTMLTextAreaElement) {
            notify = (width) =>
              this.callback(
                [
                  {
                    target,
                    contentRect: new DOMRect(0, 0, width, 0),
                    borderBoxSize: [],
                    contentBoxSize: [],
                    devicePixelContentBoxSize: [],
                  },
                ],
                this,
              )
          }
        }
        disconnect() {}
        unobserve() {}
      },
    )
    const view = chat()
    try {
      const input = await screen.findByRole('textbox', {
        name: 'Mensaje para Statia',
      })
      await userEvent.type(input, 'Borrador conservado')
      let height = 158
      Object.defineProperty(input, 'scrollHeight', {
        configurable: true,
        get: () => height,
      })
      act(() => notify(80))
      await waitFor(() => expect(input).toHaveStyle({ height: '160px' }))
      // El panel termina de redistribuirse sin otro evento de ventana.
      height = 43
      act(() => notify(264))
      await waitFor(() => expect(input).toHaveStyle({ height: '45px' }))
      expect(input).toHaveValue('Borrador conservado')
      expect(chatService.turn).not.toHaveBeenCalled()
    } finally {
      view.unmount()
      vi.unstubAllGlobals()
    }
  })
  it('Enter envía una sola vez, conserva el foco y bloquea envíos durante la solicitud', async () => {
    let finish!: (value: { status: string }) => void
    vi.mocked(chatService.turn).mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve
        }),
    )
    chat()
    const user = userEvent.setup()
    const input = await screen.findByRole('textbox', {
      name: 'Mensaje para Statia',
    })
    await user.type(input, 'Quiero explorar los datos{Enter}{Enter}')
    expect(chatService.turn).toHaveBeenCalledTimes(1)
    expect(chatService.turn).toHaveBeenCalledWith(
      'p1',
      'c1',
      expect.objectContaining({
        content: 'Quiero explorar los datos',
        action: 'message',
      }),
    )
    expect(input).toBeDisabled()
    expect(screen.getByRole('status')).toHaveTextContent(
      'preparando una respuesta',
    )
    finish({ status: 'completed' })
    await waitFor(() => expect(input).toBeEnabled())
    expect(input).toHaveValue('')
    expect(input).toHaveFocus()
  })

  it('Shift + Enter inserta una línea y no envía; el clic envía el texto multilínea', async () => {
    chat()
    const user = userEvent.setup()
    const input = await screen.findByRole('textbox', {
      name: 'Mensaje para Statia',
    })
    await user.type(input, 'Primera línea{Shift>}{Enter}{/Shift}Segunda línea')
    expect(input).toHaveValue('Primera línea\nSegunda línea')
    expect(chatService.turn).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Enviar' }))
    expect(chatService.turn).toHaveBeenCalledWith(
      'p1',
      'c1',
      expect.objectContaining({ content: 'Primera línea\nSegunda línea' }),
    )
  })

  it('ignora Enter durante IME, native isComposing y keyCode 229', async () => {
    chat()
    const input = await screen.findByRole('textbox', {
      name: 'Mensaje para Statia',
    })
    fireEvent.change(input, { target: { value: '解析' } })
    fireEvent.compositionStart(input)
    fireEvent.keyDown(input, { key: 'Enter', code: 'Enter' })
    fireEvent.compositionEnd(input)
    fireEvent.keyDown(input, { key: 'Enter', isComposing: true })
    fireEvent.keyDown(input, { key: 'Enter', keyCode: 229 })
    expect(chatService.turn).not.toHaveBeenCalled()
    fireEvent.keyDown(input, { key: 'Enter' })
    await waitFor(() => expect(chatService.turn).toHaveBeenCalledTimes(1))
  })

  it('no envía mensajes vacíos y ofrece adjuntar con etiqueta accesible', async () => {
    chat()
    const user = userEvent.setup()
    await user.type(
      await screen.findByRole('textbox', { name: 'Mensaje para Statia' }),
      '   {Enter}',
    )
    expect(screen.getByRole('button', { name: 'Enviar' })).toBeDisabled()
    expect(chatService.turn).not.toHaveBeenCalled()
    expect(
      screen.getByRole('button', { name: 'Adjuntar archivos' }),
    ).toBeEnabled()
    expect(screen.getByText(/Enter envía/)).toBeInTheDocument()
  })

  it('oculta y recupera el historial sin recargar, perder el borrador ni el reintento', async () => {
    chat()
    const user = userEvent.setup()
    const input = await screen.findByLabelText('Mensaje para Statia')
    await user.type(input, 'Un borrador')
    await user.click(screen.getByRole('button', { name: 'Ocultar historial' }))
    expect(
      screen.getByRole('button', { name: 'Mostrar historial' }),
    ).toHaveAttribute('aria-expanded', 'false')
    expect(
      screen.queryByRole('navigation', { name: 'Conversaciones' }),
    ).not.toBeInTheDocument()
    expect(input).toHaveValue('Un borrador')
    await user.click(screen.getByRole('button', { name: 'Mostrar historial' }))
    expect(
      screen.getByRole('button', { name: 'Ocultar historial' }),
    ).toHaveAttribute('aria-expanded', 'true')
    expect(chatService.get).toHaveBeenCalledTimes(1)
    vi.mocked(chatService.turn).mockRejectedValueOnce(
      new ApiError('Error recuperable', 503),
    )
    await user.keyboard('{Tab}')
    await user.click(screen.getByRole('button', { name: 'Enviar' }))
    await screen.findByText('Error recuperable')
    await user.click(screen.getByRole('button', { name: 'Ocultar historial' }))
    expect(
      screen.getByRole('button', { name: 'Reintentar solicitud' }),
    ).toBeEnabled()
  })

  it('muestra el título completo en el nombre accesible y selecciona otra conversación', async () => {
    const longTitle =
      'Análisis exploratorio de mediciones y comparación de grupos con un título deliberadamente muy largo para el historial'
    const second = { ...detail.conversation, id: 'c2', title: longTitle }
    vi.mocked(chatService.list).mockResolvedValue([detail.conversation, second])
    vi.mocked(chatService.get).mockImplementation(async (_project, id) => ({
      ...structuredClone(detail),
      conversation: id === 'c2' ? second : detail.conversation,
    }))
    chat()
    const user = userEvent.setup()
    const item = await screen.findByRole('button', {
      name: `Abrir conversación: ${longTitle}`,
    })
    expect(item).toHaveAttribute('title', longTitle)
    await user.click(item)
    await waitFor(() =>
      expect(
        screen.getByRole('heading', { name: longTitle }),
      ).toBeInTheDocument(),
    )
    expect(item).toHaveAttribute('aria-current', 'page')
    expect(chatService.get).toHaveBeenCalledWith('p1', 'c2')
  })

  it('en móvil usa un diálogo temporal, cierra al seleccionar y conserva el chat', async () => {
    vi.mocked(window.matchMedia).mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as unknown as MediaQueryList)
    chat()
    const user = userEvent.setup()
    await screen.findByLabelText('Mensaje para Statia')
    expect(
      screen.queryByRole('navigation', { name: 'Conversaciones' }),
    ).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Mostrar historial' }))
    expect(
      screen.getByRole('dialog', { name: 'Historial de conversaciones' }),
    ).toBeInTheDocument()
    await user.click(
      screen.getByRole('button', {
        name: 'Abrir conversación: Nueva conversación',
      }),
    )
    await waitFor(() =>
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument(),
    )
    expect(
      await screen.findByLabelText('Mensaje para Statia'),
    ).toBeInTheDocument()
  })
})

it('muestra la etapa actual de aclaración en presencia de una ejecución histórica completada', async () => {
  detail.conversation.current_stage = 'clarification'
  detail.latest_analysis_run = {
    id: 'historico',
    proposal_id: 'anterior',
    status: 'completed',
  }
  chat()
  expect((await screen.findAllByText('Aclaraciones')).length).toBeGreaterThan(0)
  expect(screen.queryByText('Análisis completado')).not.toBeInTheDocument()
})

it('un plan recién aceptado conserva su estado aunque exista una ejecución anterior de otro plan', async () => {
  detail.conversation.current_stage = 'ready'
  detail.latest_analysis_run = {
    id: 'historico',
    proposal_id: 'anterior',
    status: 'completed',
  }
  detail.messages.push({
    id: 'decision',
    position: 2,
    role: 'system',
    content: 'Plan aceptado.',
    message_type: 'event',
    metadata: { proposal_id: 'nuevo', status: 'accepted' },
  })
  chat()
  expect((await screen.findAllByText('Plan aceptado')).length).toBeGreaterThan(
    0,
  )
  expect(screen.queryByText('Análisis completado')).not.toBeInTheDocument()
})
