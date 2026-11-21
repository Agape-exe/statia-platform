import type {
  AssistantProvider,
  AssistantProviderId,
  Message,
} from '../types/chat'

export const providerName = (id: AssistantProviderId) =>
  id === 'openai' ? 'Terra (OpenAI)' : 'Gemini'

export function providerAvailability(provider: AssistantProvider) {
  if (!provider.enabled) return 'Deshabilitado'
  if (!provider.configured) return 'No configurado'
  return 'Disponible'
}

export function messageProvenance(message: Message): string | null {
  if (message.role === 'user') return null
  const generation = message.metadata.generation ?? message.generation
  if (message.metadata.event === 'provider_selected')
    return 'Cambio de proveedor · Statia'
  if (
    generation?.source === 'deterministic' ||
    message.metadata.source === 'deterministic'
  )
    return 'Información del sistema'
  if (message.message_type === 'event' || message.role === 'system')
    return 'Información del sistema'
  // La selección por sí sola no acredita que haya intervenido un modelo.
  const provider = generation?.provider
  if (provider !== 'gemini' && provider !== 'openai') return 'Statia'
  const name = provider === 'openai' ? 'Terra' : 'Gemini'
  return name
}
