# Validación de Sesión 01

Las pruebas del frontend usan mocks de Auth y proyectos; no sustituyen la conexión real en la aplicación. Comprueban guards, inicialización y recuperación de sesión, validaciones, registro pendiente de correo, errores de login, creación, edición con tipo fijo, confirmación de eliminación, cierre de sesión, reintentos y navegación por tipo de proyecto.

Las pruebas de Python importan la aplicación, verifican `/health`, lista de orígenes, CORS permitido/rechazado y 404. El arranque real de Uvicorn y una petición HTTP a `/health` también se verifican localmente. Starlette emite una advertencia de deprecación de su integración con httpx; las tres pruebas pasan.

Desde `supabase`, ejecutar `npm ci` y `npm test` para probar la migración en PostgreSQL local con PGlite (sin Docker). La prueba crea un esquema Auth mínimo efímero y cambia de rol a `authenticated`/`anon`: comprueba CRUD, restricciones de longitud/tipo, inmutabilidad, actualización de fecha y aislamiento entre dos identidades. No usa credenciales ni se conecta al proyecto externo.

No se dispuso de credenciales ni sesión del proyecto Supabase durante la implementación. Quedan pendientes la aplicación remota de la migración, los correos, Auth real, persistencia y pruebas de aislamiento con dos usuarios descritas en `SETUP.md`. Ninguna prueba con mocks demuestra por sí sola el funcionamiento de RLS remoto.

## Resultados ejecutados

- Vitest: 15 pruebas aprobadas en 2 archivos.
- TypeScript estricto, oxlint, formato Prettier y compilación Vite: aprobados.
- pytest: 3 pruebas aprobadas; advertencia de Starlette/httpx descrita arriba.
- PGlite: 1 prueba de migración/CRUD/RLS aprobada con múltiples comprobaciones de seguridad.
- Uvicorn: inicio correcto y petición HTTP real a `/health` con respuesta 200 y `status: ok`.
- Chromium/Playwright local: recorrido con HTTP Supabase interceptado, login, rutas privadas, creación tesis/general, recuperación tras recarga, bloqueo de Contexto por URL, navegación móvil y logout. Sin errores JavaScript ni desbordamiento horizontal a 390 px; capturas de escritorio (1440 px) y móvil revisadas visualmente. Script y capturas temporales fuera del repositorio, sin incorporar infraestructura E2E al proyecto.

La prueba de navegador verifica la integración del SDK con las respuestas HTTP esperadas, pero no confirma disponibilidad, configuración o seguridad de un servicio remoto. No se ha desplegado en Vercel ni Render.
