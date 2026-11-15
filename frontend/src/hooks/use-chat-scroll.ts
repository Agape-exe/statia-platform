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
  return {
    transcript,
    onScroll,
    capturePrepend,
    end,
    unread,
    requestFollow: () => {
      follow.current = true
    },
  }
}
