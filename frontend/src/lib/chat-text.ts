import type { ProjectFile } from '../types/chat'

export function visibleChatText(
  text: string,
  files: ProjectFile[],
  runIds: string[] = [],
  technical = false,
): string {
  // Solo presentación de texto legado; no modificar el mensaje persistido.
  if (!technical) {
    text = text.replace(
      /https?:\/\/[^\s)`]+\/storage\/v1\/object\/[^\s)`]+/gi,
      'recurso privado',
    )
    text = text.replace(
      /\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}(?:\/[^\s)`]+)+/gi,
      'archivo privado',
    )
  }
  text = text.replace(
    /(?:ejecutad[oa] bajo el\s+)?run_id\s*[:=]?\s*archivo del proyecto/gi,
    '',
  )
  for (const file of files) text = text.split(file.id).join(file.original_name)
  if (!technical) {
    text = text.replace(
      /\brun_id`?\s*[:=]?\s*`?[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}`?/gi,
      'ejecución guardada',
    )
    text = text.replace(
      /\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})?\b/g,
      'fecha de la ejecución',
    )
  }
  return text.replace(
    /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi,
    (id) => (technical && runIds.includes(id) ? id : 'archivo del proyecto'),
  )
}
