import { useId, type Ref } from 'react'
import type {
  AssistantProviderCatalog,
  AssistantProviderId,
} from '../types/chat'
import { providerAvailability, providerName } from '../lib/assistant-provider'

export function AssistantProviderSelector({
  catalog,
  loading,
  error,
  value,
  disabled,
  onSelect,
  onReload,
  label = 'Proveedor del asistente',
  selectRef,
}: {
  catalog: AssistantProviderCatalog | null
  loading: boolean
  error: string | null
  value: AssistantProviderId
  disabled: boolean
  onSelect: (id: AssistantProviderId) => void
  onReload: () => void
  label?: string
  selectRef?: Ref<HTMLSelectElement>
}) {
  const id = useId()
  const provider = catalog?.providers.find((item) => item.id === value)
  return (
    <div className="provider-selector" aria-busy={loading}>
      <label htmlFor={id}>{label}</label>
      <select
        ref={selectRef}
        id={id}
        value={value}
        disabled={disabled || loading || !catalog || !!error}
        aria-describedby={`${id}-status`}
        onChange={(event) =>
          onSelect(event.target.value as AssistantProviderId)
        }
      >
        {!provider && <option value={value}>{providerName(value)}</option>}
        {catalog?.providers.map((item) => (
          <option
            key={item.id}
            value={item.id}
            disabled={!item.enabled || !item.configured}
          >
            {item.name}
            {item.experimental ? ' · Experimental' : ''}
            {(!item.enabled || !item.configured) &&
              ` · ${providerAvailability(item)}`}
          </option>
        ))}
      </select>
      <small id={`${id}-status`} aria-live="polite">
        {loading
          ? 'Cargando proveedores…'
          : error
            ? error
            : provider
              ? `${provider.model} · ${providerAvailability(provider)}${provider.experimental ? ' · Experimental' : ''}`
              : 'Proveedor ausente del catálogo. Recarga la disponibilidad.'}
      </small>
      {(error || (!loading && !provider)) && (
        <button
          type="button"
          className="provider-reload"
          disabled={disabled || loading}
          onClick={onReload}
        >
          Recargar proveedores
        </button>
      )}
    </div>
  )
}

export function ProviderDisclosure({
  provider,
}: {
  provider: AssistantProviderId
}) {
  return (
    <p className="provider-disclosure">
      {providerName(provider)} recibirá los próximos mensajes y el contexto
      compartido de esta conversación. Este contexto puede incluir historial
      anterior, perfiles de datasets, Contexto de tesis y resultados agregados.
      Las muestras pequeñas conservan su ajuste. Los instrumentos PDF y DOCX
      requieren autorización para el proveedor de destino.
      {provider === 'openai' && ' Terra es experimental.'}
    </p>
  )
}
