import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { StatisticalChat } from '../components/StatisticalChat'
import { messageProvenance } from '../lib/assistant-provider'
import type {
  AssistantProviderCatalog,
  ConversationDetail,
  Message,
  Turn,
} from '../types/chat'
import type { Project } from '../types/project'

// API real del frontend y HTTP controlado: ninguna salida a servicios remotos.
vi.mock('../lib/supabase', () => ({
  getSupabase: () => ({
    auth: {
      getSession: async () => ({
        data: { session: { access_token: 'sesion-sintetica' } },
        error: null,
      }),
    },
  }),
}))

const project = {
  id: 'p1',
  name: 'Proyecto de prueba',
  project_type: 'general',
} as Project
let catalog: AssistantProviderCatalog
let chats: ConversationDetail[]
let patchStatus: number
let createStatus: number
let turnStatus: number
let catalogStatus: number
let hold: Promise<void> | null
let fetcher: ReturnType<typeof vi.fn<typeof fetch>>
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
function fixture(
  id = 'c1',
  provider: 'gemini' | 'openai' = 'gemini',
): ConversationDetail {
  return {
    conversation: {
      id,
      assistant_provider: provider,
      project_id: 'p1',
      title: `Conversación ${id}`,
      primary_goal: null,
      current_stage: 'goal',
      updated_at: '',
      stage_data: {},
    },
    files: [],
    proposals: [],
    messages: [
      {
        id: `m-${id}`,
        position: 1,
        role: 'assistant',
        content: 'Respuesta anterior',
        message_type: 'text',
        metadata: {
          generation: { provider: 'gemini', model: 'gemini-historico' },
        },
      },
    ],
  }
}
const retry: Turn = {
  request_id: '00000000-0000-4000-8000-000000000001',
  action: 'message',
  content: 'Consulta original',
  file_ids: [],
  share_samples: true,
  share_instrument_text: false,
}
beforeEach(() => {
  catalog = {
    default: 'gemini',
    providers: [
      {
        id: 'gemini',
        name: 'Gemini',
        model: 'gemini-catalogo',
        enabled: true,
        configured: true,
        experimental: false,
      },
      {
        id: 'openai',
        name: 'Terra (OpenAI)',
        model: 'gpt-6.1-terra',
        enabled: true,
        configured: true,
        experimental: true,
      },
    ],
  }
  chats = [fixture()]
  patchStatus = createStatus = turnStatus = catalogStatus = 200
  hold = null
  vi.mocked(window.matchMedia).mockReturnValue({
    matches: false,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  } as unknown as MediaQueryList)
  fetcher = vi.fn<typeof fetch>(async (url, init) => {
    const path = new URL(String(url)).pathname
    const method = init?.method || 'GET'
    if (path.endsWith('/assistant-providers')) {
      if (hold) await hold
      return catalogStatus === 200
        ? json(catalog)
        : json({ detail: 'Catálogo no disponible' }, catalogStatus)
    }
    if (path.endsWith('/files')) return json([])
    if (path.endsWith('/conversations') && method === 'GET')
      return json(chats.map((item) => item.conversation))
    const body = init?.body ? JSON.parse(String(init.body)) : {}
    if (path.endsWith('/conversations') && method === 'POST') {
      if (createStatus !== 200)
        return json(
          { detail: 'No se pudo crear la conversación.' },
          createStatus,
        )
      const next = fixture(`c${chats.length + 1}`, body.provider || 'gemini')
      chats.push(next)
      return json(next.conversation, 201)
    }
    const id = path.split('/conversations/')[1]?.split('/')[0]
    const current = chats.find((item) => item.conversation.id === id)
    if (current && path.endsWith('/provider') && method === 'PATCH') {
      if (patchStatus !== 200)
        return json(
          { detail: 'Cambio rechazado por el servidor.' },
          patchStatus,
        )
      current.conversation.assistant_provider = body.provider
      current.messages.push({
        id: `event-${current.messages.length}`,
        position: current.messages.length + 1,
        role: 'system',
        message_type: 'event',
        content: 'El proveedor cambió.',
        metadata: { event: 'provider_selected', source: 'deterministic' },
      })
      return json(current.conversation)
    }
    if (current && path.endsWith('/turns') && method === 'POST') {
      if (turnStatus !== 200) {
        current.retry_turn = body
        return json(
          {
            detail:
              turnStatus === 409
                ? 'El reintento pertenece a otra configuración.'
                : 'Proveedor no disponible.',
          },
          turnStatus,
        )
      }
      current.retry_turn = null
      return json({ status: 'completed' })
    }
    if (current && method === 'GET') return json(current)
    throw new Error(`HTTP no previsto: ${method} ${path}`)
  })
  vi.stubGlobal('fetch', fetcher)
})
afterEach(() => vi.unstubAllGlobals())
function mount() {
  return render(
    <MemoryRouter>
      <StatisticalChat project={project} />
    </MemoryRouter>,
  )
}
async function ready() {
  const select = await screen.findByRole('combobox', {
    name: 'Proveedor del asistente',
  })
  await waitFor(() =>
    expect(select).toHaveValue(chats[0].conversation.assistant_provider),
  )
  return select
}
function requests(suffix: string, method = 'POST') {
  return fetcher.mock.calls.filter(
    ([url, init]) => String(url).endsWith(suffix) && init?.method === method,
  )
}
async function choose(provider: 'gemini' | 'openai') {
  await userEvent.selectOptions(
    screen.getByRole('combobox', { name: 'Proveedor del asistente' }),
    provider,
  )
}
async function confirm() {
  await userEvent.click(
    screen.getByRole('button', { name: /^Confirmar cambio a/ }),
  )
}

