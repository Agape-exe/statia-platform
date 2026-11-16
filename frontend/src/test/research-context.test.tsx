import { beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ThesisContext } from '../components/ThesisContext'
import { researchContextService } from '../services/research-context'
import { emptyContext, parseResearchContext } from '../lib/research-context'

vi.mock('../services/research-context', () => ({
  researchContextService: { get: vi.fn(), save: vi.fn() },
}))

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(researchContextService.get).mockResolvedValue({ context: null })
  vi.mocked(researchContextService.save).mockImplementation(
    async (_, document, revision) => ({
      context: {
        document,
        revision: revision + 1,
        updated_at: '2026-11-16T12:00:00Z',
      },
    }),
  )
})

describe('contexto de tesis', () => {
  it('admite desconocidos, tesis sin hipótesis y campos propios; rechaza formatos ajenos', () => {
    expect(
      parseResearchContext(
        '{"schema_version":1,"additional_fields":{"enfoque":null}}',
      ),
    ).toEqual({ ...emptyContext(), additional_fields: { enfoque: null } })
    for (const value of [
      '{}',
      '[]',
      '{"schema_version":true}',
      '{"schema_version":1,"variables":[3]}',
      '{"schema_version":1,"extra":"x"}',
    ])
      expect(() => parseResearchContext(value)).toThrow()
    expect(() =>
      parseResearchContext(
        JSON.stringify({ schema_version: 1, research_title: 'x'.repeat(2001) }),
      ),
    ).toThrow(/2000/)
  })

  it('importa a un borrador editable y exige revisión y confirmación antes de persistir', async () => {
    render(<ThesisContext projectId="thesis-a" />)
    const user = userEvent.setup()
    await screen.findByText(/Todavía no hay contexto guardado/)
    await user.click(screen.getByText('Importar contexto desde JSON'))
    await user.click(screen.getByLabelText('JSON estructurado'))
    await user.paste(
      JSON.stringify({
        schema_version: 1,
        research_title: 'Estudio importado',
        hypotheses: [],
        additional_fields: { disciplina: 'Historia' },
      }),
    )
    await user.click(
      screen.getByRole('button', { name: 'Cargar importación para revisar' }),
    )
    expect(researchContextService.save).not.toHaveBeenCalled()
    expect(screen.getByLabelText('Título de investigación')).toHaveValue(
      'Estudio importado',
    )
    await user.clear(screen.getByLabelText('Título de investigación'))
    await user.type(
      screen.getByLabelText('Título de investigación'),
      'Título revisado',
    )
    await user.click(
      screen.getByRole('button', { name: 'Revisar antes de guardar' }),
    )
    expect(screen.getByRole('dialog')).toHaveTextContent('Título revisado')
    expect(researchContextService.save).not.toHaveBeenCalled()
    await user.click(
      screen.getByRole('button', { name: 'Confirmar y guardar contexto' }),
    )
    await waitFor(() =>
      expect(researchContextService.save).toHaveBeenCalledWith(
        'thesis-a',
        expect.objectContaining({
          research_title: 'Título revisado',
          hypotheses: [],
        }),
        0,
      ),
    )
    expect(await screen.findByText(/Contexto guardado/)).toBeInTheDocument()
  })

  it('conserva el borrador ante conflicto y envía la revisión original', async () => {
    vi.mocked(researchContextService.get).mockResolvedValue({
      context: {
        document: emptyContext(),
        revision: 3,
        updated_at: '2026-11-16T12:00:00Z',
      },
    })
    vi.mocked(researchContextService.save).mockRejectedValue(
      new Error('El contexto cambió. Recarga y revisa antes de guardar.'),
    )
    render(<ThesisContext projectId="thesis-a" />)
    const user = userEvent.setup()
    await screen.findByText(/Revisión 3/)
    await user.type(
      screen.getByLabelText('Título de investigación'),
      'Mi borrador',
    )
    await user.click(
      screen.getByRole('button', { name: 'Revisar antes de guardar' }),
    )
    await user.click(
      screen.getByRole('button', { name: 'Confirmar y guardar contexto' }),
    )
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'El contexto cambió',
    )
    expect(screen.getByLabelText('Título de investigación')).toHaveValue(
      'Mi borrador',
    )
    expect(researchContextService.save).toHaveBeenCalledWith(
      'thesis-a',
      expect.anything(),
      3,
    )
  })

  it('informa errores de importación sin reemplazar campos existentes', async () => {
    render(<ThesisContext projectId="thesis-a" />)
    const user = userEvent.setup()
    await screen.findByText(/Todavía no hay contexto guardado/)
    await user.type(
      screen.getByLabelText('Título de investigación'),
      'Conservar',
    )
    await user.click(screen.getByText('Importar contexto desde JSON'))
    await user.type(screen.getByLabelText('JSON estructurado'), 'JSON inválido')
    await user.click(
      screen.getByRole('button', { name: 'Cargar importación para revisar' }),
    )
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'JSON no es válido',
    )
    expect(screen.getByLabelText('Título de investigación')).toHaveValue(
      'Conservar',
    )
    expect(researchContextService.save).not.toHaveBeenCalled()
  })
})
