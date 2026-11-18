import { api } from '../lib/api'
import type {
  AssistantProviderCatalog,
  AssistantProviderId,
  Conversation,
  ConversationDetail,
  Message,
  ProjectFile,
  Turn,
} from '../types/chat'

const base = (projectId: string) => `/projects/${encodeURIComponent(projectId)}`
const chat = (projectId: string, conversationId: string) =>
  `${base(projectId)}/conversations/${encodeURIComponent(conversationId)}`
export const chatService = {
  providers: (projectId: string) =>
    api<AssistantProviderCatalog>(`${base(projectId)}/assistant-providers`),
  changeProvider: (
    projectId: string,
    id: string,
    provider: AssistantProviderId,
    expectedProvider: AssistantProviderId,
  ) =>
    api<Conversation>(`${chat(projectId, id)}/provider`, {
      method: 'PATCH',
      body: JSON.stringify({ provider, expected_provider: expectedProvider }),
    }),
  list: (projectId: string) =>
    api<Conversation[]>(`${base(projectId)}/conversations`),
  create: (
    projectId: string,
    sourceConversationId?: string,
    provider: AssistantProviderId = 'gemini',
  ) =>
    api<Conversation>(`${base(projectId)}/conversations`, {
      method: 'POST',
      body: JSON.stringify({
        source_conversation_id: sourceConversationId,
        provider,
      }),
    }),
  get: (projectId: string, id: string) =>
    api<ConversationDetail>(chat(projectId, id)),
  earlier: (projectId: string, id: string, before: number) =>
    api<{ messages: Message[]; has_more_messages: boolean }>(
      `${chat(projectId, id)}/messages?before=${before}`,
    ),
  rename: (projectId: string, id: string, title: string) =>
    api<Conversation>(chat(projectId, id), {
      method: 'PATCH',
      body: JSON.stringify({ title }),
    }),
  remove: (projectId: string, id: string) =>
    api<void>(chat(projectId, id), { method: 'DELETE' }),
  turn: (projectId: string, id: string, turn: Turn) =>
    api(chat(projectId, id) + '/turns', {
      method: 'POST',
      body: JSON.stringify(turn),
    }),
  files: (projectId: string) => api<ProjectFile[]>(`${base(projectId)}/files`),
  upload: (projectId: string, id: string, file: File, role: string) => {
    const form = new FormData()
    form.append('file', file)
    form.append('file_role', role)
    return api<ProjectFile>(chat(projectId, id) + '/files', {
      method: 'POST',
      body: form,
    })
  },
  sheet: (projectId: string, id: string, title: string) =>
    api<ProjectFile>(`${base(projectId)}/files/${id}/sheet`, {
      method: 'PUT',
      body: JSON.stringify({ title }),
    }),
  decide: (
    projectId: string,
    id: string,
    proposalId: string,
    status: 'accepted' | 'rejected',
  ) =>
    api(chat(projectId, id) + `/proposals/${proposalId}`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),
  download: async (projectId: string, file: ProjectFile) => {
    const blob = await api<Blob>(
      `${base(projectId)}/files/${file.id}/download`,
      {},
      true,
    )
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = file.original_name
    link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  },
}
