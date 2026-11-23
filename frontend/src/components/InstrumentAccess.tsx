import { useState } from 'react'
import { FileText, ShieldCheck } from 'lucide-react'
import type { AssistantProviderId, ProjectFile } from '../types/chat'
import { providerName } from '../lib/assistant-provider'
import { Modal } from './Modal'
import { instrumentReading } from '../lib/instrument'

export function InstrumentAccess({
  files,
  provider,
  decision,
  busy,
  onDecide,
}: {
  files: ProjectFile[]
  provider: AssistantProviderId
  decision: boolean | undefined
  busy: boolean
  onDecide: (allowed: boolean) => void
}) {
  const [reviewing, setReviewing] = useState(false)
  const instruments = files.filter((file) => file.file_role === 'instrument')
  if (!instruments.length) return null
  const choose = (allowed: boolean) => {
    onDecide(allowed)
    setReviewing(false)
  }
  return (
    <>
      <div className="instrument-access" aria-label="Acceso a instrumentos">
        <ShieldCheck size={16} aria-hidden="true" />
        <span>
          {instruments.length}{' '}
          {instruments.length === 1 ? 'instrumento' : 'instrumentos'} ·{' '}
          {decision ? 'Lectura autorizada' : 'Contenido no compartido'} con{' '}
          {providerName(provider)}
        </span>
        <button
          className="text-button"
          disabled={busy}
          onClick={() => setReviewing(true)}
        >
          Cambiar autorización
        </button>
      </div>
      {!busy && (decision === undefined || reviewing) && (
        <Modal
          title="¿Quieres que Statia utilice este instrumento para comprender mejor tus datos?"
          onClose={() => choose(decision ?? false)}
          className="instrument-consent"
        >
          <p>
            Podemos compartir fragmentos relevantes del instrumento con el
            proveedor seleccionado para identificar preguntas, variables,
            escalas y categorías de respuesta. El archivo original permanece en
            almacenamiento privado.
          </p>
          <p className="consent-provider">
            Proveedor seleccionado: <strong>{providerName(provider)}</strong>
          </p>
          <ul className="consent-files">
            {instruments.map((file) => (
              <li key={file.id}>
                <FileText size={18} aria-hidden="true" />
                <span>
                  <strong>{file.original_name}</strong>
                  <small>{instrumentReading(file)}</small>
                </span>
              </li>
            ))}
          </ul>
          <p className="muted">
            La autorización se aplica a los próximos mensajes de esta
            conversación durante esta sesión y puedes modificarla aquí. No se
            reenvían consultas anteriores. El historial ya compartido se
            conserva.
          </p>
          <div className="form-actions">
            <button className="btn secondary" onClick={() => choose(false)}>
              Continuar sin compartir
            </button>
            <button className="btn primary" onClick={() => choose(true)}>
              Permitir consultar fragmentos
            </button>
          </div>
        </Modal>
      )}
    </>
  )
}
