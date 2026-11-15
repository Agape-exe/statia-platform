import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { MessageSquarePlus, PanelLeftClose, PanelLeftOpen } from 'lucide-react'
import { chatService } from '../services/chat'
import { ApiError } from '../lib/api'
import { visibleChatText } from '../lib/chat-text'
import type { Project } from '../types/project'
import {
  stageLabel,
  type Conversation,
  type ConversationDetail,
  type ProjectFile,
  type Turn,
  type TurnAction,
} from '../types/chat'
import { Alert, Loading } from './ui'
import { Modal } from './Modal'
import { DatasetCard } from './DatasetCard'
import { ProposalCard } from './ProposalCard'
import { ChatComposer } from './ChatComposer'
import { ConversationHistory } from './ConversationHistory'
import { useChatScroll } from '../hooks/use-chat-scroll'

export function StatisticalChat({ project }: { project: Project }) {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [projectFiles, setProjectFiles] = useState<ProjectFile[]>([])
  const [detail, setDetail] = useState<ConversationDetail | null>(null)
  const [selected, setSelected] = useState('')
  const [loading, setLoading] = useState(true)
  const [opening, setOpening] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<Error | null>(null)
  const [text, setText] = useState('')
  const [pending, setPending] = useState<Turn | null>(null)
  const [rename, setRename] = useState<string | null>(null)
  const [removing, setRemoving] = useState(false)
  const [reuseIds, setReuseIds] = useState<string[]>([])
  const [samples, setSamples] = useState(false)
  const [instrumentText, setInstrumentText] = useState(false)
  const [compact, setCompact] = useState(
    () => window.matchMedia('(max-width: 1100px)').matches,
  )
  const [historyOpen, setHistoryOpen] = useState(
    () => !window.matchMedia('(max-width: 1100px)').matches,
  )
  const [busyLabel, setBusyLabel] = useState('Procesando la solicitud…')
  const historyButton = useRef<HTMLButtonElement>(null)
  const temporaryHistory = useRef(false)
  useEffect(() => {
    if (temporaryHistory.current && !historyOpen)
      historyButton.current?.focus({ preventScroll: true })
    temporaryHistory.current = historyOpen && compact
  }, [historyOpen, compact])
  const { transcript, onScroll, capturePrepend, end, unread, requestFollow } =
    useChatScroll(
      opening ? undefined : detail?.conversation.id,
      detail?.messages[0]?.id,
      detail?.messages.at(-1)?.id,
    )
  const generation = useRef(0)
  const selectedRef = useRef('')
  const mutation = useRef(false)

  const showError = (caught: unknown) =>
    setError(
      caught instanceof Error
        ? caught
        : new Error('No se pudo completar la operación.'),
    )

  async function refresh(id = selectedRef.current) {
    const version = ++generation.current
    const [list, files, current] = await Promise.all([
      chatService.list(project.id),
      chatService.files(project.id),
      id ? chatService.get(project.id, id) : Promise.resolve(null),
    ])
    if (version !== generation.current) return
    setConversations(list)
    setProjectFiles(files)
    setDetail(current)
    setSelected(id)
    selectedRef.current = id
    if (current?.retry_turn) setPending(current.retry_turn)
    return current
  }

  useEffect(() => {
    let active = true
    Promise.all([chatService.list(project.id), chatService.files(project.id)])
      .then(async ([list, files]) => {
        if (!active) return
        setConversations(list)
        setProjectFiles(files)
        const id = list[0]?.id
        if (id) {
          const current = await chatService.get(project.id, id)
          if (!active) return
          setDetail(current)
          setSelected(id)
          selectedRef.current = id
          setPending(current.retry_turn || null)
        }
      })
      .catch((caught) => {
        if (active) showError(caught)
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [project.id])

  useEffect(() => {
    const query = window.matchMedia('(max-width: 1100px)')
    const change = () => {
      setCompact(query.matches)
      setHistoryOpen(!query.matches)
    }
    query.addEventListener('change', change)
    return () => query.removeEventListener('change', change)
  }, [])

  async function perform(work: () => Promise<void>) {
    if (mutation.current) return
    mutation.current = true
    setBusy(true)
    setBusyLabel('Procesando la solicitud…')
    setError(null)
    try {
      await work()
    } catch (caught) {
      showError(caught)
    } finally {
      mutation.current = false
      setBusy(false)
    }
  }

  async function open(id: string) {
    if (busy || opening) return
    setOpening(true)
    setError(null)
    setPending(null)
    setText('')
    setReuseIds([])
    try {
      await refresh(id)
    } catch (caught) {
      showError(caught)
    } finally {
      setOpening(false)
    }
  }

  const create = (source?: string) =>
    perform(async () => {
      const conversation = await chatService.create(project.id, source)
      setPending(null)
      setText('')
      setReuseIds([])
      await refresh(conversation.id)
    })

  async function send(
    action: TurnAction = 'message',
    ids: string[] = [],
    retry?: Turn,
  ) {
    const id = selectedRef.current
    if (!id) return
    const turn: Turn = retry || {
      request_id: crypto.randomUUID(),
      action,
      content: action === 'message' ? text.trim() : '',
      file_ids: ids,
      share_samples: samples,
      share_instrument_text: instrumentText,
    }
    if (turn.action === 'message' && !turn.content) return
    await perform(() => submitTurn(id, turn))
  }

  async function submitTurn(id: string, turn: Turn) {
    requestFollow()
    setBusyLabel('Statia está preparando una respuesta…')
    setPending(turn)
    try {
      await chatService.turn(project.id, id, turn)
      setPending(null)
      setText('')
      await refresh(id)
    } catch (caught) {
      // El mensaje puede haberse persistido antes del fallo del proveedor.
      try {
        await refresh(id)
      } catch {
        /* Conservar la vista y el reintento original. */
      }
      throw caught
    }
  }

  async function understandIfReady(
    current: ConversationDetail | null | undefined,
  ) {
    if (
      !current ||
      pending ||
      ['instrument', 'reuse'].includes(current.conversation.current_stage) ||
      !current.files.some((file) => file.metadata.profile) ||
      current.files.some((file) => file.metadata.needs_sheet_selection)
    )
      return
    await submitTurn(current.conversation.id, {
      request_id: crypto.randomUUID(),
      action: 'files_ready',
      content: '',
      file_ids: [],
      share_samples: samples,
      share_instrument_text: instrumentText,
    })
  }

  const upload = (files: File[]) =>
    perform(async () => {
      const failures: string[] = []
      for (const file of files) {
        try {
          setBusyLabel(`Subiendo ${file.name}…`)
          await chatService.upload(
            project.id,
            selectedRef.current,
            file,
            file.name.toLowerCase().endsWith('.pdf') ? 'instrument' : 'dataset',
          )
        } catch (caught) {
          failures.push(
            `${file.name}: ${caught instanceof Error ? caught.message : 'No se pudo subir.'}`,
          )
        }
      }
      const current = await refresh()
      if (failures.length) throw new Error(failures.join('\n'))
      if (files.some((file) => !file.name.toLowerCase().endsWith('.pdf')))
        await understandIfReady(current)
    })

  const conversation = detail?.conversation
  const visible = (value: string) =>
    visibleChatText(value, detail?.files || projectFiles)
  const answerReuse = (content: string) =>
    perform(() =>
      submitTurn(selectedRef.current, {
        request_id: crypto.randomUUID(),
        action: 'message',
        content,
        file_ids: [],
        share_samples: samples,
        share_instrument_text: instrumentText,
      }),
    )
  const disabled = busy || opening
  const candidates = projectFiles.filter((file) =>
    conversation?.stage_data.reuse_file_ids?.includes(file.id),
  )
  const unlinked = projectFiles.filter(
    (file) => !detail?.files.some((linked) => linked.id === file.id),
  )
  if (loading) return <Loading />
  return (
    <div
      className={`chat-layout ${historyOpen && !compact ? '' : 'history-collapsed'}`}
    >
      {historyOpen && (
        <ConversationHistory
          conversations={conversations}
          selected={selected}
          busy={disabled}
          temporary={compact}
          titleFor={visible}
          onClose={() => setHistoryOpen(false)}
          onCreate={() => {
            if (compact) setHistoryOpen(false)
            void create()
          }}
          onSelect={(id) => {
            if (compact) setHistoryOpen(false)
            void open(id)
          }}
        />
      )}
      <section className="chat-panel" aria-label="Chat estadístico">
        <div className="chat-toolbar">
          <button
            className="icon-btn"
            ref={historyButton}
            aria-label={historyOpen ? 'Ocultar historial' : 'Mostrar historial'}
            title={historyOpen ? 'Ocultar historial' : 'Mostrar historial'}
            aria-expanded={historyOpen}
            aria-controls="conversation-history"
            onClick={() => setHistoryOpen((value) => !value)}
          >
            {historyOpen ? (
              <PanelLeftClose size={21} />
            ) : (
              <PanelLeftOpen size={21} />
            )}
          </button>
          <span>Conversación estadística</span>
          <button
            className="btn secondary"
            disabled={disabled}
            onClick={() => create()}
          >
            <MessageSquarePlus size={17} />
            Nuevo chat
          </button>
        </div>
        {error && (
          <Alert>
            {error.message}
            {error instanceof ApiError && error.status === 401 && (
              <Link to="/login"> Recuperar acceso</Link>
            )}
            <button
              disabled={disabled}
              onClick={() =>
                perform(async () => {
                  await refresh()
                  setLoading(false)
                })
              }
            >
              Recargar
            </button>
          </Alert>
        )}
        {opening ? (
          <Loading />
        ) : !detail || !conversation ? (
          <div className="chat-empty">
            <MessageSquarePlus size={36} />
            <h2>Comienza con una pregunta</h2>
            <p>
              Adjunta tus datos, aclara tu objetivo y prepara un plan
              estadístico verificable.
            </p>
            <button
              className="btn primary"
              disabled={disabled}
              onClick={() => create()}
            >
              Crear conversación
            </button>
          </div>
        ) : (
          <>
            <header className="chat-heading">
              <div>
                <h2>{visible(conversation.title)}</h2>
                <small>{stageLabel[conversation.current_stage]}</small>
              </div>
              <div className="chat-actions">
                <button
                  className="btn secondary"
                  disabled={disabled}
                  onClick={() => setRename(visible(conversation.title))}
                >
                  Renombrar
                </button>
                <button
                  className="btn secondary danger-text"
                  disabled={disabled}
                  onClick={() => setRemoving(true)}
                >
                  Eliminar
                </button>
              </div>
            </header>
            <div
              className="transcript"
              ref={transcript}
              onScroll={onScroll}
              tabIndex={0}
              aria-label="Mensajes y archivos"
            >
              <div className="transcript-inner">
                {detail.has_more_messages && (
                  <button
                    className="btn secondary"
                    disabled={disabled}
                    onClick={() =>
                      perform(async () => {
                        const page = await chatService.earlier(
                          project.id,
                          selected,
                          detail.messages[0].position,
                        )
                        if (page.messages.length) capturePrepend()
                        setDetail((current) =>
                          current
                            ? {
                                ...current,
                                messages: [
                                  ...page.messages,
                                  ...current.messages,
                                ],
                                has_more_messages: page.has_more_messages,
                              }
                            : current,
                        )
                      })
                    }
                  >
                    Cargar mensajes anteriores
                  </button>
                )}
                {conversation.primary_goal && (
                  <p className="goal-note">
                    <strong>Finalidad:</strong>{' '}
                    {visible(conversation.primary_goal)}
                  </p>
                )}
                {detail.messages.map((message) => (
                  <article
                    key={message.id}
                    className={`chat-message ${message.role}`}
                  >
                    <strong>
                      {message.role === 'user'
                        ? 'Tú'
                        : message.role === 'assistant'
                          ? 'Statia'
                          : 'Estado del plan'}
                    </strong>
                    <p>{visible(message.content)}</p>
                    {!!message.metadata.questions?.length && (
                      <ul>
                        {message.metadata.questions.map((question, i) => (
                          <li key={i}>{visible(question)}</li>
                        ))}
                      </ul>
                    )}
                    {!!message.metadata.warnings?.length && (
                      <ul className="muted">
                        {message.metadata.warnings.map((warning, i) => (
                          <li key={i}>{visible(warning)}</li>
                        ))}
                      </ul>
                    )}
                  </article>
                ))}
                {conversation.current_stage === 'reuse' && (
                  <div className="flow-card">
                    <h3>Archivos de tu conversación anterior</h3>
                    <ul>
                      {candidates.map((file) => (
                        <li key={file.id}>{file.original_name}</li>
                      ))}
                    </ul>
                    <div className="chat-actions">
                      <button
                        className="btn primary"
                        disabled={disabled || !!pending || !candidates.length}
                        onClick={() => send('reuse')}
                      >
                        Reutilizar archivos
                      </button>
                      <button
                        className="btn secondary"
                        disabled={disabled || !!pending}
                        onClick={() => send('new_files')}
                      >
                        Cargar archivos nuevos
                      </button>
                    </div>
                  </div>
                )}
                {conversation.current_stage === 'instrument' && (
                  <div className="chat-actions">
                    <button
                      className="btn primary"
                      disabled={disabled || !!pending}
                      onClick={() => send('instrument_yes')}
                    >
                      Sí, utilicé un instrumento
                    </button>
                    <button
                      className="btn secondary"
                      disabled={disabled || !!pending}
                      onClick={() => send('instrument_no')}
                    >
                      No tengo instrumento
                    </button>
                  </div>
                )}
                {detail.files.length > 0 && (
                  <section aria-label="Archivos relacionados">
                    <h3>Archivos relacionados</h3>
                    {detail.files.map((file) => (
                      <DatasetCard
                        key={file.id}
                        file={file}
                        busy={disabled}
                        onSheet={(sheet) =>
                          perform(async () => {
                            await chatService.sheet(project.id, file.id, sheet)
                            await understandIfReady(await refresh())
                          })
                        }
                        onDownload={() =>
                          perform(async () => {
                            await chatService.download(project.id, file)
                          })
                        }
                      />
                    ))}
                  </section>
                )}
                {conversation.current_stage !== 'instrument' &&
                  conversation.current_stage !== 'reuse' &&
                  unlinked.length > 0 && (
                    <details className="flow-card">
                      <summary>Reutilizar otros archivos del proyecto</summary>
                      {unlinked.map((file) => (
                        <label className="checkbox-label" key={file.id}>
                          <input
                            type="checkbox"
                            checked={reuseIds.includes(file.id)}
                            disabled={disabled || !!pending}
                            onChange={(e) =>
                              setReuseIds(
                                e.target.checked
                                  ? [...reuseIds, file.id]
                                  : reuseIds.filter((id) => id !== file.id),
                              )
                            }
                          />
                          {file.original_name}
                        </label>
                      ))}
                      <button
                        className="btn secondary"
                        disabled={disabled || !!pending || !reuseIds.length}
                        onClick={() => send('reuse', reuseIds)}
                      >
                        Asociar archivos seleccionados
                      </button>
                    </details>
                  )}
                {conversation.current_stage === 'upload_instrument' && (
                  <button
                    className="btn secondary"
                    disabled={disabled || !!pending}
                    onClick={() => send('instruments_done')}
                  >
                    Continuar con los datasets
                  </button>
                )}
                {detail.files.some((file) => file.metadata.profile) &&
                  [
                    'upload_dataset',
                    'understanding',
                    'upload_instrument',
                  ].includes(conversation.current_stage) && (
                    <button
                      className="btn primary"
                      disabled={
                        disabled ||
                        !!pending ||
                        detail.files.some(
                          (file) => file.metadata.needs_sheet_selection,
                        )
                      }
                      onClick={() => send('files_ready')}
                    >
                      Comprender archivos con Gemini
                    </button>
                  )}
                {conversation.stage_data.awaiting_reuse_update && (
                  <div className="chat-actions">
                    <button
                      className="btn primary"
                      disabled={disabled || !!pending}
                      onClick={() => answerReuse('No')}
                    >
                      No, continuar
                    </button>
                    <button
                      className="btn secondary"
                      disabled={disabled || !!pending}
                      onClick={() => answerReuse('Sí')}
                    >
                      Sí, añadir información
                    </button>
                  </div>
                )}
                {detail.proposals.length > 1 && (
                  <p className="notice">
                    Elige la propuesta que prefieras. Aceptarla conserva el
                    estado de las demás; todavía no se ejecutan análisis.
                  </p>
                )}
                {detail.proposals.map((proposal) => (
                  <ProposalCard
                    key={proposal.id}
                    proposal={proposal}
                    files={detail.files}
                    busy={disabled || !!pending}
                    onDecide={(status) =>
                      perform(async () => {
                        await chatService.decide(
                          project.id,
                          selected,
                          proposal.id,
                          status,
                        )
                        await refresh()
                      })
                    }
                  />
                ))}
                {conversation.stage_data.goal_change && (
                  <div className="flow-card">
                    <h3>¿Abrir otra conversación?</h3>
                    <p>{visible(conversation.stage_data.goal_change.reason)}</p>
                    <p>
                      El nuevo chat te permitirá elegir archivos para
                      reutilizar. Esta conversación conservará su finalidad.
                    </p>
                    <div className="chat-actions">
                      <button
                        className="btn primary"
                        disabled={disabled || !!pending}
                        onClick={() => create(conversation.id)}
                      >
                        Crear chat para la nueva finalidad
                      </button>
                      <button
                        className="btn secondary"
                        disabled={disabled || !!pending}
                        onClick={() => send('keep_goal')}
                      >
                        Seguir en esta conversación
                      </button>
                    </div>
                  </div>
                )}
              </div>
            </div>
            {unread && (
              <button className="new-messages" onClick={end}>
                Ver mensajes nuevos ↓
              </button>
            )}
            <ChatComposer
              key={conversation.id}
              text={text}
              disabled={disabled}
              busy={busy}
              busyLabel={busyLabel}
              pending={pending}
              samples={samples}
              instrumentText={instrumentText}
              onText={setText}
              onSend={() => {
                void send()
              }}
              onFiles={(files) => {
                void upload(files)
              }}
              onRetry={() => {
                if (pending)
                  void send(pending.action, pending.file_ids, pending)
              }}
              onDiscard={() => setPending(null)}
              onSamples={setSamples}
              onInstrumentText={setInstrumentText}
            />
          </>
        )}
      </section>
      {rename !== null && (
        <Modal
          title="Renombrar conversación"
          busy={busy}
          onClose={() => setRename(null)}
        >
          <form
            onSubmit={(e) => {
              e.preventDefault()
              void perform(async () => {
                await chatService.rename(project.id, selected, rename.trim())
                setRename(null)
                await refresh()
              })
            }}
          >
            <label>
              Título de la conversación
              <input
                autoFocus
                value={rename}
                maxLength={120}
                onChange={(e) => setRename(e.target.value)}
                required
              />
            </label>
            <button className="btn primary" disabled={busy || !rename.trim()}>
              Guardar título
            </button>
          </form>
        </Modal>
      )}
      {removing && (
        <Modal
          title="Eliminar conversación"
          busy={busy}
          onClose={() => setRemoving(false)}
        >
          <p>
            Se eliminarán «{visible(conversation?.title || '')}», sus mensajes y
            propuestas. Los archivos seguirán disponibles en el proyecto.
          </p>
          <button
            className="btn danger"
            disabled={busy}
            onClick={() =>
              perform(async () => {
                await chatService.remove(project.id, selected)
                setRemoving(false)
                setPending(null)
                await refresh('')
              })
            }
          >
            Confirmar eliminación
          </button>
        </Modal>
      )}
    </div>
  )
}
