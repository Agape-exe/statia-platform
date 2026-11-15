# Convenciones de Statia Platform

- Trabajar en una rama de funcionalidad desde `develop` actualizado. Nunca desarrollar directamente en `main` o `develop`.
- Conventional Commits en español, metadatos auténticos y commits por bloques funcionales. No añadir coautores artificiales, colaboradores ni fusionar PR automáticamente.
- Frontend: React + TypeScript estricto, presentación en componentes/páginas, acceso a datos en `services`, clientes en `lib`. Interfaz y errores en español; estados de carga, vacío y fallo explícitos.
- Supabase JS gestiona Auth y CRUD de proyectos. La seguridad depende de RLS, nunca solo de filtros del navegador. No usar `service_role` en frontend.
- FastAPI: configuración y sesión en `core`, rutas en `api`, contratos en `models`, perfilado/proveedor/persistencia en `services`. No duplicar el CRUD de proyectos. Rutas privadas validan el token con Supabase Auth y acceden a REST/Storage con el JWT del usuario y clave publicable; sin credenciales administrativas.
- Mantener arquitectura modular sin carpetas o capas vacías. No adelantar IA, datasets, análisis ni otras funcionalidades fuera de la sesión autorizada.
- Nunca versionar secretos, `.env`, credenciales de prueba reales o archivos de usuarios. Solo `.env.example` con valores vacíos o públicos de ejemplo.
- Ejecutar las comprobaciones relevantes; no inventar resultados ni presentar mocks como integración real. Documentar las validaciones externas pendientes.
- El asistente prepara planes versionados, no ejecuta estadísticas inferenciales todavía. Validar archivos/hojas/columnas al generar y aceptar planes. Sin Gemini configurado, informar el problema sin respuestas simuladas. Mantener originales privados e intactos; no unir ni limpiar datos automáticamente.
- Antes de entregar: revisar diff, secretos, pruebas, TypeScript, lint y compilación. Consultar `docs/SETUP.md` y `docs/ARCHITECTURE.md`.
