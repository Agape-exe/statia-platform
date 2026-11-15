export type ProjectType = 'thesis' | 'general'
export interface Project {
  id: string
  user_id: string
  name: string
  project_type: ProjectType
  description: string | null
  created_at: string
  updated_at: string
}
export interface ProjectInput {
  name: string
  description: string
  project_type: ProjectType
}
export const typeLabel = (type: ProjectType) =>
  type === 'thesis' ? 'Investigación de tesis' : 'Dataset general'
