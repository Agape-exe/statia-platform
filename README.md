# Statia Platform

Plataforma de análisis estadístico conversacional para investigaciones y datasets. Conserva Auth, proyectos y conversaciones con Gemini; incorpora ejecución estadística Python, resultados persistentes y recursos privados descargables. Contexto solo aparece en tesis y su persistencia sigue pendiente.

**Sesión 03:** motor y recorrido de ejecución implementados. P0 y ampliación P1 con validación numérica; revisión explícita antes de calcular, resultados en chat y módulo Resultados, CSV/PNG/JSON/Markdown/ZIP. La migración nueva y el recorrido autenticado en Supabase remoto siguen pendientes. Gemini real interpretó correctamente una síntesis sintética calculada localmente. Ver [motor y límites](docs/STATISTICAL_ENGINE.md) y [validación](docs/VALIDATION.md).

## Tecnologías y estructura

- `frontend/`: React, TypeScript, Vite, Tailwind CSS, React Router, Supabase JS y Lucide. Componentes, páginas, layouts, hooks, servicios y tipos separados.
- `backend/`: Python 3.12, FastAPI, Pydantic, `google-genai`, openpyxl, pypdf, NumPy, SciPy y Matplotlib/Agg. Auth servidor, perfilado acotado y estado conversacional; `GET /health` independiente de credenciales.
- `supabase/migrations/`: proyectos, conversaciones, mensajes, archivos, relaciones, propuestas e idempotencia. RLS, RPC y buckets privados `project-files` (originales) y `analysis-results` (recursos).
- `docs/`: [configuración](docs/SETUP.md), [arquitectura](docs/ARCHITECTURE.md) y [validación](docs/VALIDATION.md).

## Instalación y ejecución (PowerShell)

Requisitos: Node.js 22.12+ o 24 LTS, npm y Python 3.12. Desde la raíz:

```powershell
cd frontend
npm ci
Copy-Item .env.example .env.local
# Completar URL y clave PUBLICABLE en frontend/.env.local.
npm run dev
```

Ejecutar las migraciones y configurar Auth, Storage y Gemini siguiendo [SETUP](docs/SETUP.md). En otra terminal desde la raíz:

```powershell
cd backend
py -3.12 -m venv .venv
./.venv/Scripts/python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
# Completar Supabase y Gemini solo en backend/.env.
./.venv/Scripts/python -m uvicorn app.main:app --reload
```

Frontend: `http://localhost:5173`. API: `http://localhost:8000/health`; OpenAPI en `/docs`. No se necesita Docker. Auth y proyectos siguen usando Supabase JS; el asistente requiere FastAPI. Sin clave Gemini se pueden administrar conversaciones y perfilar archivos; la interpretación informa que falta habilitar el proveedor.

## Validaciones

```powershell
cd frontend
npm test
npm run typecheck
npm run lint
npm run build
```

```powershell
cd backend
./.venv/Scripts/python scripts/check_analysis_quality.py
./.venv/Scripts/python -m pytest -q
./.venv/Scripts/python -m pip check
```

Desde `supabase`, `npm ci` y `npm test` validan las cuatro migraciones y RLS en PostgreSQL local con PGlite sin Docker.

No versionar `.env.local`, `.env` ni archivos de usuarios. `VITE_API_URL` apunta a FastAPI; nunca usar una variable `VITE_` para claves privadas. CSV UTF-8/coma/punto y coma, XLSX con elección de hoja, JSON array de objetos y PDF con texto: 10 MB por archivo por defecto. No hay OCR, uniones ni correcciones automáticas.

La aceptación de un plan no ejecuta cálculos: **Ejecutar análisis** prepara los datos y presenta un resumen o una aclaración en el mismo chat. El cálculo requiere una segunda acción explícita desde **Análisis preparado**. **Opciones avanzadas** conserva la revisión técnica opcional. La preparación determinista, resultados y descargas funcionan sin Gemini. El motor relee originales, no une tablas ni imputa valores. Producción prevista: un worker y límites documentados de memoria/tiempo; no hay cola durable. Ver [recorrido, decisiones y límites](docs/EXECUTION_UX.md).
