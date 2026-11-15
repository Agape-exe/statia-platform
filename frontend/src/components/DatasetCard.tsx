import type { ProjectFile } from '../types/chat'

const physical: Record<string, string> = {
  empty: 'Vacía',
  numeric: 'Numérico',
  text: 'Texto',
  boolean: 'Booleano',
}
const statistical: Record<string, string> = {
  identifier: 'Identificador probable',
  temporal: 'Temporal probable',
  categorical_or_ordinal: 'Categórica u ordinal',
  quantitative: 'Cuantitativa probable',
  categorical: 'Categórica probable',
}

export function DatasetCard({
  file,
  busy,
  onSheet,
  onDownload,
}: {
  file: ProjectFile
  busy: boolean
  onSheet: (sheet: string) => void
  onDownload: () => void
}) {
  const { profile } = file.metadata
  return (
    <details className="dataset-card">
      <summary>
        {file.original_name}{' '}
        <span className="muted">
          {file.file_role === 'instrument'
            ? 'Instrumento PDF'
            : profile
              ? `${profile.row_count} filas · ${profile.column_count} columnas`
              : 'Selecciona una hoja'}
        </span>
      </summary>
      <div className="dataset-body">
        <button className="btn secondary" disabled={busy} onClick={onDownload}>
          Descargar original
        </button>
        <p className="muted">
          {(file.file_size / 1024).toFixed(1)} KB ·{' '}
          {file.metadata.selected_sheet
            ? `Hoja: ${file.metadata.selected_sheet}`
            : file.metadata.pages
              ? `${file.metadata.pages} páginas`
              : ''}
        </p>
        {file.metadata.needs_sheet_selection && (
          <label>
            Hoja de {file.original_name}
            <select
              disabled={busy}
              value=""
              onChange={(e) => {
                if (e.target.value) onSheet(e.target.value)
              }}
            >
              <option value="" disabled>
                Elige una hoja
              </option>
              {file.metadata.sheets.map((sheet) => (
                <option key={sheet}>{sheet}</option>
              ))}
            </select>
          </label>
        )}
        {profile && (
          <>
            <p>
              {profile.missing_count} celdas ausentes · {profile.duplicate_rows}{' '}
              posibles filas duplicadas. El original permanece intacto.
            </p>
            <div className="table-scroll">
              <table>
                <caption>Perfil de columnas de {file.original_name}</caption>
                <thead>
                  <tr>
                    <th>Columna</th>
                    <th>Tipo físico</th>
                    <th>Tipo estadístico tentativo</th>
                    <th>Ausentes</th>
                    <th>Distintos</th>
                    <th>Mín. / Máx.</th>
                  </tr>
                </thead>
                <tbody>
                  {profile.columns.map((column) => (
                    <tr key={column.name}>
                      <th scope="row">{column.name}</th>
                      <td>
                        {physical[column.physical_type] || column.physical_type}
                      </td>
                      <td>
                        {statistical[column.statistical_type] ||
                          column.statistical_type}
                      </td>
                      <td>{column.missing}</td>
                      <td>{column.unique}</td>
                      <td>
                        {column.min === undefined
                          ? '—'
                          : `${column.min} / ${column.max}`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
        {file.metadata.warnings?.map((warning) => (
          <p className="muted" key={warning}>
            {warning}
          </p>
        ))}
      </div>
    </details>
  )
}
