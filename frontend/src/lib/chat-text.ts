import type { ProjectFile } from '../types/chat'

export function visibleChatText(
  text: string,
  files: ProjectFile[],
  runIds: string[] = [],
): string {
  // Solo presentación de texto legado; no modificar el mensaje persistido.
  text = text.replace(
    /(?:ejecutad[oa] bajo el\s+)?run_id\s*[:=]?\s*archivo del proyecto/gi,
    '',
  )
  for (const file of files) text = text.split(file.id).join(file.original_name)
  return text.replace(
    /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi,
    (id) => (runIds.includes(id) ? id : 'archivo del proyecto'),
  )
}
