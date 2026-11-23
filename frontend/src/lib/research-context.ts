import type { ResearchContextDocument } from '../types/research-context'

export const contextFields = [
  { key: 'research_title', label: 'Título de investigación', list: false },
  {
    key: 'research_problem',
    label: 'Problema o pregunta de investigación',
    list: false,
  },
  { key: 'general_objective', label: 'Objetivo general', list: false },
  { key: 'specific_objectives', label: 'Objetivos específicos', list: true },
  { key: 'hypotheses', label: 'Hipótesis (si existen)', list: true },
  { key: 'variables', label: 'Variables', list: true },
  { key: 'methodological_design', label: 'Diseño metodológico', list: false },
  { key: 'population_sample', label: 'Población y muestra', list: false },
  { key: 'instruments', label: 'Instrumentos', list: true },
  {
    key: 'additional_information',
    label: 'Información adicional relevante',
    list: false,
  },
] as const

export function emptyContext(): ResearchContextDocument {
  return {
    schema_version: 1,
    research_title: null,
    research_problem: null,
    general_objective: null,
    specific_objectives: [],
    hypotheses: [],
    variables: [],
    methodological_design: null,
    population_sample: null,
    instruments: [],
    additional_information: null,
    additional_fields: {},
  }
}

export function contextFingerprint(document: ResearchContextDocument): string {
  const normalized = Object.fromEntries(
    contextFields.map(({ key, list }) => [
      key,
      list
        ? document[key].map((value) => value.trim()).filter(Boolean)
        : document[key]?.trim() || null,
    ]),
  )
  return JSON.stringify({
    ...normalized,
    additional_fields: Object.entries(document.additional_fields)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, value]) => [key, value?.trim() || null]),
  })
}

export function parseResearchContext(text: string): ResearchContextDocument {
  if (new TextEncoder().encode(text).length > 100000)
    throw new Error('El JSON supera los 100 KB permitidos para importar.')
  let value: unknown
  try {
    value = JSON.parse(text)
  } catch {
    throw new Error('El JSON no es válido. Revisa comillas y separadores.')
  }
  if (!value || typeof value !== 'object' || Array.isArray(value))
    throw new Error('El contexto debe ser un objeto JSON.')
  const input = value as Record<string, unknown>
  const known = new Set<string>([
    'schema_version',
    'additional_fields',
    ...contextFields.map((field) => field.key),
  ])
  if (
    input.schema_version !== 1 ||
    Object.keys(input).some((key) => !known.has(key))
  )
    throw new Error(
      'Usa schema_version: 1 y coloca los campos propios de tu disciplina en additional_fields.',
    )
  const document = emptyContext()
  for (const field of contextFields) {
    const item = input[field.key]
    if (item === undefined) continue
    if (field.list) {
      if (
        !Array.isArray(item) ||
        item.length > 20 ||
        item.some(
          (part: unknown) =>
            typeof part !== 'string' ||
            part.length < 1 ||
            [...part].length > 500,
        )
      )
        throw new Error(
          `${field.label}: usa hasta 20 textos de 1 a 500 caracteres o una lista vacía.`,
        )
      document[field.key] = item as string[]
    } else {
      if (
        item !== null &&
        (typeof item !== 'string' || [...item].length > 2000)
      )
        throw new Error(
          `${field.label}: usa texto de hasta 2000 caracteres o null.`,
        )
      document[field.key] = item as string | null
    }
  }
  if (input.additional_fields !== undefined) {
    const extras = input.additional_fields
    if (
      !extras ||
      typeof extras !== 'object' ||
      Array.isArray(extras) ||
      Object.keys(extras).length > 20 ||
      Object.entries(extras).some(
        ([key, part]) =>
          !key.length ||
          [...key].length > 80 ||
          (part !== null &&
            (typeof part !== 'string' || [...part].length > 2000)),
      )
    )
      throw new Error(
        'Campos adicionales: usa un objeto de hasta 20 campos con texto o null.',
      )
    document.additional_fields = extras as Record<string, string | null>
  }
  if ([...JSON.stringify(document)].length > 16000)
    throw new Error('El contexto supera los 16000 caracteres permitidos.')
  return document
}
