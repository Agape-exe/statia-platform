# Convenciones de Statia Platform

- Trabajar en una rama de funcionalidad desde `develop` actualizado. Nunca desarrollar directamente en `main` o `develop`.
- Conventional Commits en español, metadatos auténticos y commits por bloques funcionales. No añadir coautores artificiales, colaboradores ni fusionar PR automáticamente.
- Frontend: React + TypeScript estricto, presentación en componentes/páginas, acceso a datos en `services`, clientes en `lib`. Interfaz y errores en español; estados de carga, vacío y fallo explícitos.
- Supabase JS gestiona Auth y CRUD de proyectos. La seguridad depende de RLS, nunca solo de filtros del navegador. No usar `service_role` en frontend.
- FastAPI prepara el procesamiento futuro: configuración en `core`, rutas en `api`. No duplicar el CRUD del frontend. Futuras rutas privadas deberán validar el JWT de Supabase.
- Mantener arquitectura modular sin carpetas o capas vacías. No adelantar IA, datasets, análisis ni otras funcionalidades fuera de la sesión autorizada.
- Nunca versionar secretos, `.env`, credenciales de prueba reales o archivos de usuarios. Solo `.env.example` con valores vacíos o públicos de ejemplo.
- Ejecutar las comprobaciones relevantes; no inventar resultados ni presentar mocks como integración real. Documentar las validaciones externas pendientes.
- Antes de entregar: revisar diff, secretos, pruebas, TypeScript, lint y compilación. Consultar `docs/SETUP.md` y `docs/ARCHITECTURE.md`.
