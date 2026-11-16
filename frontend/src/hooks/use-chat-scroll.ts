import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from 'react'

export function useChatScroll(
  conversationId: string | undefined,
  firstId: string | undefined,
  latestId: string | undefined,
) {
  const viewport = useRef<HTMLDivElement | null>(null)
  const [mountVersion, setMountVersion] = useState(0)
  const transcript = useCallback((node: HTMLDivElement | null) => {
    viewport.current = node
    setMountVersion((version) => version + 1)
  }, [])
  const previous = useRef<{
    conversationId: string | undefined
    latestId: string | undefined
    node: HTMLDivElement | null
  }>({ conversationId, latestId, node: null })
  const follow = useRef(true)
  const prepend = useRef<{ height: number; top: number } | null>(null)
  const [unread, setUnread] = useState(false)
  const [resultTarget, setResultTarget] = useState<{
    id: string
    conversationId: string | undefined
  } | null>(null)
  const [unreadResult, setUnreadResult] = useState<{
    id: string
    conversationId: string | undefined
  } | null>(null)
  const processedResult = useRef<typeof resultTarget>(null)
  const revealResult = useCallback((id: string) => {
    const node = viewport.current
    const card = document.getElementById(`analysis-result-${id}`)
    if (!node || !card || !node.contains(card)) return false
    node.scrollTop +=
      card.getBoundingClientRect().top - node.getBoundingClientRect().top - 12
    card.focus({ preventScroll: true })
    follow.current = false
    setUnreadResult(null)
    setUnread(false)
    return true
  }, [])
  const end = useCallback(() => {
    const node = viewport.current
    if (node) node.scrollTop = node.scrollHeight
    follow.current = true
    setUnread(false)
  }, [])
  function onScroll() {
    const node = viewport.current
    if (!node) return
    follow.current = node.scrollHeight - node.scrollTop - node.clientHeight < 96
    if (follow.current) setUnread(false)
  }
  function capturePrepend() {
    const node = viewport.current
    if (node)
      prepend.current = { height: node.scrollHeight, top: node.scrollTop }
  }
  useLayoutEffect(() => {
    const node = viewport.current
    if (!node) return
    if (
      previous.current.conversationId !== conversationId ||
      previous.current.node !== node
    ) {
      prepend.current = null
      end()
    } else if (prepend.current) {
      node.scrollTop =
        prepend.current.top + node.scrollHeight - prepend.current.height
      prepend.current = null
    } else if (previous.current.latestId !== latestId) {
      if (follow.current) end()
      else setUnread(true)
    }
    previous.current = { conversationId, latestId, node }
  }, [mountVersion, conversationId, firstId, latestId, end])
  useEffect(() => {
    const node = viewport.current
    if (!node || typeof ResizeObserver === 'undefined') return
    const observer = new ResizeObserver(() => {
      if (follow.current && !prepend.current) end()
    })
    observer.observe(node)
    return () => observer.disconnect()
  }, [mountVersion, end])
  useLayoutEffect(() => {
    if (
      !resultTarget ||
      resultTarget.conversationId !== conversationId ||
      processedResult.current === resultTarget
    )
      return
    processedResult.current = resultTarget
    if (follow.current) revealResult(resultTarget.id)
    else setUnreadResult(resultTarget)
  }, [resultTarget, conversationId, latestId, revealResult])
  return {
    transcript,
    onScroll,
    capturePrepend,
    end,
    unread,
    unreadResult:
      unreadResult && unreadResult.conversationId === conversationId
        ? unreadResult.id
        : null,
    revealResult,
    resultAvailable: (id: string) => setResultTarget({ id, conversationId }),
    requestFollow: () => {
      follow.current = true
    },
  }
}
