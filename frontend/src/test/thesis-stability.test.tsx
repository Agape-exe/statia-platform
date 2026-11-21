import { beforeEach, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ThesisContext } from '../components/ThesisContext'
import { ResponseMeaning } from '../components/ResponseMeaning'
import { DatasetCard } from '../components/DatasetCard'
import { emptyContext } from '../lib/research-context'
import { visibleChatText } from '../lib/chat-text'
import { researchContextService } from '../services/research-context'
import type { ResultTable } from '../types/analysis'

vi.mock('../services/research-context', () => ({
  researchContextService: { get: vi.fn(), save: vi.fn() },
}))

beforeEach(() => vi.resetAllMocks())

it('distingue Contexto confirmado y cambios reales; deshacer no crea revisión', async () => {
  const document = {
    ...emptyContext(),
    research_title: 'Investigación comunitaria',
    additional_fields: { z: 'último', a: 'primero' },
  }
  vi.mocked(researchContextService.get).mockResolvedValue({
    context: { document, revision: 4, updated_at: '2026-11-20T12:00:00Z' },
  })
  vi.mocked(researchContextService.save).mockImplementation(
    async (_, doc, revision) => ({
      context: {
        document: doc,
        revision: revision + 1,
        updated_at: '2026-11-20T13:00:00Z',
      },
    }),
  )
  render(<ThesisContext projectId="thesis" />)
  const user = userEvent.setup()
  await screen.findByText(/Contexto confirmado · Revisión 4/)
  const review = screen.getByRole('button', {
    name: 'Revisar antes de guardar',
  })
  expect(review).toBeDisabled()
  const title = screen.getByLabelText('Título de investigación')
  await user.type(title, ' actualizado')
  expect(review).toBeEnabled()
  await user.clear(title)
  await user.type(title, 'Investigación comunitaria')
  expect(review).toBeDisabled()
  await user.clear(screen.getByLabelText(/Campos adicionales de tu disciplina/))
  await user.paste('{"a":"primero","z":"último"}')
  expect(review).toBeDisabled()
  expect(researchContextService.save).not.toHaveBeenCalled()
  await user.type(title, ' nuevo')
  await user.click(review)
  await user.click(
    screen.getByRole('button', { name: 'Confirmar y guardar contexto' }),
  )
  await screen.findByText(/Contexto confirmado · Revisión 5/)
  expect(review).toBeDisabled()
  expect(researchContextService.save).toHaveBeenCalledTimes(1)
})

it('permite clasificar no información en una vista local, sin alterar los conteos', async () => {
  const table = {
    title: 'Frecuencias guardadas',
    columns: [
      'Variable / grupo',
      'Categoría',
      'Frecuencia',
      'N válido',
      'Ausentes',
    ],
    rows: [
      {
        'Variable / grupo': 'apoyo',
        Categoría: 'Habitual',
        Frecuencia: 8,
        'N válido': 12,
        Ausentes: 2,
      },
      {
        'Variable / grupo': 'apoyo',
        Categoría: 'Ocasional',
        Frecuencia: 1,
        'N válido': 12,
        Ausentes: 2,
      },
      {
        'Variable / grupo': 'apoyo',
        Categoría: 'Sin opinión',
        Frecuencia: 3,
        'N válido': 12,
        Ausentes: 2,
      },
    ],
  } as ResultTable
  const original = structuredClone(table)
  render(<ResponseMeaning table={table} />)
  const user = userEvent.setup()
  await user.click(
    screen.getByText('Distinguir valores presentes y respuestas sustantivas'),
  )
  expect(screen.queryByRole('status')).not.toBeInTheDocument()
  await user.click(screen.getByRole('checkbox', { name: 'Sin opinión (3)' }))
  expect(screen.getByRole('status')).toHaveTextContent(
    '12 valores presentes · 9 respuestas sustantivas · 3 respuestas de no información',
  )
  expect(table).toEqual(original)
  expect(screen.getByText(/no se guarda ni modifica/)).toBeInTheDocument()
})

it('no presenta un desglose semántico si la tabla está incompleta', () => {
  render(
    <ResponseMeaning
      table={{
        title: 'Incompleta',
        columns: [
          'Variable / grupo',
          'Categoría',
          'Frecuencia',
          'N válido',
          'Ausentes',
        ],
        rows: [
          {
            'Variable / grupo': 'x',
            Categoría: 'A',
            Frecuencia: 2,
            'N válido': 7,
            Ausentes: 0,
          },
        ],
      }}
    />,
  )
  expect(screen.queryByRole('checkbox')).not.toBeInTheDocument()
  expect(screen.getByText(/No hay una tabla completa/)).toBeInTheDocument()
})

it('informa lectura parcial Word y conserva descarga del original', async () => {
  const download = vi.fn()
  render(
    <DatasetCard
      busy={false}
      expanded
      onDownload={download}
      file={{
        id: 'word',
        file_role: 'instrument',
        file_type: 'docx',
        original_name: 'escala.docx',
        file_size: 700,
        metadata: {
          sheets: [],
          extraction_status: 'partial',
          text_excerpt: 'Preguntas recuperadas',
          warnings: ['Numeración automática no recuperable'],
        },
      }}
    />,
  )
  expect(screen.getByText('Instrumento DOCX')).toBeInTheDocument()
  expect(screen.getByText(/extracción parcial/)).toBeInTheDocument()
  expect(screen.getByText(/Archivo asociado no significa/)).toBeInTheDocument()
  await userEvent.click(
    screen.getByRole('button', { name: 'Descargar original' }),
  )
  expect(download).toHaveBeenCalledOnce()
})

it('oculta UUID y fecha técnica por defecto; solo muestra trazas verificadas al pedirlas', () => {
  const id = '10000000-0000-4000-8000-000000000001'
  const text = `Resultado run_id ${id} · 2026-11-20T12:00:00Z`
  expect(visibleChatText(text, [], [id])).not.toMatch(/run_id|10000000|T12:/)
  expect(visibleChatText(text, [], [id], true)).toContain(id)
  expect(visibleChatText(text, [], [], true)).not.toContain(id)
  expect(
    visibleChatText(
      `https://example.invalid/storage/v1/object/private/${id}/documento.docx?token=synthetic`,
      [],
    ),
  ).toBe('recurso privado')
})
