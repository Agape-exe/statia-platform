import { beforeEach, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'
import { ProjectData } from '../components/ProjectData'
import { AnalysisResults } from '../components/AnalysisResults'
import { AnalysisResultCard } from '../components/AnalysisResultCard'
import { chatService } from '../services/chat'
import { analysisService } from '../services/analysis'
import { visibleChatText } from '../lib/chat-text'
import type { ProjectFile } from '../types/chat'
import type { AnalysisRun } from '../types/analysis'

vi.mock('../services/chat', () => ({
  chatService: {
    files: vi.fn(),
    rows: vi.fn(),
    list: vi.fn(),
    profile: vi.fn(),
    download: vi.fn(),
  },
}))
vi.mock('../services/analysis', () => ({
  analysisService: { get: vi.fn(), list: vi.fn(), downloadZip: vi.fn() },
}))

const dataset: ProjectFile = {
  id: 'csv',
  original_name: 'original.csv',
  file_type: 'csv',
  file_role: 'dataset',
  file_size: 1234,
  metadata: { sheets: [] },
}
const run = {
  id: 'run',
  title: 'Descripción guardada',
  conversation_id: 'chat',
  status: 'completed',
  created_at: '2026-11-18',
  methods: ['Descriptiva'],
  artifact_count: 1,
  artifacts: [],
  result: {
    summary: 'Solo descripción.',
    components: [],
    component_states: [],
    files: [],
    dependencies: {},
    specification: {},
  },
} as unknown as AnalysisRun

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(chatService.files).mockResolvedValue([
    dataset,
    {
      ...dataset,
      id: 'pdf',
      file_type: 'pdf',
      file_role: 'instrument',
      original_name: 'instrumento.pdf',
    },
  ])
  vi.mocked(chatService.list).mockResolvedValue([])
  vi.mocked(analysisService.list).mockResolvedValue([run])
  vi.mocked(analysisService.get).mockResolvedValue(run)
})

it('consulta solo al elegir Ver datos, pagina todos los registros y mantiene vacíos y texto sin HTML', async () => {
  vi.mocked(chatService.rows).mockImplementation(
    async (_project, _id, offset = 0) => ({
      columns: ['codigo', 'valor', 'texto'],
      offset,
      limit: 50,
      total_rows: 123,
      sheet: 'tabla',
      has_more: offset + 50 < 123,
      rows: Array.from({ length: Math.min(50, 123 - offset) }, (_, i) => [
        `00${offset + i}`,
        i === 0 ? null : '',
        '<script>alert(1)</script>',
      ]),
    }),
  )
  const { container } = render(<ProjectData projectId="privado" />)
  const user = userEvent.setup()
  await screen.findByRole('heading', { name: 'original.csv' })
  expect(chatService.rows).not.toHaveBeenCalled()
  expect(screen.getAllByRole('button', { name: 'Ver datos' })).toHaveLength(1)
  await user.click(screen.getByRole('button', { name: 'Ver datos' }))
  await screen.findByText(/Filas 1–50 de 123/)
  expect(chatService.rows).toHaveBeenLastCalledWith('privado', 'csv', 0)
  expect(screen.getAllByRole('row')).toHaveLength(51)
  expect(screen.getByText('000')).toBeInTheDocument()
  expect(screen.getByText('Ausente')).toBeInTheDocument()
  expect(screen.getAllByText('Vacío')).toHaveLength(49)
  expect(container.querySelector('script')).toBeNull()
  await user.click(screen.getByRole('button', { name: 'Página siguiente' }))
  await screen.findByText(/Filas 51–100 de 123/)
  await user.click(screen.getByRole('button', { name: 'Página siguiente' }))
  await screen.findByText(/Filas 101–123 de 123/)
  expect(
    screen.getByRole('button', { name: 'Página siguiente' }),
  ).toBeDisabled()
  expect(screen.getByText('00122')).toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Página anterior' }))
  await screen.findByText(/Filas 51–100 de 123/)
  await user.click(screen.getByRole('button', { name: 'Ocultar datos' }))
  expect(screen.queryByRole('table')).not.toBeInTheDocument()
})

it('conserva un fallo de autorización visible sin simular registros y permite reintentar', async () => {
  vi.mocked(chatService.rows)
    .mockRejectedValueOnce(new Error('No tienes acceso al archivo.'))
    .mockResolvedValueOnce({
      columns: ['x'],
      rows: [['real']],
      offset: 0,
      limit: 50,
      total_rows: 1,
      has_more: false,
      sheet: 'tabla',
    })
  render(<ProjectData projectId="privado" />)
  await userEvent.click(
    await screen.findByRole('button', { name: 'Ver datos' }),
  )
  expect(await screen.findByRole('alert')).toHaveTextContent('No tienes acceso')
  expect(screen.queryByRole('table')).not.toBeInTheDocument()
  await userEvent.click(
    screen.getByRole('button', { name: 'Reintentar consulta' }),
  )
  expect(await screen.findByText('real')).toBeInTheDocument()
})

function Navigation() {
  const location = useLocation()
  const navigate = useNavigate()
  return (
    <>
      <output aria-label="URL actual">{location.search}</output>
      <button onClick={() => navigate(-1)}>Atrás</button>
    </>
  )
}

it('Resultados tiene un solo cierre, conserva ZIP, parámetros adicionales e historial', async () => {
  render(
    <MemoryRouter
      initialEntries={['/proyectos/p/resultados?run=run&origen=prueba']}
    >
      <AnalysisResults projectId="p" />
      <Navigation />
    </MemoryRouter>,
  )
  const user = userEvent.setup()
  await screen.findByRole('button', { name: 'Descargar ZIP' })
  expect(
    screen.getAllByRole('button', { name: 'Cerrar detalle' }),
  ).toHaveLength(1)
  expect(
    screen.queryByRole('button', { name: 'Ocultar detalle' }),
  ).not.toBeInTheDocument()
  expect(
    screen.queryByRole('link', { name: 'Abrir en Resultados' }),
  ).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Descargar ZIP' }))
  expect(analysisService.downloadZip).toHaveBeenCalledWith('p', 'run')
  await user.click(screen.getByRole('button', { name: 'Cerrar detalle' }))
  expect(screen.getByLabelText('URL actual')).toHaveTextContent(
    '?origen=prueba',
  )
  expect(
    screen.queryByRole('button', { name: 'Descargar ZIP' }),
  ).not.toBeInTheDocument()
  await user.click(screen.getByRole('button', { name: 'Atrás' }))
  expect(
    await screen.findByRole('button', { name: 'Descargar ZIP' }),
  ).toBeInTheDocument()
  expect(screen.getByLabelText('URL actual')).toHaveTextContent('run=run')
})

it('desde otro módulo conserva el enlace a Resultados y el control de detalle', async () => {
  render(
    <MemoryRouter>
      <AnalysisResultCard projectId="p" runId="run" initialRun={run} expanded />
    </MemoryRouter>,
  )
  expect(
    screen.getByRole('link', { name: 'Abrir en Resultados' }),
  ).toHaveAttribute('href', '/proyectos/p/resultados?run=run')
  expect(
    screen.getByRole('button', { name: 'Ocultar detalle' }),
  ).toBeInTheDocument()
})

it('solo conserva identificadores de ejecución conocidos y omite el marcador legado', () => {
  const id = '10000000-0000-4000-8000-000000000001'
  expect(visibleChatText(`Ejecución run_id ${id}`, [], [id])).toContain(id)
  expect(
    visibleChatText(
      'Resultado ejecutado bajo el run_id archivo del proyecto.',
      [],
    ),
  ).not.toContain('run_id')
})
