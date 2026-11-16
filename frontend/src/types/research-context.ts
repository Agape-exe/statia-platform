export interface ResearchContextDocument {
  schema_version: 1
  research_title: string | null
  research_problem: string | null
  general_objective: string | null
  specific_objectives: string[]
  hypotheses: string[]
  variables: string[]
  methodological_design: string | null
  population_sample: string | null
  instruments: string[]
  additional_information: string | null
  additional_fields: Record<string, string | null>
}

export interface SavedResearchContext {
  document: ResearchContextDocument
  revision: number
  updated_at: string
}
