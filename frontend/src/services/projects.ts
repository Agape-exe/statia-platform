import { getSupabase } from '../lib/supabase'
import { validateProject } from '../lib/validation'
import type { Project, ProjectInput } from '../types/project'

export const projectsService = {
  async list(userId: string): Promise<Project[]> {
    const { data, error } = await getSupabase()
      .from('projects')
      .select('*')
      .eq('user_id', userId)
      .order('updated_at', { ascending: false })
    if (error) throw error
    return data as Project[]
  },
  async get(id: string, userId: string): Promise<Project | null> {
    const { data, error } = await getSupabase()
      .from('projects')
      .select('*')
      .eq('id', id)
      .eq('user_id', userId)
      .maybeSingle()
    if (error) throw error
    return data as Project | null
  },
  async create(input: ProjectInput, userId: string): Promise<Project> {
    const validation = validateProject(input)
    if (validation) throw new Error(validation)
    const { data, error } = await getSupabase()
      .from('projects')
      .insert({
        name: input.name.trim(),
        description: input.description.trim() || null,
        project_type: input.project_type,
        user_id: userId,
      })
      .select()
      .single()
    if (error) throw error
    return data as Project
  },
  async update(
    id: string,
    input: ProjectInput,
    userId: string,
  ): Promise<Project> {
    const validation = validateProject(input)
    if (validation) throw new Error(validation)
    const { data, error } = await getSupabase()
      .from('projects')
      .update({
        name: input.name.trim(),
        description: input.description.trim() || null,
      })
      .eq('id', id)
      .eq('user_id', userId)
      .select()
      .single()
    if (error) throw error
    return data as Project
  },
  async remove(id: string, userId: string) {
    const { data, error } = await getSupabase()
      .from('projects')
      .delete()
      .eq('id', id)
      .eq('user_id', userId)
      .select('id')
      .single()
    if (error) throw error
    return data
  },
}
