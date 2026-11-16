import type { Variable } from './chat'

export type Method =
  | 'descriptive'
  | 'pearson'
  | 'spearman'
  | 'student_t'
  | 'welch_t'
  | 'anova'
  | 'welch_anova'
export type StatisticalType =
  | 'continuous'
  | 'discrete'
  | 'ordinal'
  | 'nominal'
  | 'binary'
  | 'temporal'
  | 'identifier'
export interface DataDecision {
  variable: Variable
  statistical_type: StatisticalType
  missing_markers: string[]
  retained_markers: string[]
  ordinal_order: string[]
  unit: string
}
export interface ExecutionComponent {
  source_index: number
  method: Method
  design: 'independent' | 'not_applicable'
  equal_variances_confirmed: boolean
  group_values: string[]
}
export interface ExecutionSpec {
  schema_version: 1
  components: ExecutionComponent[]
  decisions: DataDecision[]
  filters: { variable: Variable; values: string[] }[]
  confidence_level: number
  alternative: 'two-sided'
  missing_policy: 'available_cases_per_procedure'
  multiplicity: 'none' | 'holm'
  decisions_confirmed: boolean
}
export interface ExecuteRequest {
  request_id: string
  specification: ExecutionSpec
}
export interface ProcedureInfo {
  code: Method
  name: string
  families: string[]
  variable_types: string
  design: string
  groups: string
  assumptions: string[]
  parameters: string[]
  statistics: string[]
  effects: string[]
  limitations: string[]
}
export type JsonValue =
  null | boolean | string | number | JsonValue[] | { [key: string]: JsonValue }
export interface ResultTable {
  title: string
  columns: string[]
  rows: Record<string, JsonValue>[]
}
export interface ComponentResult {
  source_index: number
  method: Method
  title: string
  status: 'completed' | 'partial' | 'failed'
  error: string | null
  variables: Variable[]
  scope: Record<string, string>
  sample: Record<string, JsonValue>
  statistics: Record<string, JsonValue>
  assumptions: {
    name: string
    status: 'evaluated' | 'pending' | 'violated' | 'not_applicable'
    detail: string
  }[]
  warnings: string[]
  tables: ResultTable[]
  charts: string[]
  interpretation: string
}
export interface AnalysisResult {
  schema_version: 1
  run_id: string
  project_id: string
  conversation_id: string
  proposal_id: string
  created_at: string
  title: string
  specification: ExecutionSpec
  plan_snapshot: Record<string, JsonValue>
  files: {
    id: string
    name: string
    sheet: string
    sha256: string
    bytes: number
    initial_rows: number
  }[]
  dependencies: Record<string, string>
  components: ComponentResult[]
  status: 'completed' | 'partial' | 'failed'
  summary: string
}
export interface AnalysisArtifact {
  id: string
  run_id: string
  project_id: string
  name: string
  mime_type: string
  size_bytes: number
  sha256: string
}
export interface AnalysisRun {
  id: string
  project_id: string
  conversation_id: string
  proposal_id: string
  request_id: string
  title: string
  status: 'running' | 'completed' | 'partial' | 'failed'
  created_at: string
  finished_at: string | null
  error: string | null
  result: AnalysisResult | null
  artifact_count: number
  methods: string[]
  artifacts: AnalysisArtifact[]
}
export const runStatus = {
  running: 'Procesando',
  completed: 'Completado',
  partial: 'Parcial',
  failed: 'Fallido',
}
