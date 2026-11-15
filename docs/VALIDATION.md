# Validación — Sesión 02

Base: `develop` actualizado en `f7d4ea7`, con Sesión 01 fusionada por PR #1. El encargo informa que Auth y proyectos ya fueron comprobados manualmente con Supabase real; esta sesión conserva ese código y no atribuye esas comprobaciones al agente.

## Pruebas ejecutadas localmente

- Backend: `python -m pytest -q`, 49 pruebas. Perfilado real de CSV UTF-8/BOM y delimitadores, XLSX/hojas, JSON tabular, PDF sin texto, tipos, faltantes, duplicados, formatos y límites. HTTP de conversaciones, archivos, descarga, paginación, propuesta/aceptación/rechazo, idempotencia, compensación y estados. Auth, repositorio Supabase y Gemini usan dobles controlados en estas pruebas de orquestación.
- SDK Gemini: una prueba usa el SDK oficial con transporte HTTP interceptado para verificar serialización del contrato completo y lectura de la respuesta. Otras usan dobles controlados: Pydantic, modelo configurable, selección de columnas, corrección limitada, rechazo de variables/resultados inferenciales inválidos, contexto reducido, redacción, credenciales ausentes, 429/500/503, timeout y red. No se consumió Gemini real.
- Frontend: Vitest, 27 pruebas en 4 archivos. Incluye las 15 de Sesión 01, chat, archivos múltiples, comprensión automática, perfiles/hoja, decisiones, reutilización, finalidad nueva confirmada, reintento con el mismo UUID y recuperación de sesión. Servicios y Auth controlados mediante mocks.
- TypeScript estricto, oxlint, Prettier y compilación Vite aprobados. `pip check` sin dependencias rotas.
- PostgreSQL local PGlite: 2 suites aprobadas. Ejecutan ambas migraciones SQL, RLS SELECT/INSERT/UPDATE/DELETE entre dos identidades y anon, integridad entre proyectos, bucket privado/políticas, historial, título manual, transacciones, idempotencia, aceptación y reutilización sin otro objeto. Auth y esquema Storage son emulados; no es Supabase remoto.
- Uvicorn de producción iniciado sin claves: HTTP real `/health` 200 y `/openapi.json` disponible. La advertencia de Starlette/httpx en TestClient es una deprecación de la dependencia, sin fallos.
- Navegador local: workspace y chat reales contra rutas FastAPI, con Auth/repositorio/Gemini controlados y datos sintéticos. Se comprobó aceptación, mensaje, creación y reutilización. Revisión visual de escritorio y móvil, sin desbordamiento horizontal en la vista móvil comprobada y con compositor accesible. Capturas temporales fuera del repositorio; el servidor QA y su entrada están ignorados y no forman parte de producción.

## Validación externa pendiente

En esta sesión no se dispuso de una sesión autenticada/API administrativa para aplicar la migración remota ni de `GEMINI_API_KEY`. La clave publicable del frontend no autoriza migraciones ni sustituye una sesión de usuario. No se probaron las nuevas tablas/Storage con Supabase real ni una respuesta de Gemini real.

Pendiente: aplicar `202611150002_chat.sql`, configurar Supabase y Gemini en backend, y ejecutar los recorridos de `SETUP.md` con dos cuentas y datasets sintéticos. Confirmar modelo/permisos/cuota con el administrador. No se desplegó en Render ni Vercel.

## Límites conocidos

- Sin OCR ni ejecución inferencial; los planes aceptados quedan preparados para Sesión 03.
- La inferencia de tipos/semántica y la detección de datos sensibles son parciales; requieren revisión del usuario. El regex que rechaza estadísticos en el texto complementa el contrato y las instrucciones, no demuestra la veracidad de cualquier frase generada.
- No se limpian ni unen tablas automáticamente. Los libros con varias hojas exigen selección; otra hoja se adjunta por separado para preservar planes previos.
- Los objetos de un proyecto eliminado requieren limpieza de Storage; la cascada SQL solo elimina metadatos. La compensación de subidas es de mejor esfuerzo ante interrupciones de red.
- Listados sujetos al límite de filas de PostgREST; historial de mensajes con paginación explícita. Contexto Gemini acotado y archivos de conversación limitados por configuración.
- El propietario puede modificar sus propias filas vía REST. El motor futuro debe volver a validar planes y originales antes de ejecutar; no confiar en flags metodológicos ni texto de un modelo como autorización para código arbitrario.
