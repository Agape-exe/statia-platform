import { useEffect, useState } from 'react'
import type { FormEvent } from 'react'
import { researchContextService } from '../services/research-context'
import {
  contextFields,
  emptyContext,
  parseResearchContext,
  contextFingerprint,
} from '../lib/research-context'
import { errorMessage } from '../lib/errors'
import type {
  ResearchContextDocument,
  SavedResearchContext,
} from '../types/research-context'
import { Alert, Loading } from './ui'
import { Modal } from './Modal'

const contextError = (error: unknown) =>
  error instanceof Error ? error.message : errorMessage(error)

export function ThesisContext({ projectId }: { projectId: string }) {
  const [saved, setSaved] = useState<SavedResearchContext | null>(null)
  const [draft, setDraft] = useState(emptyContext)
  const [extras, setExtras] = useState('{}')
  const [importText, setImportText] = useState('')
  const [review, setReview] = useState<ResearchContextDocument | null>(null)
  const [loading, setLoading] = useState(true)
  const [loaded, setLoaded] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [importNotice, setImportNotice] = useState('')
  const [notice, setNotice] = useState('')
  const [retry, setRetry] = useState(0)

  function currentDocument() {
    const cleaned = { ...draft }
    for (const field of contextFields) {
      if (field.list)
        cleaned[field.key] = draft[field.key]
          .map((item) => item.trim())
          .filter(Boolean)
      else cleaned[field.key] = draft[field.key]?.trim() || null
    }
    return parseResearchContext(
      JSON.stringify({
        ...cleaned,
        additional_fields: JSON.parse(extras) as unknown,
      }),
    )
  }
  let changed = true
  try {
    changed =
      contextFingerprint(currentDocument()) !==
      contextFingerprint(saved?.document ?? emptyContext())
  } catch {
    /* Un borrador inválido sigue siendo un cambio que requiere revisión. */
  }

  useEffect(() => {
    let active = true
    researchContextService
      .get(projectId)
      .then(({ context }) => {
        if (!active) return
        setSaved(context)
        setLoaded(true)
        setDraft(context?.document ?? emptyContext())
        setExtras(
          JSON.stringify(context?.document.additional_fields ?? {}, null, 2),
        )
        setError(null)
        setNotice('')
      })
      .catch((err) => {
        if (active) setError(contextError(err))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [projectId, retry])

  function importDraft(text = importText) {
    try {
      const document = parseResearchContext(text)
      setDraft(document)
      setExtras(JSON.stringify(document.additional_fields, null, 2))
      setReview(null)
      setError(null)
      setImportNotice(
        'Contexto importado correctamente. Revisa los campos antes de guardar.',
      )
      setNotice('Borrador importado; todavía no se ha guardado.')
    } catch (err) {
      setError(contextError(err))
    }
  }

  function prepareReview(event: FormEvent) {
    event.preventDefault()
    try {
      const document = currentDocument()
      if (!changed) return
      setReview(document)
      setError(null)
    } catch (err) {
      setError(
        err instanceof SyntaxError
          ? 'Los campos adicionales deben ser un objeto JSON válido.'
          : contextError(err),
      )
    }
  }

  async function save() {
    if (!review || busy) return
    setBusy(true)
    setError(null)
    try {
      const { context } = await researchContextService.save(
        projectId,
        review,
        saved?.revision ?? 0,
      )
      setSaved(context)
      setImportNotice('')
      setDraft(context.document)
      setExtras(JSON.stringify(context.document.additional_fields, null, 2))
      setReview(null)
      setNotice(
        'Contexto guardado. Las próximas consultas del asistente usarán esta revisión; los resultados históricos se conservan.',
      )
    } catch (err) {
      setReview(null)
      setError(contextError(err))
    } finally {
      setBusy(false)
    }
  }

  if (loading) return <Loading />
  return (
    <section className="thesis-context">
      {error && (
        <Alert>
          {error} El borrador se conserva.{' '}
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              if (
                window.confirm(
                  'Recargar reemplazará tu borrador con la versión guardada. ¿Continuar?',
                )
              ) {
                setLoading(true)
                setRetry((value) => value + 1)
              }
            }}
          >
            Recargar versión guardada
          </button>
        </Alert>
      )}
      {notice && (
        <div className="notice" role="status">
          {notice}
        </div>
      )}
      <p className="muted">
        {saved
          ? `Contexto confirmado · Revisión ${saved.revision} · ${new Date(saved.updated_at).toLocaleString('es-PE')}`
          : 'Todavía no hay contexto guardado.'}{' '}
        Todos los campos son opcionales. Deja vacía la información desconocida;
        no necesitas formular hipótesis si tu estudio no las tiene.
      </p>
      <p role="status">
        {changed
          ? 'Borrador modificado; los cambios aún no están guardados.'
          : saved
            ? 'Sin cambios pendientes.'
            : 'Completa o importa el contexto para revisarlo.'}
      </p>
      <p className="muted">
        El contexto confirmado se comparte con el asistente para orientar
        recomendaciones. Revisa su contenido y evita incluir datos personales,
        contraseñas o información confidencial.
      </p>
      <details className="context-import">
        {importNotice && (
          <div className="notice" role="status">
            {importNotice}
          </div>
        )}
        <summary>Importar contexto desde JSON</summary>
        <p>
          Usa el prompt maestro con tu información metodológica. Importar
          reemplaza el borrador completo para revisarlo; no guarda
          automáticamente.
        </p>
        <a className="back-link" href="/contexto-tesis-prompt.md" download>
          Descargar prompt maestro y contrato JSON
        </a>
        <label>
          Archivo JSON (hasta 100 KB)
          <input
            type="file"
            accept=".json,application/json"
            disabled={busy}
            onChange={(event) => {
              const file = event.target.files?.[0]
              event.target.value = ''
              if (!file) return
              if (file.size > 100000) {
                setError('El archivo supera los 100 KB permitidos.')
                return
              }
              void file
                .text()
                .then((text) => importDraft(text))
                .catch(() => setError('No se pudo leer el archivo JSON.'))
            }}
          />
        </label>
        <label>
          JSON estructurado
          <textarea
            rows={8}
            value={importText}
            maxLength={100000}
            disabled={busy}
            onChange={(event) => setImportText(event.target.value)}
            placeholder={'{"schema_version": 1, "research_title": null}'}
          />
        </label>
        <button
          className="btn secondary"
          type="button"
          disabled={busy || !importText.trim()}
          onClick={() => importDraft()}
        >
          Cargar importación para revisar
        </button>
      </details>
      <form className="project-form context-form" onSubmit={prepareReview}>
        <fieldset disabled={busy || !loaded}>
          {contextFields.map((field) => (
            <label key={field.key}>
              {field.label}
              {field.list && (
                <small className="muted">
                  Un elemento por línea; hasta 20 elementos de 500 caracteres.
                </small>
              )}
              <textarea
                rows={field.key === 'research_title' ? 2 : 3}
                maxLength={field.list ? 10020 : 2000}
                value={
                  field.list
                    ? draft[field.key].join('\n')
                    : (draft[field.key] ?? '')
                }
                onChange={(event) => {
                  const value = event.target.value
                  setDraft((current) => ({
                    ...current,
                    [field.key]: field.list ? value.split('\n') : value || null,
                  }))
                  setNotice('')
                }}
              />
            </label>
          ))}
          <label>
            Campos adicionales de tu disciplina (JSON)
            <small className="muted">
              Objeto con nombres propios y valores de texto o null. Usa {'{}'}{' '}
              si no hay otros campos.
            </small>
            <textarea
              rows={4}
              value={extras}
              maxLength={16000}
              onChange={(event) => {
                setExtras(event.target.value)
                setNotice('')
              }}
            />
          </label>
        </fieldset>
        <button
          className="btn primary"
          disabled={busy || !loaded || !changed}
          type="submit"
        >
          Revisar antes de guardar
        </button>
      </form>
      {review && (
        <Modal
          title="Revisar contexto de tesis"
          busy={busy}
          onClose={() => {
            if (!busy) setReview(null)
          }}
        >
          <p>
            Confirma que estos datos describen tu estudio. Guardar reemplazará
            el contexto vigente del proyecto, sin cambiar resultados ni planes
            históricos.
          </p>
          <dl className="context-review">
            {contextFields.map((field) => (
              <div key={field.key}>
                <dt>{field.label}</dt>
                <dd>
                  {field.list
                    ? review[field.key].join('\n') ||
                      'Sin información proporcionada'
                    : review[field.key] || 'Sin información proporcionada'}
                </dd>
              </div>
            ))}
            {Object.entries(review.additional_fields).map(([key, value]) => (
              <div key={key}>
                <dt>{key}</dt>
                <dd>{value || 'Sin información proporcionada'}</dd>
              </div>
            ))}
          </dl>
          <div className="form-actions">
            <button
              className="btn secondary"
              disabled={busy}
              onClick={() => setReview(null)}
            >
              Volver a editar
            </button>
            <button
              className="btn primary"
              disabled={busy}
              onClick={() => void save()}
            >
              {busy ? 'Guardando…' : 'Confirmar y guardar contexto'}
            </button>
          </div>
        </Modal>
      )}
    </section>
  )
}
