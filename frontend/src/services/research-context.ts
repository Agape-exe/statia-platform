import { api } from '../lib/api'
import type {
  ResearchContextDocument,
  SavedResearchContext,
} from '../types/research-context'

export const researchContextService = {
  get(projectId: string) {
    return api<{ context: SavedResearchContext | null }>(
      `/projects/${projectId}/research-context`,
    )
  },
  save(
    projectId: string,
    document: ResearchContextDocument,
    expectedRevision: number,
  ) {
    return api<{ context: SavedResearchContext }>(
      `/projects/${projectId}/research-context`,
      {
        method: 'PUT',
        body: JSON.stringify({
          document,
          expected_revision: expectedRevision,
          confirmed: true,
        }),
      },
    )
  },
}
