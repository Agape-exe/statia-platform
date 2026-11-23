import { useState } from 'react'
import type { ResultTable } from '../types/analysis'

// Capa de lectura local: el investigador declara las categorías; no altera resultados.
export function ResponseMeaning({ table }: { table: ResultTable }) {
  const [selection, setSelection] = useState<string[]>([])
  if (
    ![
      'Variable / grupo',
      'Categoría',
      'Frecuencia',
      'N válido',
      'Ausentes',
    ].every((column) => table.columns.includes(column))
  )
    return null
  const groups = [
    ...new Set(table.rows.map((row) => String(row['Variable / grupo']))),
  ]
  return (
    <details>
      <summary>Distinguir valores presentes y respuestas sustantivas</summary>
      <p>
        N válido cuenta valores presentes según la ejecución. Ausentes cuenta
        las exclusiones registradas. Una categoría de no información puede estar
        presente físicamente. Los porcentajes originales mantienen su
        denominador.
      </p>
      <p>
        Selecciona únicamente las categorías cuyo significado de no información
        hayas confirmado. Esta vista local no se guarda ni modifica el análisis
        o sus descargas.
      </p>
      {groups.map((group) => {
        const rows = table.rows.filter(
          (row) => String(row['Variable / grupo']) === group,
        )
        const total = Number(rows[0]?.['N válido'])
        const complete =
          rows.every(
            (row) =>
              typeof row.Frecuencia === 'number' &&
              Number.isSafeInteger(row.Frecuencia) &&
              row.Frecuencia >= 0 &&
              row['N válido'] === total,
          ) &&
          rows.reduce((sum, row) => sum + Number(row.Frecuencia), 0) === total
        if (!complete)
          return (
            <p key={group}>
              No hay una tabla completa para distinguir respuestas en {group}.
            </p>
          )
        const excluded = rows
          .filter((row) =>
            selection.includes(JSON.stringify([group, row.Categoría])),
          )
          .reduce((sum, row) => sum + Number(row.Frecuencia), 0)
        return (
          <fieldset key={group}>
            <legend>{group}: categorías de no información</legend>
            {rows.map((row) => {
              const key = JSON.stringify([group, row.Categoría])
              return (
                <label className="checkbox-label" key={key}>
                  <input
                    type="checkbox"
                    checked={selection.includes(key)}
                    onChange={(event) =>
                      setSelection((current) =>
                        event.target.checked
                          ? [...current, key]
                          : current.filter((item) => item !== key),
                      )
                    }
                  />
                  {String(row.Categoría)} ({String(row.Frecuencia)})
                </label>
              )
            })}
            {selection.some((key) =>
              rows.some(
                (row) => key === JSON.stringify([group, row.Categoría]),
              ),
            ) && (
              <p role="status">
                Según tu selección: {total} valores presentes ·{' '}
                {total - excluded} respuestas sustantivas · {excluded}{' '}
                respuestas de no información. Ausentes registrados:{' '}
                {String(rows[0]?.Ausentes)}.
              </p>
            )}
          </fieldset>
        )
      })}
    </details>
  )
}
