import { useEffect, useLayoutEffect, useRef } from 'react'
import { LoaderCircle, Paperclip, Send } from 'lucide-react'
import type { Turn } from '../types/chat'

export function ChatComposer({
  text,
  disabled,
  busy,
  busyLabel,
  pending,
  samples,
  instrumentText,
  onText,
  onSend,
  onFiles,
  onRetry,
  onDiscard,
  onSamples,
  onInstrumentText,
}: {
  text: string
  disabled: boolean
  busy: boolean
  busyLabel: string
  pending: Turn | null
  samples: boolean
  instrumentText: boolean
  onText: (value: string) => void
  onSend: () => void
  onFiles: (files: File[]) => void
  onRetry: () => void
  onDiscard: () => void
  onSamples: (value: boolean) => void
  onInstrumentText: (value: boolean) => void
}) {
  const textarea = useRef<HTMLTextAreaElement>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const composing = useRef(false)
  const returnFocus = useRef(false)
  const canSend = !disabled && !pending && !!text.trim()
  function resize() {
    const node = textarea.current
    if (!node) return
    node.style.height = 'auto'
    node.style.height = `${Math.min(node.scrollHeight + 2, 160)}px`
  }
  useLayoutEffect(resize, [text])
  useEffect(() => {
    window.addEventListener('resize', resize)
    return () => window.removeEventListener('resize', resize)
  }, [])
  useEffect(() => {
    if (!busy && !disabled && !pending && returnFocus.current) {
      if (
        document.activeElement === document.body ||
        document.activeElement === textarea.current
      )
        textarea.current?.focus({ preventScroll: true })
      returnFocus.current = false
    }
  }, [busy, disabled, pending])
  function submit() {
    if (!canSend || composing.current) return
    returnFocus.current = document.activeElement === textarea.current
    onSend()
  }
  return (
    <form
      className="chat-composer"
      aria-label="Compositor de mensajes"
      onSubmit={(event) => {
        event.preventDefault()
        submit()
      }}
    >
      {pending && !busy && (
        <div className="retry-turn" role="status">
          Tu solicitud no se completó. Puedes reintentar sin duplicar el
          mensaje.
          <div className="chat-actions">
            <button type="button" className="btn secondary" onClick={onRetry}>
              Reintentar solicitud
            </button>
            <button type="button" className="btn secondary" onClick={onDiscard}>
              Escribir otra solicitud
            </button>
          </div>
        </div>
      )}
      {busy && (
        <p className="composer-status" role="status">
          <LoaderCircle size={16} className="spin" aria-hidden="true" />
          {busyLabel}
        </p>
      )}
      <div className="composer-input-row">
        <input
          ref={fileInput}
          type="file"
          multiple
          hidden
          aria-label="Archivos para adjuntar"
          accept=".csv,.xlsx,.json,.pdf"
          onChange={(event) => {
            const files = Array.from(event.target.files || [])
            event.target.value = ''
            if (files.length) onFiles(files)
          }}
        />
        <button
          type="button"
          className="icon-btn attachment-button"
          aria-label="Adjuntar archivos"
          title="Adjuntar CSV, XLSX, JSON o PDF (10 MB por archivo por defecto)"
          disabled={disabled || !!pending}
          onClick={() => fileInput.current?.click()}
        >
          <Paperclip size={20} aria-hidden="true" />
        </button>
        <label className="composer-label">
          <span className="sr-only">Mensaje para Statia</span>
          <textarea
            ref={textarea}
            value={text}
            onChange={(event) => onText(event.target.value)}
            rows={1}
            maxLength={6000}
            disabled={disabled || !!pending}
            placeholder="Pregunta sobre tus datos…"
            aria-describedby="composer-hint"
            onCompositionStart={() => {
              composing.current = true
            }}
            onCompositionEnd={() => {
              composing.current = false
            }}
            onKeyDown={(event) => {
              if (
                event.key !== 'Enter' ||
                event.shiftKey ||
                event.nativeEvent.isComposing ||
                composing.current ||
                event.keyCode === 229
              )
                return
              event.preventDefault()
              submit()
            }}
          />
        </label>
        <button
          className="btn primary send-button"
          type="submit"
          disabled={!canSend}
          aria-label="Enviar"
          title="Enviar mensaje"
        >
          <Send size={19} aria-hidden="true" />
          <span>Enviar</span>
        </button>
      </div>
      <div className="composer-footer">
        <details className="privacy-options">
          <summary>Información compartida con Gemini</summary>
          <div className="privacy-content">
            <p>
              Se envían mensajes y resúmenes de columnas. Evita información
              personal o secretos. Los archivos completos permanecen en el
              almacenamiento privado.
            </p>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={samples}
                disabled={disabled}
                onChange={(event) => onSamples(event.target.checked)}
              />
              Compartir muestras pequeñas sin identificadores detectados
            </label>
            <label className="checkbox-label">
              <input
                type="checkbox"
                checked={instrumentText}
                disabled={disabled}
                onChange={(event) => onInstrumentText(event.target.checked)}
              />
              Compartir extractos de instrumentos PDF
            </label>
            <small>
              La detección de datos sensibles es parcial. Revisa tus archivos
              antes de habilitar estas opciones.
            </small>
          </div>
        </details>
        <span id="composer-hint">
          Enter envía · Shift + Enter añade una línea
        </span>
      </div>
    </form>
  )
}
