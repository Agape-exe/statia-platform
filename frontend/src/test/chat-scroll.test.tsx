import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useChatScroll } from '../hooks/use-chat-scroll'

let height = 1000
function Transcript({
  id,
  first = 'first',
  last = 'last',
  mounted = true,
}: {
  id: string | undefined
  first?: string
  last?: string
  mounted?: boolean
}) {
  const { transcript, onScroll, capturePrepend, end, unread } = useChatScroll(
    id,
    first,
    last,
  )
  return (
    <>
      <button onClick={capturePrepend}>Antes de paginar</button>
      <button onClick={end}>Ir al final</button>
      {unread && <span>Hay mensajes nuevos</span>}
      {mounted && (
        <div aria-label="Transcripción" ref={transcript} onScroll={onScroll} />
      )}
    </>
  )
}

beforeEach(() => {
  vi.spyOn(HTMLElement.prototype, 'scrollHeight', 'get').mockImplementation(
    () => height,
  )
  vi.spyOn(HTMLElement.prototype, 'clientHeight', 'get').mockReturnValue(200)
})
afterEach(() => vi.restoreAllMocks())

describe('desplazamiento local de mensajes', () => {
  it('abre abajo incluso si el panel se monta después de terminar la carga', () => {
    height = 1000
    const view = render(<Transcript id="a" />)
    expect(screen.getByLabelText('Transcripción').scrollTop).toBe(1000)
    view.rerender(<Transcript id={undefined} mounted={false} />)
    view.rerender(<Transcript id="b" mounted={false} />)
    view.rerender(<Transcript id="b" />)
    expect(screen.getByLabelText('Transcripción').scrollTop).toBe(1000)
  })
  it('sigue cerca del final pero conserva la lectura y avisa cuando el usuario sube', () => {
    height = 1000
    const view = render(<Transcript id="a" />)
    const node = screen.getByLabelText('Transcripción')
    node.scrollTop = 780
    fireEvent.scroll(node)
    height = 1200
    view.rerender(<Transcript id="a" last="new1" />)
    expect(node.scrollTop).toBe(1200)
    node.scrollTop = 200
    fireEvent.scroll(node)
    height = 1400
    view.rerender(<Transcript id="a" last="new2" />)
    expect(node.scrollTop).toBe(200)
    expect(screen.getByText('Hay mensajes nuevos')).toBeInTheDocument()
    fireEvent.click(screen.getByText('Ir al final'))
    expect(node.scrollTop).toBe(1400)
    expect(screen.queryByText('Hay mensajes nuevos')).not.toBeInTheDocument()
  })
  it('compensa la altura de mensajes anteriores sin saltar al final', () => {
    height = 1000
    const view = render(<Transcript id="a" />)
    const node = screen.getByLabelText('Transcripción')
    node.scrollTop = 120
    fireEvent.scroll(node)
    fireEvent.click(screen.getByText('Antes de paginar'))
    height = 1500
    act(() => view.rerender(<Transcript id="a" first="older" />))
    expect(node.scrollTop).toBe(620)
  })
})
