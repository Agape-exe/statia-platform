import { beforeEach, expect, it, vi } from 'vitest'
import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { ProjectData } from '../components/ProjectData'
import { chatService } from '../services/chat'
import type { ProjectFile } from '../types/chat'

vi.mock('../services/chat', () => ({
  chatService: {
    files: vi.fn(),
    profile: vi.fn(),
    rows: vi.fn(),
    download: vi.fn(),
    sheet: vi.fn(),
  },
}))

const firstProfile = {
  profile_version: 2,
  row_count: 123,
  column_count: 1,
  missing_count: 0,
  duplicate_rows: 0,
  columns: [
    {
      name: 'presión kPa',
      physical_type: 'numeric',
      statistical_type: 'quantitative',
      semantic_hint: 'Tentativo',
      unique: 123,
      missing: 0,
    },
  ],
}
const secondProfile = {
  ...firstProfile,
  row_count: 2,
  column_count: 2,
  missing_count: 1,
  columns: [
    {
      ...firstProfile.columns[0]!,
      name: 'categoría',
      physical_type: 'text',
      statistical_type: 'categorical',
    },
    { ...firstProfile.columns[0]!, name: 'valor' },
  ],
}
const metadata: ProjectFile['metadata'] = {
  sheets: ['Medición física', 'Economía 日本', 'Vacía'],
  selected_sheet: 'Medición física',
  profile: firstProfile,
  workbook_profile_version: 1,
  sheet_profiles: [
    {
      sheet: 'Medición física',
      status: 'available',
      profile: firstProfile,
      warnings: [],
    },
    {
      sheet: 'Economía 日本',
      status: 'available',
      profile: secondProfile,
      warnings: [],
    },
    {
      sheet: 'Vacía',
      status: 'unavailable',
      warnings: ['La tabla no contiene registros.'],
    },
  ],
}
const file: ProjectFile = {
  id: 'excel',
  original_name: 'libro.xlsx',
  file_type: 'xlsx',
  file_role: 'dataset',
  file_size: 500,
  metadata: { sheets: [] },
}

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(chatService.files).mockResolvedValue([file])
  vi.mocked(chatService.profile).mockResolvedValue(structuredClone(metadata))
  vi.mocked(chatService.rows).mockImplementation(
    async (_project, _file, offset = 0, sheet) => {
      if (sheet === 'Vacía') throw new Error('La tabla no contiene registros.')
      const other = sheet === 'Economía 日本'
      return {
        sheet: sheet || 'Medición física',
        offset,
        limit: 50,
        columns: other ? ['categoría', 'valor'] : ['presión kPa'],
        rows: other
          ? [
              ['NA', null],
              ['Sur', '12'],
            ]
          : Array.from({ length: Math.min(50, 123 - offset) }, (_, i) => [
              `${offset + i}`,
            ]),
        total_rows: other ? 2 : 123,
        has_more: !other && offset < 100,
      }
    },
  )
})

it('cambia solo la hoja visual, reinicia paginación y consulta su perfil sin modificar la selección histórica', async () => {
  const user = userEvent.setup()
  const historical = structuredClone(metadata)
  render(<ProjectData projectId="privado" />)
  await user.click(await screen.findByRole('button', { name: 'Ver datos' }))
  await screen.findByText(/Filas 1–50 de 123/)
  const selector = screen.getByRole('combobox', {
    name: /Hoja visible de libro.xlsx/,
  })
  expect(selector).toHaveValue('Medición física')
  await user.click(screen.getByRole('button', { name: 'Página siguiente' }))
  await screen.findByText(/Filas 51–100 de 123/)
  await user.selectOptions(selector, 'Economía 日本')
  await screen.findByText(/Hoja: Economía 日本. Filas 1–2 de 2. 2 columnas/)
  expect(chatService.rows).toHaveBeenLastCalledWith(
    'privado',
    'excel',
    0,
    'Economía 日本',
  )
  expect(
    screen.getByRole('columnheader', { name: 'categoría' }),
  ).toBeInTheDocument()
  expect(screen.getByText('Ausente')).toBeInTheDocument()
  expect(screen.getByRole('button', { name: 'Página anterior' })).toBeDisabled()
  expect(
    screen.getByRole('button', { name: 'Página siguiente' }),
  ).toBeDisabled()
  await user.click(
    screen.getByRole('button', { name: 'Consultar metadatos y perfil' }),
  )
  const profileTable = screen.getByRole('table', {
    name: 'Perfil de columnas de libro.xlsx',
  })
  expect(within(profileTable).getByText('categoría')).toBeInTheDocument()
  expect(
    within(profileTable).queryByText('presión kPa'),
  ).not.toBeInTheDocument()
  expect(chatService.profile).toHaveBeenCalledOnce()
  await user.click(screen.getByRole('button', { name: 'Descargar original' }))
  expect(chatService.download).toHaveBeenCalledWith('privado', {
    ...file,
    metadata,
  })
  expect(chatService.sheet).not.toHaveBeenCalled()
  expect(metadata).toEqual(historical)
  await user.selectOptions(selector, 'Medición física')
  await screen.findByText(/Filas 1–50 de 123/)
  expect(chatService.rows).toHaveBeenLastCalledWith(
    'privado',
    'excel',
    0,
    'Medición física',
  )
})

it('informa hojas no examinables y permite volver a una válida', async () => {
  const user = userEvent.setup()
  render(<ProjectData projectId="privado" />)
  await user.click(await screen.findByRole('button', { name: 'Ver datos' }))
  await screen.findByText(/Filas 1–50/)
  await user.selectOptions(screen.getByRole('combobox'), 'Vacía')
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'no contiene registros',
  )
  expect(screen.queryByRole('table')).not.toBeInTheDocument()
  await user.selectOptions(screen.getByRole('combobox'), 'Economía 日本')
  await screen.findByRole('table')
  expect(screen.queryByRole('alert')).not.toBeInTheDocument()
})

it('ignora una respuesta tardía de otra hoja al cambiar la selección', async () => {
  let resolve:
    ((value: Awaited<ReturnType<typeof chatService.rows>>) => void) | undefined
  vi.mocked(chatService.rows).mockImplementationOnce(
    () =>
      new Promise((done) => {
        resolve = done
      }),
  )
  render(<ProjectData projectId="privado" />)
  const user = userEvent.setup()
  await user.click(await screen.findByRole('button', { name: 'Ver datos' }))
  await user.selectOptions(await screen.findByRole('combobox'), 'Economía 日本')
  await screen.findByText(/Filas 1–2 de 2/)
  resolve?.({
    sheet: 'Medición física',
    offset: 0,
    limit: 50,
    columns: ['obsoleta'],
    rows: [['vieja']],
    total_rows: 1,
    has_more: false,
  })
  await waitFor(() =>
    expect(screen.queryByText('obsoleta')).not.toBeInTheDocument(),
  )
  expect(
    screen.getByRole('columnheader', { name: 'categoría' }),
  ).toBeInTheDocument()
})
