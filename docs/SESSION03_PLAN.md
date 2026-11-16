# Sesión 03: plan de implementación

Base: `origin/develop` d03023f (PR #2 integrado). Rama: `feat/motor-estadistico`.

1. Añadir especificación ejecutable versionada y revisión explícita de métodos, tipos, ausencias, diseño y filtros; conservar Plan v1.
2. Implementar preparación desde originales, catálogo determinista P0, efectos e intervalos documentados y pruebas numéricas independientes.
3. Persistir ejecuciones idempotentes y artefactos privados mediante migración aditiva, RLS y finalización transaccional. Aislar y limitar el trabajo numérico.
4. Conectar ejecución, tarjetas del chat, módulo Resultados y descargas CSV/PNG/JSON/Markdown/ZIP. Aportar resultados guardados al contexto de preguntas posteriores.
5. Validar regresiones, precisión, integridad SQL, interfaz, exportaciones y memoria. Actualizar documentación, crear commits funcionales y PR hacia develop sin fusionar.

P0 precede a ampliaciones P1; P2 queda fuera. Las pruebas locales con dobles no acreditan Supabase/Gemini remotos. La sesión 03 autoriza expresamente ejecución inferencial y sustituye la restricción temporal de sesión 02 en AGENTS.md.
