import type { ProjectFile } from '../types/chat'

export function visibleChatText(text: string, files: ProjectFile[]): string {
  for (const file of files) text = text.split(file.id).join(file.original_name)
  return text.replace(
    /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi,
    'archivo del proyecto',
  )
}