describe('selector multiproveedor con HTTP controlado', () => {
  it('carga catálogo, modelo y Gemini confirmado por defecto', async () => {
    mount()
    expect(await ready()).toHaveValue('gemini')
    expect(
      screen.getByRole('option', {
        name: /Terra.*Experimental.*gpt-6.1-terra.*Disponible/,
      }),
    ).toBeEnabled()
    expect(screen.getByText('gemini-catalogo · Disponible')).toBeInTheDocument()
    expect(
      fetcher.mock.calls.some(([url]) =>
        String(url).endsWith('/projects/p1/assistant-providers'),
      ),
    ).toBe(true)
    expect(requests('/turns')).toHaveLength(0)
  })
  it.each(['enabled', 'configured'] as const)(
    'Terra no es seleccionable con %s=false',
    async (field) => {
      catalog.providers[1][field] = false
      mount()
      const select = await ready()
      const option = screen.getByRole('option', { name: /Terra/ })
      expect(option).toBeDisabled()
      expect(option).toHaveTextContent(
        field === 'enabled' ? 'Deshabilitado' : 'No configurado',
      )
      await userEvent.selectOptions(select, 'openai')
      expect(select).toHaveValue('gemini')
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
      expect(requests('/provider', 'PATCH')).toHaveLength(0)
    },
  )
  it('muestra carga sin bloquear el historial y sin inventar disponibilidad', async () => {
    let release!: () => void
    hold = new Promise((resolve) => {
      release = resolve
    })
    mount()
    expect(await ready()).toBeDisabled()
    expect(screen.getByText('Cargando proveedores…')).toBeInTheDocument()
    expect(
      screen.queryByRole('option', { name: /Terra/ }),
    ).not.toBeInTheDocument()
    await act(async () => release())
    await waitFor(() => expect(screen.getByRole('combobox')).toBeEnabled())
  })
  it('recupera un fallo de catálogo con un reintento explícito', async () => {
    catalogStatus = 503
    mount()
    expect(await ready()).toBeDisabled()
    await screen.findByText(
      'No se pudo consultar la disponibilidad de proveedores.',
    )
    catalogStatus = 200
    await userEvent.click(
      screen.getByRole('button', { name: 'Recargar proveedores' }),
    )
    await waitFor(() => expect(screen.getByRole('combobox')).toBeEnabled())
  })
  it.each([
    ['gemini', 'openai'],
    ['openai', 'gemini'],
  ] as const)(
    'confirma %s → %s y usa expected_provider confirmado',
    async (from, to) => {
      chats[0].conversation.assistant_provider = from
      mount()
      const select = await ready()
      await choose(to)
      const dialog = screen.getByRole('dialog', {
        name: 'Cambiar proveedor del asistente',
      })
      expect(dialog).toHaveTextContent(
        'historial anterior, perfiles de datasets, Contexto de tesis y resultados agregados',
      )
      expect(dialog).toHaveTextContent('muestras pequeñas y extractos PDF')
      expect(select).toHaveValue(from)
      expect(requests('/provider', 'PATCH')).toHaveLength(0)
      await confirm()
      await waitFor(() => expect(select).toHaveValue(to))
      const [, init] = requests('/provider', 'PATCH')[0]
      expect(JSON.parse(String(init?.body))).toEqual({
        provider: to,
        expected_provider: from,
      })
      expect(
        await screen.findByText('Cambio de proveedor · Statia'),
      ).toBeInTheDocument()
      expect(screen.getByText('Gemini — gemini-historico')).toBeInTheDocument()
      expect(requests('/turns')).toHaveLength(0)
    },
  )
  it('cancela sin PATCH y permite usar el selector por teclado', async () => {
    mount()
    const select = await ready()
    select.focus()
    expect(select).toHaveFocus()
    await choose('openai')
    await userEvent.click(
      screen.getByRole('button', { name: 'Cancelar cambio' }),
    )
    expect(select).toHaveValue('gemini')
    expect(select).toHaveFocus()
    expect(requests('/provider', 'PATCH')).toHaveLength(0)
  })
  it('un fallo de cambio mantiene el valor confirmado y permite cancelar', async () => {
    patchStatus = 503
    mount()
    const select = await ready()
    await choose('openai')
    await confirm()
    await screen.findByText('Cambio rechazado por el servidor.')
    expect(select).toHaveValue('gemini')
    expect(screen.getByRole('dialog')).toHaveTextContent(
      'Cambio rechazado por el servidor.',
    )
    await userEvent.click(
      screen.getByRole('button', { name: 'Cancelar cambio' }),
    )
    expect(select).toHaveValue('gemini')
  })
  it('409 recarga la conversación y explica el cambio de selección', async () => {
    patchStatus = 409
    mount()
    const select = await ready()
    await choose('openai')
    chats[0].conversation.assistant_provider = 'openai' // Otro cliente ganó el cambio.
    await confirm()
    await screen.findByText(/Se recargó la conversación/)
    expect(select).toHaveValue('openai')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(
      fetcher.mock.calls.filter(([url]) =>
        String(url).endsWith('/conversations/c1'),
      ).length,
    ).toBe(2)
  })
  it('no permite enviar con una selección incierta si se pierde la respuesta del cambio', async () => {
    mount()
    const select = await ready()
    await choose('openai')
    const original = fetcher.getMockImplementation()!
    fetcher.mockImplementation(async (url, init) => {
      if (String(url).endsWith('/provider')) {
        chats[0].conversation.assistant_provider = 'openai'
        throw new TypeError('Respuesta perdida después de persistir')
      }
      return original(url, init)
    })
    await confirm()
    await screen.findByText(/No se pudo confirmar el cambio de proveedor/)
    expect(select).toHaveValue('gemini')
    expect(select).toBeDisabled()
    expect(screen.getByLabelText('Mensaje para Statia')).toBeDisabled()
    await userEvent.click(screen.getByRole('button', { name: 'Recargar' }))
    await waitFor(() => expect(select).toHaveValue('openai'))
    expect(select).toBeEnabled()
    expect(requests('/turns')).toHaveLength(0)
  })
  it('si falla la recarga tras 409 bloquea envíos hasta recuperar el estado confirmado', async () => {
    patchStatus = 409
    mount()
    const select = await ready()
    await choose('openai')
    const original = fetcher.getMockImplementation()!
    let failGet = true
    fetcher.mockImplementation(async (url, init) => {
      if (failGet && String(url).endsWith('/conversations/c1'))
        return json({ detail: 'Sin conexión' }, 503)
      return original(url, init)
    })
    await confirm()
    await screen.findByText(/No se pudo recuperar el estado/)
    expect(select).toBeDisabled()
    expect(screen.getByLabelText('Mensaje para Statia')).toBeDisabled()
    failGet = false
    chats[0].conversation.assistant_provider = 'openai'
    await userEvent.click(screen.getByRole('button', { name: 'Recargar' }))
    await waitFor(() => expect(select).toHaveValue('openai'))
    expect(select).toBeEnabled()
    expect(screen.getByLabelText('Mensaje para Statia')).toBeEnabled()
  })
  it.each(['active_request', 'running_analysis', 'failed_turn'] as const)(
    'bloquea selección con %s',
    async (operation) => {
      if (operation === 'active_request')
        chats[0].conversation.active_request_id = retry.request_id
      if (operation === 'running_analysis')
        chats[0].latest_analysis_run = {
          id: 'run',
          proposal_id: 'pr',
          status: 'running',
        }
      if (operation === 'failed_turn') chats[0].retry_turn = retry
      mount()
      expect(await ready()).toBeDisabled()
    },
  )
  it('bloquea selección durante un turno local y permite después del éxito', async () => {
    mount()
    const select = await ready()
    const original = fetcher.getMockImplementation()!
    let release!: () => void
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    fetcher.mockImplementation(async (url, init) => {
      if (String(url).endsWith('/turns')) await gate
      return original(url, init)
    })
    await userEvent.type(
      screen.getByLabelText('Mensaje para Statia'),
      'Explorar',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Enviar' }))
    expect(select).toBeDisabled()
    await act(async () => release())
    await waitFor(() => expect(select).toBeEnabled())
  })
  it('recupera Terra al recargar y restaura cada conversación al navegar', async () => {
    chats = [fixture('c1', 'openai'), fixture('c2', 'gemini')]
    const view = mount()
    expect(await ready()).toHaveValue('openai')
    await userEvent.click(
      screen.getByRole('button', {
        name: 'Abrir conversación: Conversación c2',
      }),
    )
    await waitFor(() =>
      expect(screen.getByRole('combobox')).toHaveValue('gemini'),
    )
    await userEvent.click(
      screen.getByRole('button', {
        name: 'Abrir conversación: Conversación c1',
      }),
    )
    await waitFor(() =>
      expect(screen.getByRole('combobox')).toHaveValue('openai'),
    )
    view.unmount()
    mount()
    expect(await ready()).toHaveValue('openai')
  })
  it('conserva UUID y conflicto del reintento; otra solicitud explícita obtiene otro UUID', async () => {
    chats[0].conversation.assistant_provider = 'openai'
    chats[0].retry_turn = retry // Fallo anterior de Gemini o de otro modelo, sin snapshot HTTP.
    turnStatus = 409
    mount()
    await ready()
    await userEvent.click(
      screen.getByRole('button', { name: 'Reintentar solicitud' }),
    )
    await screen.findByText(/El reintento está en conflicto/)
    expect(JSON.parse(String(requests('/turns')[0][1]?.body))).toEqual(retry)
    expect(requests('/turns')).toHaveLength(1)
    expect(screen.getByRole('combobox')).toBeDisabled()
    await userEvent.click(
      screen.getByRole('button', { name: 'Escribir otra solicitud' }),
    )
    turnStatus = 200
    await userEvent.type(
      screen.getByLabelText('Mensaje para Statia'),
      'Nueva consulta explícita',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Enviar' }))
    await waitFor(() => expect(requests('/turns')).toHaveLength(2))
    const next = JSON.parse(String(requests('/turns')[1][1]?.body)) as Turn
    expect(next.request_id).not.toBe(retry.request_id)
    expect(next.content).toBe('Nueva consulta explícita')
    expect(requests('/provider', 'PATCH')).toHaveLength(0)
  })
  it('no hace fallback ni reintentos automáticos de un fallo de proveedor', async () => {
    turnStatus = 503
    mount()
    await ready()
    await userEvent.type(
      screen.getByLabelText('Mensaje para Statia'),
      'Explorar',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Enviar' }))
    await screen.findByText('Proveedor no disponible.')
    expect(requests('/turns')).toHaveLength(1)
    expect(requests('/provider', 'PATCH')).toHaveLength(0)
  })
  it('creación rápida Gemini incluso sin clave ni catálogo', async () => {
    catalogStatus = 503
    catalog.providers[0].configured = false
    mount()
    await ready()
    await userEvent.click(screen.getByRole('button', { name: 'Nuevo chat' }))
    await screen.findByRole('heading', { name: 'Conversación c2' })
    expect(JSON.parse(String(requests('/conversations')[0][1]?.body))).toEqual({
      provider: 'gemini',
    })
    expect(requests('/turns')).toHaveLength(0)
  })
  it('crear Terra exige elección y confirmación informada y no envía un turno', async () => {
    mount()
    await ready()
    await userEvent.click(
      screen.getByRole('button', { name: 'Elegir proveedor para nuevo chat' }),
    )
    const dialog = screen.getByRole('dialog', {
      name: 'Nueva conversación · proveedor',
    })
    const select = within(dialog).getByRole('combobox')
    expect(select).toHaveValue('gemini')
    await userEvent.selectOptions(select, 'openai')
    expect(dialog).toHaveTextContent('Terra es experimental')
    expect(dialog).toHaveTextContent(
      'historial anterior, perfiles de datasets, Contexto de tesis y resultados agregados',
    )
    expect(requests('/conversations')).toHaveLength(0)
    await userEvent.click(
      within(dialog).getByRole('button', {
        name: 'Confirmar y crear con Terra (OpenAI)',
      }),
    )
    await screen.findByRole('heading', { name: 'Conversación c2' })
    expect(screen.getByRole('combobox')).toHaveValue('openai')
    expect(JSON.parse(String(requests('/conversations')[0][1]?.body))).toEqual({
      provider: 'openai',
    })
    expect(requests('/turns')).toHaveLength(0)
  })
  it('cancelar la creación no crea chats y un fallo no muestra uno inexistente', async () => {
    createStatus = 503
    mount()
    await ready()
    await userEvent.click(
      screen.getByRole('button', { name: 'Elegir proveedor para nuevo chat' }),
    )
    await userEvent.click(
      screen.getByRole('button', { name: 'Cancelar creación' }),
    )
    expect(requests('/conversations')).toHaveLength(0)
    await userEvent.click(screen.getByRole('button', { name: 'Nuevo chat' }))
    await screen.findByText('No se pudo crear la conversación.')
    expect(
      screen.getByRole('heading', { name: 'Conversación c1' }),
    ).toBeInTheDocument()
    expect(screen.queryByText('Conversación c2')).not.toBeInTheDocument()
  })
  it('un fallo al crear Terra permanece visible dentro del diálogo sin chat inexistente', async () => {
    createStatus = 503
    mount()
    await ready()
    await userEvent.click(
      screen.getByRole('button', { name: 'Elegir proveedor para nuevo chat' }),
    )
    const dialog = screen.getByRole('dialog')
    await userEvent.selectOptions(
      within(dialog).getByRole('combobox'),
      'openai',
    )
    await userEvent.click(
      within(dialog).getByRole('button', {
        name: 'Confirmar y crear con Terra (OpenAI)',
      }),
    )
    await within(dialog).findByText('No se pudo crear la conversación.')
    expect(
      screen.getByRole('heading', { name: 'Conversación c1' }),
    ).toBeInTheDocument()
    expect(chats).toHaveLength(1)
    expect(requests('/turns')).toHaveLength(0)
  })
  it('una nueva finalidad desde Terra crea Gemini sin herencia silenciosa', async () => {
    chats[0].conversation.assistant_provider = 'openai'
    chats[0].conversation.stage_data.goal_change = {
      goal: 'Otro objetivo',
      reason: 'Nueva finalidad',
      title: null,
    }
    mount()
    await ready()
    await userEvent.click(
      screen.getByRole('button', {
        name: 'Crear chat para la nueva finalidad',
      }),
    )
    await screen.findByRole('heading', { name: 'Conversación c2' })
    expect(JSON.parse(String(requests('/conversations')[0][1]?.body))).toEqual({
      provider: 'gemini',
      source_conversation_id: 'c1',
    })
    expect(screen.getByRole('combobox')).toHaveValue('gemini')
  })
  it('conserva controles de muestras/PDF y los envía realmente al cambiar proveedor', async () => {
    mount()
    await ready()
    await userEvent.click(screen.getByText('Información compartida con Gemini'))
    await userEvent.click(
      screen.getByRole('checkbox', { name: /Compartir muestras/ }),
    )
    await userEvent.click(
      screen.getByRole('checkbox', { name: /Compartir extractos/ }),
    )
    await choose('openai')
    await confirm()
    await screen.findByText('Información compartida con Terra (OpenAI)')
    expect(
      screen.getByRole('checkbox', { name: /Compartir muestras/ }),
    ).toBeChecked()
    expect(
      screen.getByRole('checkbox', { name: /Compartir extractos/ }),
    ).toBeChecked()
    expect(
      screen.getByText(/Evita información personal o secretos/),
    ).toBeInTheDocument()
    await userEvent.type(
      screen.getByLabelText('Mensaje para Statia'),
      'Interpretar',
    )
    await userEvent.click(screen.getByRole('button', { name: 'Enviar' }))
    await waitFor(() => expect(requests('/turns')).toHaveLength(1))
    expect(JSON.parse(String(requests('/turns')[0][1]?.body))).toMatchObject({
      share_samples: true,
      share_instrument_text: true,
    })
  })
  it('mantiene el selector etiquetado y la confirmación en vista móvil', async () => {
    vi.mocked(window.matchMedia).mockReturnValue({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    } as unknown as MediaQueryList)
    mount()
    await ready()
    expect(
      screen.queryByRole('navigation', { name: 'Conversaciones' }),
    ).not.toBeInTheDocument()
    await choose('openai')
    expect(
      screen.getByRole('dialog', { name: 'Cambiar proveedor del asistente' }),
    ).toBeInTheDocument()
    await userEvent.click(
      screen.getByRole('button', { name: 'Cancelar cambio' }),
    )
    expect(screen.getByRole('combobox')).toHaveAccessibleName(
      'Proveedor del asistente',
    )
  })
})

describe('procedencia histórica independiente de la selección', () => {
  it.each([
    [
      {
        generation: { provider: 'gemini', model: 'modelo-antiguo' },
        selected_provider: 'openai',
      },
      'Gemini — modelo-antiguo',
    ],
    [
      { generation: { provider: 'openai', model: 'gpt-6.1-terra' } },
      'Terra — gpt-6.1-terra',
    ],
    [
      { generation: { provider: 'gemini', model: null } },
      'Gemini — modelo histórico no registrado',
    ],
    [
      { generation: { source: 'deterministic' }, selected_provider: 'openai' },
      'Acción determinista de Statia',
    ],
    [{ selected_provider: 'openai' }, 'Modelo histórico no registrado'],
    [{}, 'Modelo histórico no registrado'],
    [
      { event: 'provider_selected', source: 'deterministic' },
      'Cambio de proveedor · Statia',
    ],
  ] as const)('usa únicamente metadata acreditada: %j', (metadata, label) => {
    const message: Message = {
      id: 'm',
      role: 'assistant',
      position: 1,
      content: '',
      message_type: 'text',
      metadata,
    }
    expect(messageProvenance(message)).toBe(label)
  })
  it('lee generation superior, distingue eventos y no atribuye mensajes del usuario', () => {
    const message = fixture().messages[0]
    message.metadata = {}
    message.generation = { provider: 'openai', model: 'modelo-registrado' }
    expect(messageProvenance(message)).toBe('Terra — modelo-registrado')
    message.message_type = 'event'
    expect(messageProvenance(message)).toBe('Evento de Statia')
    message.role = 'user'
    expect(messageProvenance(message)).toBeNull()
  })
})
