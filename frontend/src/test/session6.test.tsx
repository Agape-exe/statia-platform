import { beforeEach, expect, it, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ChatMarkdown } from '../components/ChatMarkdown'
import { ProjectData } from '../components/ProjectData'
import { chatService } from '../services/chat'
import type { ProjectFile } from '../types/chat'

vi.mock('../services/chat', () => ({
  chatService: { files: vi.fn(), profile: vi.fn(), download: vi.fn() },
}))
beforeEach(() => vi.resetAllMocks())

it('renderiza GFM, código y enlaces permitidos sin ejecutar HTML ni javascript', () => {
  const { container } = render(
    <ChatMarkdown>
      {
        '# Resumen\n\n**Resultado** y *detalle*, `puntaje`\n\n| Medida | Valor |\n|---|---|\n| Media | 12 |\n\n- Primer punto\n\n```python\nprint(1)\n```\n\n[Seguro](https://example.org) [Inseguro](javascript:alert(1))\n\n<script>alert(1)</script><img src=x onerror=alert(1)>'
      }
    </ChatMarkdown>,
  )
  expect(screen.getByRole('heading', { name: 'Resumen' })).toBeInTheDocument()
  expect(container.querySelector('strong')).toHaveTextContent('Resultado')
  expect(screen.getByRole('table')).toHaveTextContent('Media')
  expect(container.querySelector('pre code')).toHaveTextContent('print(1)')
  expect(screen.getByRole('link', { name: 'Seguro' })).toHaveAttribute(
    'rel',
    'noopener noreferrer',
  )
  expect(
    screen.queryByRole('link', { name: 'Inseguro' }),
  ).not.toBeInTheDocument()
  expect(container.querySelector('script, img, iframe')).toBeNull()
})

it('Datos muestra cada ID una vez, mantiene archivos distintos del mismo nombre y consulta/descarga privados', async () => {
  const dataset: ProjectFile = {
    id: 'csv',
    original_name: 'datos.csv',
    file_type: 'csv',
    file_role: 'dataset',
    file_size: 500,
    metadata: { sheets: [] },
  }
  const instrument: ProjectFile = {
    id: 'pdf',
    original_name: 'instrumento.pdf',
    file_type: 'pdf',
    file_role: 'instrument',
    file_size: 1200,
    metadata: { sheets: [] },
  }
  vi.mocked(chatService.files).mockResolvedValue([
    dataset,
    dataset,
    { ...dataset, id: 'otro' },
    instrument,
  ])
  vi.mocked(chatService.profile).mockResolvedValue({
    sheets: [],
    pages: 1,
    text_excerpt: 'Instrumento sintético',
    warnings: [],
  })
  vi.mocked(chatService.download).mockResolvedValue(undefined)
  render(<ProjectData projectId="proyecto-privado" />)
  const user = userEvent.setup()
  await screen.findByRole('heading', { name: 'instrumento.pdf' })
  expect(screen.getAllByRole('article')).toHaveLength(3)
  const card = screen
    .getByRole('heading', { name: 'instrumento.pdf' })
    .closest('article')!
  await user.click(
    within(card).getByRole('button', { name: 'Consultar metadatos y perfil' }),
  )
  await screen.findByText(/1 página/)
  expect(chatService.profile).toHaveBeenCalledWith('proyecto-privado', 'pdf')
  await user.click(within(card).getByText(/Vista previa del texto recuperado/))
  expect(screen.getByText('Instrumento sintético')).toBeInTheDocument()
  await user.click(
    within(card).getAllByRole('button', { name: 'Descargar original' })[0],
  )
  expect(chatService.download).toHaveBeenCalledWith(
    'proyecto-privado',
    expect.objectContaining({ id: 'pdf' }),
  )
  await user.click(
    within(card).getByRole('button', { name: 'Ocultar metadatos y perfil' }),
  )
  expect(screen.queryByText('Instrumento sintético')).not.toBeInTheDocument()
})

it('Datos informa fallo y vacío, y permite recuperar la carga', async () => {
  vi.mocked(chatService.files)
    .mockRejectedValueOnce(new Error('Sesión vencida'))
    .mockResolvedValueOnce([])
  render(<ProjectData projectId="privado" />)
  expect(await screen.findByRole('alert')).toHaveTextContent('Sesión vencida')
  await userEvent.click(
    screen.getByRole('button', { name: 'Actualizar archivos' }),
  )
  expect(await screen.findByText(/Aún no hay archivos/)).toBeInTheDocument()
})
