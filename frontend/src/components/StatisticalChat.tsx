import { Fragment, useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  ChevronDown,
  MessageSquarePlus,
  PanelLeftClose,
  PanelLeftOpen,
} from 'lucide-react'
import { chatService } from '../services/chat'
import { ApiError } from '../lib/api'
import { visibleChatText } from '../lib/chat-text'
import { messageProvenance, providerName } from '../lib/assistant-provider'
import {
  AssistantProviderSelector,
  ProviderDisclosure,
} from './AssistantProviderSelector'
import type {
  AssistantProviderCatalog,
  AssistantProviderId,
} from '../types/chat'
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
import { ChatMarkdown } from './ChatMarkdown'
import { DatasetCard } from './DatasetCard'
import { ComponentStates } from './ComponentStates'
import { ProposalCard } from './ProposalCard'
import { ExecutionReview } from './ExecutionReview'
import { ExecutionPreparationCard } from './ExecutionPreparationCard'
import { AnalysisResultCard } from './AnalysisResultCard'
import { analysisService } from '../services/analysis'
import type { AnalysisRun, ExecuteRequest } from '../types/analysis'
import type { Proposal } from '../types/chat'
import { ChatComposer } from './ChatComposer'
import { ConversationHistory } from './ConversationHistory'
import { useChatScroll } from '../hooks/use-chat-scroll'

