import { MessageSquarePlus } from 'lucide-react'
import type { Conversation } from '../types/chat'
import { stageLabel } from '../types/chat'
import { Modal } from './Modal'

export function ConversationHistory({
  conversations,
  selected,
  busy,
  temporary,
  titleFor,
  onCreate,
  onSelect,
  onClose,
}: {
  conversations: Conversation[]
  selected: string
  busy: boolean
  temporary: boolean
  titleFor: (text: string) => string
  onCreate: () => void
  onSelect: (id: string) => void
  onClose: () => void
}) {
  const content = (
    <>
      <button className="btn primary w-full" disabled={busy} onClick={onCreate}>
        <MessageSquarePlus size={18} />
        Nueva conversación
      </button>
      {!temporary && <h2>Conversaciones</h2>}
      {conversations.length === 0 && (
        <p className="muted">Todavía no hay conversaciones.</p>
      )}
      <nav aria-label="Conversaciones">
        {conversations.map((item) => {
          const title = titleFor(item.title)
          return (
            <button
              key={item.id}
              className={selected === item.id ? 'selected' : ''}
              aria-current={selected === item.id ? 'page' : undefined}
              aria-label={`Abrir conversación: ${title}`}
              title={title}
              disabled={busy}
              onClick={() => onSelect(item.id)}
            >
              <strong>{title}</strong>
              <small>{stageLabel[item.current_stage]}</small>
            </button>
          )
        })}
      </nav>
      <p className="history-note muted">
        Cada conversación conserva su finalidad y puede reutilizar los archivos
        del proyecto.
      </p>
    </>
  )
  return temporary ? (
    <Modal
      title="Historial de conversaciones"
      className="conversation-drawer"
      onClose={onClose}
    >
      <div id="conversation-history" className="conversation-list">
        {content}
      </div>
    </Modal>
  ) : (
    <aside
      id="conversation-history"
      className="conversation-list"
      aria-label="Historial de conversaciones"
    >
      {content}
    </aside>
  )
}
