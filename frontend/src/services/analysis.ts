import { api } from '../lib/api'
import type {
  AnalysisArtifact,
  AnalysisRun,
  ExecuteRequest,
  ProcedureInfo,
} from '../types/analysis'

const base = (projectId: string) => `/projects/${encodeURIComponent(projectId)}`
const run = (projectId: string, id: string) =>
  `${base(projectId)}/analysis-runs/${encodeURIComponent(id)}`

function save(blob: Blob, name: string) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = name
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

export const analysisService = {
  catalog: (projectId: string) =>
    api<ProcedureInfo[]>(`${base(projectId)}/analysis-procedures`),
  execute: (
    projectId: string,
    conversationId: string,
    proposalId: string,
    body: ExecuteRequest,
  ) =>
    api<AnalysisRun>(
      `${base(projectId)}/conversations/${encodeURIComponent(conversationId)}/proposals/${encodeURIComponent(proposalId)}/runs`,
      { method: 'POST', body: JSON.stringify(body) },
    ),
  list: (projectId: string, conversationId?: string, offset = 0) =>
    api<AnalysisRun[]>(
      `${base(projectId)}/analysis-runs?limit=50&offset=${offset}${conversationId ? `&conversation_id=${encodeURIComponent(conversationId)}` : ''}`,
    ),
  get: (projectId: string, id: string) => api<AnalysisRun>(run(projectId, id)),
  artifact: (projectId: string, runId: string, artifactId: string) =>
    api<Blob>(
      `${run(projectId, runId)}/artifacts/${encodeURIComponent(artifactId)}`,
      {},
      true,
    ),
  downloadArtifact: async (
    projectId: string,
    runId: string,
    artifact: AnalysisArtifact,
  ) => {
    save(
      await analysisService.artifact(projectId, runId, artifact.id),
      artifact.name.split('/').at(-1) || 'recurso',
    )
  },
  downloadZip: async (projectId: string, id: string) => {
    save(
      await api<Blob>(`${run(projectId, id)}/download`, {}, true),
      'resultados_analisis.zip',
    )
  },
}