export function StatisticalChat({ project }: { project: Project }) {
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [projectFiles, setProjectFiles] = useState<ProjectFile[]>([])
  const [detail, setDetail] = useState<ConversationDetail | null>(null)
  const [latestRun, setLatestRun] = useState<AnalysisRun | null>(null)
  const [selected, setSelected] = useState('')
  const [loading, setLoading] = useState(true)
  const [opening, setOpening] = useState(false)
  const [busy, setBusy] = useState(false)
  const [reviewProposal, setReviewProposal] = useState<Proposal | null>(null)
  const [error, setError] = useState<Error | null>(null)
  const [text, setText] = useState('')
  const [pending, setPending] = useState<Turn | null>(null)
  const [retryConflict, setRetryConflict] = useState(false)
  const [providerCatalog, setProviderCatalog] =
    useState<AssistantProviderCatalog | null>(null)
  const [providersLoading, setProvidersLoading] = useState(true)
  const [providersError, setProvidersError] = useState<string | null>(null)
  const [catalogRevision, setCatalogRevision] = useState(0)
  const [providerChange, setProviderChange] =
    useState<AssistantProviderId | null>(null)
  const [providerUncertain, setProviderUncertain] = useState(false)
  const [creatingWithProvider, setCreatingWithProvider] = useState(false)
  const [newProvider, setNewProvider] = useState<AssistantProviderId>('gemini')
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
  const providerSelect = useRef<HTMLSelectElement>(null)
  const createProviderButton = useRef<HTMLButtonElement>(null)
  const providerDialogOpen = useRef(false)
  const creationDialogOpen = useRef(false)
  useEffect(() => {
    if (providerChange) providerDialogOpen.current = true
    else if (providerDialogOpen.current && !busy && !opening) {
      providerDialogOpen.current = false
      providerSelect.current?.focus({ preventScroll: true })
    }
    if (creatingWithProvider) creationDialogOpen.current = true
    else if (creationDialogOpen.current && !busy && !opening) {
      creationDialogOpen.current = false
      createProviderButton.current?.focus({ preventScroll: true })
    }
  }, [providerChange, creatingWithProvider, busy, opening])
  const temporaryHistory = useRef(false)
  useEffect(() => {
    if (temporaryHistory.current && !historyOpen)
      historyButton.current?.focus({ preventScroll: true })
    temporaryHistory.current = historyOpen && compact
  }, [historyOpen, compact])
  const {
    transcript,
    onScroll,
    capturePrepend,
    end,
    unread,
    requestFollow,
    unreadResult,
    revealResult,
    resultAvailable,
  } = useChatScroll(
    opening ? undefined : detail?.conversation.id,
    detail?.messages[0]?.id,
    detail?.messages.at(-1)?.id,
  )
  const generation = useRef(0)
  const selectedRef = useRef('')
  const mutation = useRef(false)
  const announcedResults = useRef(new Set<string>())

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
    setProviderUncertain(false)
    setSelected(id)
    selectedRef.current = id
    if (current?.retry_turn) setPending(current.retry_turn)
    return current
  }

  useEffect(() => {
    let active = true
    chatService
      .providers(project.id)
      .then((catalog) => {
        if (active) setProviderCatalog(catalog)
      })
      .catch(() => {
        if (active) {
          setProviderCatalog(null)
          setProvidersError(
            'No se pudo consultar la disponibilidad de proveedores.',
          )
        }
      })
      .finally(() => {
        if (active) setProvidersLoading(false)
      })
    return () => {
      active = false
    }
  }, [project.id, catalogRevision])

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
    setLatestRun(null)
    announcedResults.current.clear()
    setError(null)
    setPending(null)
    setRetryConflict(false)
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

  const create = (source?: string, provider: AssistantProviderId = 'gemini') =>
    perform(async () => {
      const conversation = await chatService.create(
        project.id,
        source,
        provider,
      )
      setCreatingWithProvider(false)
      setPending(null)
      setRetryConflict(false)
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
    if (!id || providerUncertain) return
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
    setRetryConflict(false)
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
      setPending(turn)
      if (caught instanceof ApiError && caught.status === 409)
        setRetryConflict(true)
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
    visibleChatText(value, detail?.files || projectFiles, [
      ...(detail?.messages.flatMap((message) =>
        message.metadata.analysis_run_id
          ? [message.metadata.analysis_run_id]
          : [],
      ) || []),
      ...(latestRun ? [latestRun.id] : []),
      ...(detail?.latest_analysis_run ? [detail.latest_analysis_run.id] : []),
    ])
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
  const disabled = busy || opening || providerUncertain
  const headingRun = latestRun || detail?.latest_analysis_run
  const lastAcceptance = [...(detail?.messages || [])]
    .reverse()
    .find((message) => message.metadata.status === 'accepted')
  const preparationPending =
    !!conversation?.stage_data.execution_preparation &&
    ['NEEDS_CLARIFICATION', 'BLOCKED_UNCERTAINTY', 'PARTIALLY_READY'].includes(
      conversation.stage_data.execution_preparation.result.status,
    )
  const showRunStatus =
    headingRun?.status === 'running' ||
    (conversation?.current_stage === 'ready' &&
      !!headingRun &&
      !preparationPending &&
      (!lastAcceptance ||
        lastAcceptance.metadata.proposal_id === headingRun.proposal_id))
  const selectedProvider = conversation?.assistant_provider ?? 'gemini'
  const providerBlocked =
    disabled ||
    !!pending ||
    !!reviewProposal ||
    providerUncertain ||
    !!conversation?.active_request_id ||
    detail?.latest_analysis_run?.status === 'running'
  const canChooseProvider = (id: AssistantProviderId) =>
    !providersLoading &&
    !providersError &&
    !!providerCatalog?.providers.some(
      (item) => item.id === id && item.enabled && item.configured,
    )
  const reloadProviders = () => {
    setProvidersLoading(true)
    setProvidersError(null)
    setCatalogRevision((value) => value + 1)
  }
  const providerSelectorProps = {
    catalog: providerCatalog,
    loading: providersLoading,
    error: providersError,
    onReload: reloadProviders,
  }
  const changeProvider = () =>
    perform(async () => {
      if (
        !conversation ||
        !providerChange ||
        providerBlocked ||
        !canChooseProvider(providerChange)
      )
        return
      try {
        const updated = await chatService.changeProvider(
          project.id,
          conversation.id,
          providerChange,
          selectedProvider,
        )
        setDetail((current) =>
          current ? { ...current, conversation: updated } : current,
        )
        setConversations((current) =>
          current.map((item) => (item.id === updated.id ? updated : item)),
        )
        setProviderChange(null)
        await refresh(updated.id)
      } catch (caught) {
        if (caught instanceof ApiError && caught.status === 0) {
          setProviderChange(null)
          setProviderUncertain(true)
          throw new Error(
            'No se pudo confirmar el cambio de proveedor. Recarga la conversación antes de continuar para comprobar qué selección guardó el servidor.',
          )
        }
        if (caught instanceof ApiError && caught.status === 409) {
          setProviderChange(null)
          setProviderUncertain(true)
          try {
            await refresh(conversation.id)
          } catch {
            throw new Error(
              'La selección cambió o hay una operación en curso. No se pudo recuperar el estado; recarga antes de continuar.',
            )
          }
          throw new Error(
            'La selección cambió o hay una operación en curso. Se recargó la conversación; revisa el proveedor confirmado antes de continuar.',
          )
        }
        throw caught
      }
    })
  async function executeAnalysis(body: ExecuteRequest, proposalId: string) {
    if (mutation.current)
      throw new Error('Espera a que termine la operación actual.')
    mutation.current = true
    setBusy(true)
    setBusyLabel('Python está calculando y guardando los resultados…')
    setError(null)
    requestFollow()
    try {
      const run = await analysisService.execute(
        project.id,
        selectedRef.current,
        proposalId,
        body,
      )
      setLatestRun(run)
      await refresh()
      resultAvailable(run.id)
    } catch (caught) {
      try {
        await refresh()
      } catch {
        /* Conserva las decisiones y el UUID para reintentar. */
      }
      throw caught
    } finally {
      mutation.current = false
      setBusy(false)
    }
  }
  const candidates = projectFiles.filter((file) =>
    conversation?.stage_data.reuse_file_ids?.includes(file.id),
  )
  const unlinked = projectFiles.filter(
    (file) => !detail?.files.some((linked) => linked.id === file.id),
  )
  function renderProposal(proposal: Proposal) {
    if (!detail || !conversation) return null
    const card = (
      <ProposalCard
        key={proposal.id}
        proposal={proposal}
        files={detail.files}
        busy={disabled || !!pending}
        prepared={
          conversation.stage_data.execution_preparation?.proposal_id ===
          proposal.id
        }
        onExecute={() =>
          perform(() =>
            submitTurn(selected, {
              request_id: crypto.randomUUID(),
              action: 'prepare_execution',
              content: '',
              file_ids: [],
              share_samples: false,
              share_instrument_text: false,
              proposal_id: proposal.id,
            }),
          )
        }
        onDecide={(status) =>
          perform(async () => {
            await chatService.decide(project.id, selected, proposal.id, status)
            await refresh()
          })
        }
      />
    )
    return proposal.status === 'proposed' ? (
      card
    ) : (
      <details className="historical-card">
        <summary>
          {proposal.status === 'accepted'
            ? 'Plan aceptado'
            : 'Propuesta rechazada'}
          : {visible(proposal.title)}
        </summary>
        {card}
      </details>
    )
  }
  const prepState = conversation?.stage_data.execution_preparation
  const preparationMessageId = detail?.messages.findLast(
    (m) =>
      m.metadata.execution_preparation?.fingerprint ===
      prepState?.result.fingerprint,
  )?.id
  const alreadyExecuted =
    (!!detail?.preparation_run &&
      detail.preparation_run.request_id === prepState?.result.request_id) ||
    detail?.messages.some(
      (m) => m.metadata.execution_request_id === prepState?.result.request_id,
    )
  const preparationCard = (() => {
    if (!detail || !conversation || !prepState || prepState.paused) return null
    const state = prepState
    const proposal = detail.proposals.find(
      (p) => p.id === state.proposal_id && p.status === 'accepted',
    )
    if (!proposal) return null
    const card = (
      <ExecutionPreparationCard
        key={`${conversation.id}:${state.proposal_id}:${state.result.fingerprint}`}
        preparation={state.result}
        proposal={proposal}
        projectId={project.id}
        conversationId={selected}
        busy={disabled || !!pending || !!alreadyExecuted}
        onAnswer={(questionId, answer, label) =>
          perform(() =>
            submitTurn(selected, {
              request_id: crypto.randomUUID(),
              action: 'clarify_execution',
              content: label,
              file_ids: [],
              share_samples: false,
              share_instrument_text: false,
              proposal_id: proposal.id,
              question_id: questionId,
              answer,
            }),
          )
        }
        onCancel={() => send('cancel_execution')}
        onReview={(questionId) =>
          perform(() =>
            submitTurn(selected, {
              request_id: crypto.randomUUID(),
              action: 'review_execution',
              content: '',
              file_ids: [],
              share_samples: false,
              share_instrument_text: false,
              proposal_id: proposal.id,
              question_id: questionId,
            }),
          )
        }
        onDescriptive={() =>
          perform(() =>
            submitTurn(selected, {
              request_id: crypto.randomUUID(),
              action: 'request_descriptive',
              content: '',
              file_ids: [],
              share_samples: false,
              share_instrument_text: false,
              proposal_id: proposal.id,
            }),
          )
        }
        onAdvanced={() => setReviewProposal(proposal)}
        onExecute={(body) => executeAnalysis(body, proposal.id)}
      />
    )
    return alreadyExecuted ? (
      <details className="historical-card">
        <summary>Preparación utilizada · ver decisiones</summary>
        <p>
          Esta preparación ya fue ejecutada. Vuelve a preparar el plan para
          revisar los componentes pendientes.
        </p>
        <div className="historical-preparation">{card}</div>
      </details>
    ) : (
      card
    )
  })()
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
          <span>{project.name}</span>
          <button
            className="icon-btn"
            ref={createProviderButton}
            aria-label="Elegir proveedor para nuevo chat"
            title="Elegir proveedor para nuevo chat"
            disabled={disabled}
            onClick={() => {
              setError(null)
              setNewProvider('gemini')
              setCreatingWithProvider(true)
            }}
          >
            <ChevronDown size={17} />
          </button>
          <button
            className="btn secondary"
            disabled={disabled}
            onClick={() => create()}
          >
            <MessageSquarePlus size={17} />
            Nuevo chat
          </button>
        </div>
        {error && !providerChange && !creatingWithProvider && (
          <Alert>
            {error.message}
            {error instanceof ApiError && error.status === 401 && (
              <Link to="/login"> Recuperar acceso</Link>
            )}
            <button
              disabled={busy || opening}
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
                <small>
                  {showRunStatus
                    ? {
                        running: 'Calculando',
                        partial: 'Análisis parcialmente completado',
                        completed: 'Análisis completado',
                        failed: 'Ejecución fallida',
                      }[(latestRun || detail.latest_analysis_run)!.status]
                    : conversation.stage_data.execution_preparation &&
                        [
                          'NEEDS_CLARIFICATION',
                          'BLOCKED_UNCERTAINTY',
                          'PARTIALLY_READY',
                        ].includes(
                          conversation.stage_data.execution_preparation.result
                            .status,
                        )
                      ? 'Preparación pendiente'
                      : stageLabel[conversation.current_stage]}
                </small>
              </div>
              <AssistantProviderSelector
                {...providerSelectorProps}
                selectRef={providerSelect}
                value={selectedProvider}
                disabled={providerBlocked}
                onSelect={(provider) => {
                  if (
                    !providerBlocked &&
                    provider !== selectedProvider &&
                    canChooseProvider(provider)
                  ) {
                    setError(null)
                    setProviderChange(provider)
                  }
                }}
              />
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
                  <Fragment key={message.id}>
                    {message.metadata.analysis_run_id ? (
                      <div
                        id={`analysis-result-${message.metadata.analysis_run_id}`}
                        tabIndex={-1}
                        className="result-anchor"
                      >
                        <AnalysisResultCard
                          key={message.id}
                          projectId={project.id}
                          runId={message.metadata.analysis_run_id}
                          initialRun={
                            latestRun?.id === message.metadata.analysis_run_id
                              ? latestRun
                              : undefined
                          }
                          onLoaded={(run) => {
                            const key = `${selected}:${run.id}`
                            if (
                              detail.messages.at(-1)?.metadata
                                .analysis_run_id === run.id &&
                              !announcedResults.current.has(key)
                            ) {
                              announcedResults.current.add(key)
                              if (latestRun?.id !== run.id)
                                resultAvailable(run.id)
                            }
                          }}
                          preparation={
                            conversation.stage_data.execution_preparation &&
                            conversation.stage_data.execution_preparation
                              .proposal_id === message.metadata.proposal_id
                              ? conversation.stage_data.execution_preparation
                                  .result
                              : conversation.stage_data
                                  .execution_preparations?.[
                                  message.metadata.proposal_id || ''
                                ]?.result
                          }
                          busy={disabled || !!pending}
                          onAnswer={(proposalId, questionId, answer, label) =>
                            perform(() =>
                              submitTurn(selected, {
                                request_id: crypto.randomUUID(),
                                action: 'clarify_execution',
                                content: label,
                                file_ids: [],
                                share_samples: false,
                                share_instrument_text: false,
                                proposal_id: proposalId,
                                question_id: questionId,
                                answer,
                              }),
                            )
                          }
                          onPrepare={(proposalId) =>
                            perform(() =>
                              submitTurn(selected, {
                                request_id: crypto.randomUUID(),
                                action: 'prepare_execution',
                                content: '',
                                file_ids: [],
                                share_samples: false,
                                share_instrument_text: false,
                                proposal_id: proposalId,
                              }),
                            )
                          }
                        />
                      </div>
                    ) : (
                      <article
                        key={message.id}
                        className={`chat-message ${message.role}`}
                      >
                        <strong>
                          {message.role === 'user'
                            ? 'Tú'
                            : message.role === 'assistant'
                              ? 'Statia'
                              : message.metadata.event === 'provider_selected'
                                ? 'Statia'
                                : 'Estado del plan'}
                        </strong>
                        {messageProvenance(message) && (
                          <small className="message-provenance">
                            {messageProvenance(message)}
                          </small>
                        )}
                        {message.role === 'assistant' ? (
                          <ChatMarkdown>
                            {visible(message.content)}
                          </ChatMarkdown>
                        ) : (
                          <p>{visible(message.content)}</p>
                        )}
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
                    )}
                    {detail.proposals
                      .filter((p) => p.source_message_id === message.id)
                      .map((p) => (
                        <Fragment key={p.id}>{renderProposal(p)}</Fragment>
                      ))}
                    {message.id === preparationMessageId
                      ? preparationCard
                      : message.metadata.execution_preparation && (
                          <details className="historical-card">
                            <summary>Preparación anterior · ver estado</summary>
                            <p>
                              {
                                {
                                  READY: 'Listo para ejecutar',
                                  PARTIALLY_READY: 'Componentes disponibles',
                                  COMPLETED: 'Completado',
                                  NEEDS_CLARIFICATION: 'Aclaración pendiente',
                                  BLOCKED_UNCERTAINTY:
                                    'Detenido por incertidumbre',
                                  UNSUPPORTED: 'Necesita revisión',
                                }[message.metadata.execution_preparation.status]
                              }
                            </p>
                            <ComponentStates
                              components={
                                message.metadata.execution_preparation
                                  .components || []
                              }
                              projectId={project.id}
                            />
                          </details>
                        )}
                    {message.metadata.file_ids?.map((id) => {
                      const file = detail.files.find((f) => f.id === id)
                      return file ? (
                        <p key={id} className="notice">
                          Archivo: {file.original_name}
                        </p>
                      ) : null
                    })}
                  </Fragment>
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
                {detail.files
                  .filter(
                    (file) =>
                      file.file_type === 'xlsx' && file.metadata.profile,
                  )
                  .map((file) => (
                    <p className="muted" key={`xlsx-profile-${file.id}`}>
                      {file.original_name} · Hoja:{' '}
                      {file.metadata.selected_sheet} ·{' '}
                      {file.metadata.profile!.row_count} filas ·{' '}
                      {file.metadata.profile!.column_count} columnas
                    </p>
                  ))}
                {detail.files.some(
                  (file) => file.metadata.needs_sheet_selection,
                ) && (
                  <p className="notice" role="status">
                    Selecciona una hoja de cada Excel pendiente en los archivos
                    relacionados que se muestran abajo. Después continuaremos
                    con la comprensión. No se combinan hojas.
                  </p>
                )}
                {detail.files.length > 0 && (
                  <details
                    className="historical-card"
                    aria-label="Archivos relacionados"
                    open={
                      detail.files.some(
                        (file) => file.metadata.needs_sheet_selection,
                      ) || undefined
                    }
                  >
                    <summary>
                      Archivos relacionados ({detail.files.length})
                    </summary>
                    <h3>Archivos relacionados</h3>
                    {detail.files.map((file) => (
                      <DatasetCard
                        key={file.id}
                        file={file}
                        busy={disabled}
                        expanded={file.metadata.needs_sheet_selection}
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
                  </details>
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
                      {conversation.stage_data.context_summary
                        ? 'Volver a comprender archivos con '
                        : 'Comprender archivos con '}
                      {providerName(selectedProvider)}
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
                {detail.proposals.some((p) => !p.source_message_id) && (
                  <details className="historical-card">
                    <summary>
                      Propuestas anteriores sin posición registrada
                    </summary>
                    <p className="muted">
                      Este historial antiguo no registra el mensaje de origen.
                    </p>
                    {detail.proposals
                      .filter((p) => !p.source_message_id)
                      .map((p) => (
                        <Fragment key={p.id}>{renderProposal(p)}</Fragment>
                      ))}
                  </details>
                )}
                {!preparationMessageId && preparationCard}
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
            {unreadResult ? (
              <button
                className="new-messages"
                onClick={() => revealResult(unreadResult)}
              >
                Ver resultado disponible ↓
              </button>
            ) : (
              unread && (
                <button className="new-messages" onClick={end}>
                  Ver mensajes nuevos ↓
                </button>
              )
            )}
            <ChatComposer
              key={conversation.id}
              text={text}
              disabled={disabled}
              busy={busy}
              busyLabel={busyLabel}
              pending={pending}
              provider={selectedProvider}
              retryConflict={retryConflict}
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
              onDiscard={() => {
                setPending(null)
                setRetryConflict(false)
              }}
              onSamples={setSamples}
              onInstrumentText={setInstrumentText}
            />
          </>
        )}
      </section>
      {providerChange && (
        <Modal
          title="Cambiar proveedor del asistente"
          busy={busy}
          onClose={() => setProviderChange(null)}
        >
          <ProviderDisclosure provider={providerChange} />
          {error && <Alert>{error.message}</Alert>}
          <p>
            El cambio conserva el historial, archivos, planes, resultados y
            decisiones.
          </p>
          <div className="chat-actions">
            <button
              className="btn secondary"
              disabled={busy}
              onClick={() => setProviderChange(null)}
            >
              Cancelar cambio
            </button>
            <button
              className="btn primary"
              disabled={providerBlocked || !canChooseProvider(providerChange)}
              onClick={() => void changeProvider()}
            >
              Confirmar cambio a {providerName(providerChange)}
            </button>
          </div>
        </Modal>
      )}
      {creatingWithProvider && (
        <Modal
          title="Nueva conversación · proveedor"
          busy={busy}
          onClose={() => setCreatingWithProvider(false)}
        >
          {error && <Alert>{error.message}</Alert>}
          <AssistantProviderSelector
            {...providerSelectorProps}
            label="Proveedor de la nueva conversación"
            value={newProvider}
            disabled={busy}
            onSelect={(provider) => {
              if (canChooseProvider(provider)) setNewProvider(provider)
            }}
          />
          {newProvider === 'openai' ? (
            <ProviderDisclosure provider={newProvider} />
          ) : (
            <p>
              Gemini es el proveedor predeterminado. También puedes crear un
              chat directamente con «Nuevo chat».
            </p>
          )}
          <p>Crear la conversación no envía mensajes al proveedor.</p>
          <div className="chat-actions">
            <button
              className="btn secondary"
              disabled={busy}
              onClick={() => setCreatingWithProvider(false)}
            >
              Cancelar creación
            </button>
            <button
              className="btn primary"
              disabled={
                busy ||
                (newProvider !== 'gemini' && !canChooseProvider(newProvider))
              }
              onClick={() => void create(undefined, newProvider)}
            >
              {newProvider === 'openai'
                ? 'Confirmar y crear con Terra (OpenAI)'
                : 'Crear con Gemini'}
            </button>
          </div>
        </Modal>
      )}
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
      {reviewProposal && detail && (
        <ExecutionReview
          key={reviewProposal.id}
          projectId={project.id}
          conversationId={selected}
          proposal={reviewProposal}
          files={detail.files}
          busy={busy}
          onClose={() => setReviewProposal(null)}
          initialSpecification={
            conversation?.stage_data.execution_preparation?.proposal_id ===
              reviewProposal.id &&
            conversation.stage_data.execution_preparation.result.status ===
              'READY'
              ? conversation.stage_data.execution_preparation.result
                  .specification
              : null
          }
          onExecute={(body) => executeAnalysis(body, reviewProposal.id)}
        />
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
