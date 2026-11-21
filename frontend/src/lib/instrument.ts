import type { ProjectFile } from '../types/chat'

export function instrumentReading(file: ProjectFile) {
  switch (file.metadata.extraction_status) {
    case 'partial':
      return 'Extracción parcial'
    case 'no_text':
      return 'Documento sin texto recuperable'
    case 'extracted':
      return 'Instrumento disponible'
    default:
      return 'Extracto histórico; lectura por verificar'
  }
}
