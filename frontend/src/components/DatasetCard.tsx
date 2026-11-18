import type { ProjectFile } from '../types/chat'

const physical: Record<string, string> = {
  empty: 'Vacía',
  numeric: 'Numérico',
  text: 'Texto',
  boolean: 'Booleano',
  mixed: 'Mixto: números y texto',
}
const source: Record<string, string> = {
  csv_text: 'Texto CSV',
  native_numeric: 'Valores numéricos nativos',
  native_text: 'Texto nativo',
  native_mixed: 'Valores nativos mixtos',
  native_temporal: 'Fecha nativa',
  native_boolean: 'Booleano nativo',
  empty: 'Vacía',
}
const statistical: Record<string, string> = {
  identifier: 'Identificador probable',
  temporal: 'Temporal probable',
  categorical_or_ordinal: 'Categórica u ordinal',
  quantitative: 'Cuantitativa probable',
  categorical: 'Categórica probable',
  mixed: 'Mixta; requiere aclaración',
  unknown: 'Sin datos para inferir',
}

export function DatasetCard({
  file,
  busy,
  onSheet,
  onDownload,
  expanded,
}: {
  file: ProjectFile
  busy: boolean
  onSheet?: (sheet: string) => void
  expanded?: boolean
  onDownload: () => void
}) {
  const { profile } = file.metadata
  return (
    <details className="dataset-card" open={expanded || undefined}>
      <summary>
        {file.original_name}{' '}
        <span className="muted">
          {file.file_role === 'instrument'
            ? 'Instrumento PDF'
            : profile
              ? `${profile.row_count} filas · ${profile.column_count} columnas`
              : file.metadata.needs_sheet_selection
                ? 'Hoja pendiente de selección en el asistente'
                : 'Perfil no disponible'}
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
              ? `${file.metadata.pages} ${file.metadata.pages === 1 ? 'página' : 'páginas'}`
              : ''}
        </p>
        {file.metadata.needs_sheet_selection && onSheet && (
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
        {file.file_role === 'instrument' && file.metadata.text_excerpt && (
          <details>
            <summary>Texto extraído del instrumento</summary>
            <p className="instrument-excerpt">{file.metadata.text_excerpt}</p>
            <p className="muted">
              Compartir extractos con el proveedor requiere habilitarlo
              explícitamente en el asistente.
            </p>
          </details>
        )}
        {profile && (
          <>
            {profile.profile_version !== 2 && (
              <p className="notice">
                Este perfil se creó antes de la corrección de tipos y ausencias.
                Para validar nuevos planes con el perfil actualizado, vuelve a
                cargar el original en una conversación nueva; los planes
                anteriores se conservan.
              </p>
            )}
            <p>
              {profile.missing_count} celdas ausentes · {profile.duplicate_rows}{' '}
              posibles filas duplicadas. El original permanece intacto.
            </p>
            {!!profile.ambiguous_missing_count && (
              <p>
                {profile.ambiguous_missing_count} posibles ausencias ambiguas se
                conservan como cadenas hasta confirmar su significado.
              </p>
            )}
            <p className="muted">
              Ausentes incluye vacíos y marcadores interpretados con evidencia.
              Un origen de texto CSV puede representar medidas numéricas; no
              implica conversión manual. El significado semántico sigue
              pendiente de confirmar.
            </p>
            {profile.columns.some(
              (c) =>
                c.physical_type === 'numeric' &&
                c.statistical_type === 'categorical_or_ordinal' &&
                !c.possible_identifier,
            ) && (
              <p className="notice">
                Para una medida numérica ambigua, confirma su significado en el
                chat escribiendo: «Confirmo que `nombre_columna` es cuantitativa
                discreta» o «continua». Se conserva el perfil original.
              </p>
            )}
            <div className="table-scroll">
              <table>
                <caption>Perfil de columnas de {file.original_name}</caption>
                <thead>
                  <tr>
                    <th>Columna</th>
                    <th>Representación de origen</th>
                    <th>Tipo inferido</th>
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
                        {source[column.source_representation || ''] ||
                          'No informada en este perfil'}
                      </td>
                      <td>
                        {physical[
                          column.inferred_type || column.physical_type
                        ] || column.physical_type}
                      </td>
                      <td>
                        {statistical[column.statistical_type] ||
                          column.statistical_type}
                      </td>
                      <td>
                        {column.missing}
                        {!!column.ambiguous_missing &&
                          Object.keys(column.ambiguous_missing).length > 0 &&
                          ` (+${Object.values(column.ambiguous_missing).reduce((total, count) => total + count, 0)} por confirmar)`}
                      </td>
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
