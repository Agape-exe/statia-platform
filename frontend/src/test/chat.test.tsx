import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { StatisticalChat } from '../components/StatisticalChat'
import { chatService } from '../services/chat'
import { ApiError } from '../lib/api'
import type { ConversationDetail, ProjectFile, Proposal } from '../types/chat'
import type { Project } from '../types/project'

vi.mock('../services/chat', () => ({
  chatService: {
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
