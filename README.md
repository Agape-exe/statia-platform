# Statia Platform

Plataforma de análisis estadístico conversacional para investigaciones y datasets. La Sesión 01 implementa registro, inicio/cierre y recuperación de sesión con Supabase, rutas privadas, dashboard y CRUD real de proyectos. Incluye espacio de trabajo responsive; Contexto solo está disponible en proyectos de tesis.

**Estado:** implementación local lista para conectar a Supabase. Sin credenciales externas no se han validado correo, Auth, persistencia remota ni aislamiento real entre cuentas. Las pantallas Asistente, Contexto, Datos y Resultados son informativas; todavía no ejecutan IA, archivos o análisis.

## Tecnologías y estructura

- `frontend/`: React, TypeScript, Vite, Tailwind CSS, React Router, Supabase JS y Lucide. Componentes, páginas, layouts, hooks, servicios y tipos separados.
- `backend/`: Python 3.12, FastAPI, Pydantic Settings y pytest; `GET /health` y CORS configurable.
- `supabase/migrations/`: tabla `projects`, restricciones, trigger e índices; RLS para las cuatro operaciones.
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

Ejecutar primero la migración y configurar Auth siguiendo [SETUP](docs/SETUP.md). En otra terminal desde la raíz:

```powershell
cd backend
py -3.12 -m venv .venv
./.venv/Scripts/python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
./.venv/Scripts/python -m uvicorn app.main:app --reload
```

Frontend: `http://localhost:5173`. API: `http://localhost:8000/health`; documentación OpenAPI en `/docs`. No se necesita Docker. El CRUD no depende de que FastAPI esté encendido.

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
./.venv/Scripts/python -m pytest -q
```

Desde `supabase`, `npm ci` y `npm test` validan la migración y RLS en PostgreSQL local con PGlite sin Docker.

No versionar `.env.local` ni `.env`. `VITE_API_URL` queda reservado para la próxima integración; no configura ni requiere IA en esta sesión.
