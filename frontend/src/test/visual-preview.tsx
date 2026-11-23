// Entrada exclusiva de Vite dev; no se importa desde la aplicación ni el build.
// Datos sintéticos y servicios locales: nunca representa una integración real.
import { createRoot } from 'react-dom/client'
import { MemoryRouter, Navigate, Route, Routes } from 'react-router-dom'
import type { Session } from '@supabase/supabase-js'
import { AuthContext } from '../hooks/auth-context'
import { Dashboard } from '../pages/Dashboard'
import { Workspace } from '../pages/Workspace'
import { AuthPage } from '../pages/AuthPage'
import { projectsService } from '../services/projects'
import { chatService } from '../services/chat'
import { analysisService } from '../services/analysis'
import { researchContextService } from '../services/research-context'
import { emptyContext } from '../lib/research-context'
import type { Project } from '../types/project'
import type {
  ConversationDetail,
  ProjectFile,
  Proposal,
  Turn,
} from '../types/chat'
import type { AnalysisRun } from '../types/analysis'
import '../index.css'
import chartUrl from './fixtures/frequencies.synthetic.png'

if (!import.meta.env.DEV)
  throw new Error('La revisión sintética requiere Vite dev.')
// Incluso un control no implementado falla localmente antes de salir a la red.
const localFetch = window.fetch.bind(window)
window.fetch = async () => {
  throw new Error('Vista sintética: acceso de red deshabilitado.')
}
const date = '2026-11-21T14:00:00Z'
const project: Project = {
  id: 'visual',
  user_id: 'synthetic',
  name: 'Participación y bienestar universitario',
  project_type: 'thesis',
  description:
    'Estudio de las experiencias de estudiantes en su comunidad académica.',
  created_at: date,
  updated_at: date,
}
const files: ProjectFile[] = [
  {
    id: 'visual-document-file',
    original_name: 'Cuestionario de participación.docx',
    file_role: 'instrument',
    file_type: 'docx',
    file_size: 18600,
    metadata: {
      sheets: [],
      extraction_status: 'partial',
      warnings: ['La numeración automática requiere contrastar el original.'],
      text_excerpt:
        'Sección 1: Participación académica\nEDU_030: ¿Con qué frecuencia participa en actividades?\nNunca; A veces; Frecuentemente.',
      instrument_extraction_version: 1,
    },
  },
  {
    id: 'data',
    original_name: 'respuestas_estudiantes.csv',
    file_role: 'dataset',
    file_type: 'csv',
    file_size: 6400,
    metadata: {
      sheets: ['Datos'],
      selected_sheet: 'Datos',
      warnings: [],
      profile: {
        profile_version: 2,
        row_count: 48,
        column_count: 2,
        missing_count: 2,
        duplicate_rows: 0,
        columns: [
          {
            name: 'participacion',
            physical_type: 'text',
            semantic_hint: '',
            statistical_type: 'categorical',
            missing: 0,
            unique: 3,
          },
          {
            name: 'bienestar',
            physical_type: 'numeric',
            semantic_hint: '',
            statistical_type: 'quantitative',
            missing: 2,
            unique: 18,
            min: 1,
            max: 10,
          },
        ],
      },
    },
  },
]
const proposal: Proposal = {
  id: 'proposal',
  title: 'Describir la participación y el bienestar',
  objective:
    'Examinar la distribución de participacion y bienestar, conservando las respuestas originales.',
  status: 'proposed',
  source_message_id: 'assistant',
  analysis_plan: {
    schema_version: 1,
    title: 'Participación y bienestar',
    objective: 'Describir las variables',
    procedure: 'descriptive',
    method: 'Estadística descriptiva',
    variables: [
      {
        file_id: 'data',
        sheet: 'Datos',
        column: 'participacion',
        role: 'outcome',
      },
      { file_id: 'data', sheet: 'Datos', column: 'bienestar', role: 'outcome' },
    ],
    justification:
      'Permite revisar las categorías de participación y la distribución del puntaje antes de definir comparaciones.',
    requirements: [
      'Confirmar el significado de las categorías con el instrumento.',
    ],
    limitations: ['La descripción no permite establecer causalidad.'],
    expected_outputs: [
      'Tabla de frecuencias',
      'Resumen de la distribución',
      'Gráficos descriptivos',
    ],
    joins: [],
  },
}
const detail: ConversationDetail = {
  conversation: {
    id: 'chat',
    project_id: project.id,
    assistant_provider: 'gemini',
    title: 'Participación y bienestar',
    primary_goal:
      'Describir la participación y el bienestar de los estudiantes.',
    current_stage: 'proposal',
    updated_at: date,
    stage_data: {},
  },
  files,
  proposals: [proposal],
  has_more_messages: false,
  messages: [
    {
      id: 'system',
      role: 'assistant',
      position: 1,
      message_type: 'event',
      content: 'Archivos asociados. Los originales permanecen privados.',
      metadata: { source: 'deterministic' },
    },
    {
      id: 'user',
      role: 'user',
      position: 2,
      message_type: 'text',
      content:
        'Quiero describir la participación y el bienestar de los estudiantes. ¿Qué análisis puedo realizar?',
      metadata: {},
    },
    {
      id: 'assistant',
      role: 'assistant',
      position: 3,
      message_type: 'text',
      content:
        'Podemos comenzar con un **análisis descriptivo**.\n\n- **Participación:** frecuencias por categoría.\n- **Bienestar:** resumen de la distribución y valores ausentes.\n\nRevisa el plan antes de aceptarlo. El instrumento puede ayudar a comprobar el significado de las respuestas.',
      metadata: {
        generation: { provider: 'gemini', model: 'proveedor-simulado' },
      },
    },
  ],
}
const run: AnalysisRun = {
  id: 'run',
  project_id: project.id,
  conversation_id: 'chat',
  proposal_id: 'proposal',
  request_id: 'request',
  title: 'Distribución de la participación académica',
  status: 'completed',
  created_at: date,
  finished_at: date,
  error: null,
  artifact_count: 1,
  methods: ['descriptive'],
  artifacts: [
    {
      id: 'chart',
      run_id: 'run',
      project_id: project.id,
      name: 'graficos/componente_1_1.png',
      mime_type: 'image/png',
      size_bytes: 1024,
      sha256: 'synthetic',
    },
  ],
  result: {
    schema_version: 1,
    run_id: 'run',
    project_id: project.id,
    conversation_id: 'chat',
    proposal_id: 'proposal',
    created_at: date,
    title: 'Participación académica',
    status: 'completed',
    summary:
      'Ejemplo sintético de presentación. No representa datos de una investigación real.',
    plan_snapshot: {},
    files: [],
    dependencies: {},
    specification: {
      schema_version: 1,
      components: [],
      decisions: [],
      filters: [],
      confidence_level: 0.95,
      alternative: 'two-sided',
      missing_policy: 'available_cases_per_procedure',
      multiplicity: 'none',
      decisions_confirmed: true,
    },
    components: [
      {
        source_index: 0,
        method: 'descriptive',
        title: 'Frecuencias de participación',
        status: 'completed',
        error: null,
        variables: [],
        scope: {},
        sample: { initial: 48, used: 48, excluded_missing: 0 },
        statistics: {},
        assumptions: [],
        warnings: [
          'Las categorías se conservan tal como fueron registradas. No se interpretan como ausencias automáticamente.',
        ],
        interpretation:
          'Distribución ilustrativa de tres categorías de participación.',
        tables: [
          {
            title: 'Participación académica — datos sintéticos',
            columns: [
              'Variable / grupo',
              'Categoría',
              'Frecuencia',
              'Porcentaje',
              'N válido',
              'Ausentes',
            ],
            rows: [
              'Nunca',
              'A veces',
              'Frecuentemente en actividades de la comunidad universitaria',
            ].map((name, index) => ({
              'Variable / grupo': 'participacion',
              Categoría: name,
              Frecuencia: [12, 20, 16][index],
              Porcentaje: [25, 41.6667, 33.3333][index],
              'N válido': 48,
              Ausentes: 0,
            })),
          },
        ],
        charts: ['graficos/componente_1_1.png'],
      },
    ],
  },
}
Object.assign(projectsService, {
  list: async () => [
    project,
    {
      ...project,
      id: 'general',
      name: 'Exploración de datos de un proyecto general',
      project_type: 'general',
    },
  ],
  get: async () => project,
  create: async () => project,
  update: async () => project,
  remove: async () => ({ id: project.id }),
})
Object.assign(chatService, {
  list: async () => [
    detail.conversation,
    {
      ...detail.conversation,
      id: 'previous',
      title: 'Revisión del instrumento',
    },
  ],
  files: async () => files,
  get: async () => structuredClone(detail),
  providers: async () => ({
    default: 'gemini',
    providers: [
      {
        id: 'gemini',
        name: 'Gemini',
        model: 'proveedor-simulado',
        enabled: true,
        configured: true,
        experimental: false,
      },
      {
        id: 'openai',
        name: 'Terra',
        model: 'proveedor-simulado',
        enabled: true,
        configured: true,
        experimental: true,
      },
    ],
  }),
  profile: async (_project: string, id: string) =>
    files.find((file) => file.id === id)!.metadata,
  download: async () => {
    throw new Error('Vista sintética: no hay un original real para descargar.')
  },
  turn: async (_project: string, _id: string, turn: Turn) => {
    detail.messages.push({
      id: crypto.randomUUID(),
      position: detail.messages.length + 1,
      role: 'user',
      message_type: 'text',
      metadata: {},
      content: turn.content,
    })
    return { status: 'completed' }
  },
  decide: async (
    _project: string,
    _id: string,
    _proposal: string,
    status: Proposal['status'],
  ) => {
    detail.proposals[0].status = status
  },
  rename: async (_project: string, _id: string, title: string) => {
    detail.conversation.title = title
    return detail.conversation
  },
  upload: async (
    _project: string,
    _id: string,
    file: File,
    role: ProjectFile['file_role'],
  ) => {
    const record = {
      ...files[role === 'instrument' ? 0 : 1],
      id: crypto.randomUUID(),
      original_name: file.name,
    }
    files.push(record)
    return record
  },
  changeProvider: async (
    _project: string,
    _id: string,
    provider: 'gemini' | 'openai',
  ) => {
    detail.conversation.assistant_provider = provider
    return detail.conversation
  },
})
Object.assign(analysisService, {
  list: async () => [run],
  get: async () => run,
  artifact: async () => (await localFetch(chartUrl)).blob(),
  downloadZip: async () => {
    throw new Error('Vista sintética: descarga no disponible.')
  },
})
let savedContext = {
  document: {
    ...emptyContext(),
    research_title: project.name,
    general_objective:
      'Describir la participación académica y el bienestar de estudiantes universitarios.',
    methodological_design: 'Estudio transversal descriptivo.',
    instruments: ['Cuestionario de participación'],
  },
  revision: 1,
  updated_at: date,
}
Object.assign(researchContextService, {
  get: async () => ({ context: savedContext }),
  save: async (
    _project: string,
    document: typeof savedContext.document,
    revision: number,
  ) => {
    savedContext = { document, revision: revision + 1, updated_at: date }
    return { context: savedContext }
  },
})
const screen = new URLSearchParams(location.search).get('screen') || 'dashboard'
const route =
  screen === 'dashboard'
    ? '/dashboard'
    : screen === 'login' || screen === 'registro'
      ? `/${screen}`
      : `/proyectos/visual/${screen}`
createRoot(document.getElementById('root')!).render(
  <AuthContext.Provider
    value={{
      session: {
        user: { id: 'synthetic', email: 'revision@example.test' },
      } as Session,
      loading: false,
      error: null,
    }}
  >
    <MemoryRouter initialEntries={[route]}>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" />} />
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/login" element={<AuthPage />} />
        <Route path="/registro" element={<AuthPage register />} />
        <Route path="/proyectos/:projectId/:module" element={<Workspace />} />
      </Routes>
    </MemoryRouter>
    <aside
      style={{
        position: 'fixed',
        bottom: 0,
        right: 0,
        padding: '2px 8px',
        background: '#eef2ff',
        color: '#3730a3',
        fontSize: 10,
        pointerEvents: 'none',
        zIndex: 20,
      }}
    >
      Revisión sintética · Sin servicios remotos
    </aside>
  </AuthContext.Provider>,
)
