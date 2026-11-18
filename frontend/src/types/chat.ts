import type { ExecutionPreparation } from './analysis'

export type AssistantProviderId = 'gemini' | 'openai'
export interface AssistantProvider {
  id: AssistantProviderId
  name: string
  model: string
  experimental: boolean
  enabled: boolean
  configured: boolean
}
export interface AssistantProviderCatalog {
  default: AssistantProviderId
  providers: AssistantProvider[]
}
export interface Generation {
  provider?: AssistantProviderId
  model?: string | null
  source?: string
}

export type Stage =
  | 'reuse'
  | 'instrument'
  | 'upload_instrument'
  | 'upload_dataset'
  | 'understanding'
  | 'clarification'
  | 'goal'
  | 'proposal'
  | 'ready'
export interface Conversation {
  id: string
  assistant_provider: AssistantProviderId
  active_request_id?: string | null
  project_id: string
  title: string
  primary_goal: string | null
  current_stage: Stage
  updated_at: string
  stage_data: {
    context_summary?: string
    confirmed_variable_types?: {
      variable: Variable
      statistical_type: 'continuous' | 'discrete'
    }[]
    execution_preparation?: {
      proposal_id: string
      result: ExecutionPreparation
      paused?: boolean
    } | null
    execution_preparations?: Record<
      string,
      { proposal_id: string; result: ExecutionPreparation; paused?: boolean }
    >
    awaiting_reuse_update?: boolean
    reuse_file_ids?: string[]
    goal_change?: {
      goal: string | null
      reason: string
      title: string | null
    } | null
  }
}
export interface Message {
  id: string
  position: number
  role: 'user' | 'assistant' | 'system'
  content: string
  message_type: string
  metadata: {
    selected_provider?: AssistantProviderId
    generation?: Generation | null
    source?: string
    event?: string
    questions?: string[]
    warnings?: string[]
    request_id?: string
    analysis_run_id?: string
    execution_preparation?: import('./analysis').ExecutionPreparation | null
    file_ids?: string[]
    status?: 'accepted' | 'rejected'
    proposal_id?: string
    execution_request_id?: string
    execution_status?: string
  }
  generation?: Generation | null
}
export interface Column {
  name: string
  physical_type: string
  source_representation?: string
  inferred_type?: string
  statistical_type: string
  semantic_hint: string
  missing: number
  missing_confirmed?: number
  missing_inferred?: number
  ambiguous_missing?: Record<string, number>
  missing_markers?: Record<string, number>
  levels?: { value: string; count: number }[]
  possible_identifier?: boolean
  unique: number
  min?: number | string
  max?: number | string
}
export interface ProjectFile {
  id: string
  original_name: string
  file_type: string
  file_role: 'dataset' | 'instrument'
  file_size: number
  metadata: {
    sheets: string[]
    selected_sheet?: string
    needs_sheet_selection?: boolean
    text_excerpt?: string
    pages?: number
    warnings?: string[]
    profile?: {
      profile_version?: number
      row_count: number
      column_count: number
      duplicate_rows: number
      missing_count: number
      ambiguous_missing_count?: number
      columns: Column[]
    }
  }
}
export interface Variable {
  file_id: string
  sheet: string
  column: string
  role: string
}
export interface Plan {
  schema_version: 1
  title: string
  objective: string
  procedure: string
  method: string
  variables: Variable[]
  justification: string
  requirements: string[]
  limitations: string[]
  expected_outputs: string[]
  joins: { left: Variable; right: Variable; justification: string }[]
  components?: { procedure: string; method: string; variables: Variable[] }[]
  filters?: { variable: Variable; values: string[] }[]
  type_confirmations?: {
    variable: Variable
    statistical_type: 'continuous' | 'discrete'
  }[]
  comparison?: {
    design: 'independent' | 'paired' | 'unknown'
    groups: string[]
    filters: { variable: Variable; values: string[] }[]
    strata: { variable: Variable; values: string[] } | null
    independence: string
    valid_observations: string
    missing_data: string
    outliers: string
    normality: string
    variance_assumption: string
    effect_size: {
      name: string
      standardizer: string
      definition: string
      correction: string
      confidence_interval: string
    }
    purpose: string
    multiplicity: string
    multiplicity_reason: string
  } | null
}
export interface Proposal {
  id: string
  title: string
  objective: string
  status: 'proposed' | 'accepted' | 'rejected'
  analysis_plan: Plan
  source_message_id?: string | null
}
export type TurnAction =
  | 'message'
  | 'reuse'
  | 'new_files'
  | 'instrument_yes'
  | 'instrument_no'
  | 'instruments_done'
  | 'files_ready'
  | 'keep_goal'
  | 'prepare_execution'
  | 'clarify_execution'
  | 'review_execution'
  | 'request_descriptive'
  | 'cancel_execution'
export interface Turn {
  request_id: string
  action: TurnAction
  content: string
  file_ids: string[]
  share_samples: boolean
  share_instrument_text: boolean
  proposal_id?: string
  question_id?: string
  answer?: string
}
export interface ConversationDetail {
  latest_analysis_run?: {
    id: string
    proposal_id: string
    status: 'running' | 'partial' | 'completed' | 'failed'
  } | null
  preparation_run?: { id: string; request_id: string; status: string } | null
  conversation: Conversation
  messages: Message[]
  files: ProjectFile[]
  proposals: Proposal[]
  retry_turn?: Turn | null
  has_more_messages?: boolean
}
export const stageLabel: Record<Stage, string> = {
  reuse: 'Selección de archivos',
  instrument: 'Instrumentos',
  upload_instrument: 'Carga de instrumentos',
  upload_dataset: 'Carga de datasets',
  understanding: 'Comprensión',
  clarification: 'Aclaraciones',
  goal: 'Finalidad',
  proposal: 'Confirmación de propuestas',
  ready: 'Plan aceptado',
}

export interface DataPage {
  columns: string[]
  rows: (string | null)[][]
  offset: number
  limit: number
  total_rows: number
  has_more: boolean
  sheet: string | null
}
