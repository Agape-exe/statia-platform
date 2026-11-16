import type { JsonValue } from '../types/analysis'

export function formatResult(
  value: JsonValue | undefined,
  column = '',
): string {
  if (value === null || value === undefined) return 'No disponible'
  if (typeof value === 'number') {
    if (!Number.isFinite(value)) return 'No calculable'
    if (/^p($|\s)|^pvalue$/i.test(column))
      return value < 0.001 ? '< 0.001' : value.toFixed(4)
    if (Number.isInteger(value)) return value.toLocaleString('es-PE')
    if (Math.abs(value) > 0 && Math.abs(value) < 0.0001)
      return value.toExponential(3)
    return value.toLocaleString('es-PE', { maximumFractionDigits: 5 })
  }
  if (typeof value === 'object')
    return Array.isArray(value)
      ? value.map((v) => formatResult(v)).join(', ') || 'Sin moda repetida'
      : JSON.stringify(value)
  if (typeof value === 'boolean') return value ? 'Sí' : 'No'
  return value
}
