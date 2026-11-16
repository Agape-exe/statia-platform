# Sesión 04 — validación y entrega

Fecha: 16 de noviembre de 2026 (America/Lima). Base `develop`/`783ee80`, PR #3 fusionado, rama `feat/sesion4-contexto-despliegue`. El usuario reservó los despliegues y cambios remotos a su intervención manual. No se crearon servicios ni se cambiaron planes, Auth, migraciones o datos de sus cuentas Render/Vercel/Supabase.

## Comprobado localmente

| Comprobación | Resultado |
| --- | --- |
| Python 3.12.10: `python -m pytest -q` | 276 aprobadas; 345,67 s |
| `python scripts/check_analysis_quality.py` | Ruff y formato: aprobados, 35 archivos/directorios objetivo |
| `python -m pip check`, `python -m compileall -q app scripts` | Sin dependencias incompatibles; compilación Python aprobada |
| React/Vitest: `npm test` | 68 aprobadas, 7 archivos |
| `npm run test:deployment` | 2 pruebas aprobadas con configuración sintética; rechazo de URL local/ausente, credenciales en URL, clave privada y variable Gemini en VITE |
| `npm run typecheck`, `npm run lint`, `npm run format:check` | Aprobados; lint acotado al código propio |
| `npm run build` | Aprobado |
| `npm run build:production` | Aprobado con URLs/claves públicas de ejemplo, sin probar servicios; rechazó correctamente la configuración local no válida para publicación |
| `npm audit --omit=dev --audit-level=high` | 0 vulnerabilidades informadas en dependencias de producción del frontend |
| SQL/PGlite: `npm test` en supabase | 4 suites aprobadas; regresiones existentes y Contexto/RLS/revisión/cascada |
| `bash -n backend/start.sh` | Sintaxis de arranque Linux aprobada |
| `render.yaml` | YAML válido y validación aprobada con Ajv/draft2020 contra `https://render.com/schema/render.yaml.json`; CLI/API de Render no ejecutadas |
| Diff / secretos | Revisión de cambios y `git diff --check`; sin `.env`, credenciales reales, datos de usuarios ni capturas con secretos versionados |

Advertencias existentes: Starlette/httpx en TestClient; paquete principal Vite de 500,71 kB (compilación local). No bloquean estas pruebas. Contexto se carga bajo demanda en un paquete separado (~8,2 kB antes de gzip).

Algunos intentos iniciales dentro del sandbox no pudieron leer módulos nativos o iniciar procesos. Los controles informados como aprobados se repitieron con acceso local adecuado. El script anterior de memoria no completaba un descriptivo por un contrato desactualizado; se corrigió y ahora devuelve error si no completa el cálculo, en lugar de considerar éxito la mera medición de un fallo.

## Memoria y compatibilidad

`measure_analysis_memory.py`: datos sintéticos de 20 000 filas × 20 columnas (400 000 celdas), original de 2 629 782 bytes, descriptivos y PNG. Windows/Python 3.12.10: API inicial 89,3 MiB, hijo máximo 212,0 MiB, combinado máximo 314,5 MiB, 7,41 s y estado completed. **Linux/WSL Ubuntu/Python 3.12.3:** instalación limpia de `requirements.txt`, API inicial 102,9 MiB, hijo 236,6 MiB, combinado 357,2 MiB, 6,27 s, estado completed y `pip check` sin conflictos. El proceso numérico y Agg funcionan en Linux. Se usaron entornos temporales, sin instalar paquetes del sistema. No es un máximo universal ni medición de capacidad Render. CI ejecutará también la medición en Ubuntu/Python 3.12.

El manifiesto fija un worker, plan gratuito, sin disco y arranque con PORT. Conserva límites existentes de filas, bytes, CPU por hilos, tiempo, RSS del hijo y exportación. El perfilado sigue en hilo de API sin barrera RSS propia. Para el plan gratuito, 0,1 CPU y suspensión por inactividad pueden afectar la demostración aunque la memoria baste. No se contrataron recursos ni se elevaron límites para encubrir un fallo.

## Servicios reales y navegador

`python scripts/check_gemini_context.py` realizó dos consultas a **Gemini real** mediante la configuración local, con contexto exclusivamente sintético. Revisión 1 exploratoria y revisión 2 longitudinal: ambas devolvieron `AssistantReply`, reconocieron el diseño vigente y no generaron propuestas ni cambio de finalidad. No se imprimen ni guardan claves/prompts/respuestas. Esta prueba no usa Supabase y no acredita el recorrido HTTP autenticado remoto. Los fallos de proveedor siguen siendo explícitos, sin respuestas simuladas.

Navegador IAB: 1440×900 y 390×844. Se comprobó el formulario en el workspace, importación de JSON, modificación de título, ausencia de información/hipótesis, diálogo de revisión, regreso a edición y confirmación. El ancho del documento no superó el viewport. Capturas locales de escritorio y móvil conservadas fuera del repositorio, con datos sintéticos. Se usó un fixture temporal de presentación que reemplazaba servicios por memoria: **no es una validación de persistencia o Auth remotas**. El fixture y servidor de QA se retiran al finalizar.

Las pruebas HTTP existentes conservan el recorrido general de propuesta/aceptación/preparación/ejecución/resultados/descargas con Python y exportaciones reales, y Auth/REST/Storage controlados. Las pruebas nuevas verifican contexto vigente entre dos consultas y conservación de mensajes históricos. La suite SQL usa PostgreSQL local WASM y auth.uid emulado; no sustituye aislamiento remoto con JWT de dos cuentas.

## Pendiente exclusivamente de configuración/despliegue manual

1. Revisar y fusionar manualmente el PR hacia develop cuando corresponda, o seleccionar expresamente la rama de sesión para demostrar sin fusión. No se fusiona automáticamente.
2. Verificar migraciones 001–005 existentes y aplicar solo las ausentes. Instalar la aditiva 006 una sola vez. Comprobar RLS, funciones y buckets privados con `supabase/checks/deployment.sql` y pruebas autenticadas de dos usuarios.
3. Crear/configurar Render y Vercel según [DEPLOYMENT](DEPLOYMENT.md), con variables reales en sus paneles y sin secretos en frontend. Esperar Live/Ready; registrar URLs y SHA reales. No existe una URL pública acreditada en esta entrega.
4. Configurar CORS exacto y Site URL/Redirect URLs de Supabase conservando localhost. Probar registro, correo confirmado, login, refresco y logout.
5. Completar ambos recorridos reales con Palmer Penguins, Gemini, Storage privado, descargas y cuentas A/B; repetir escritorio/móvil en el hosting y medir CPU/RAM, cold start, errores y reinicios.

## Backlog posterior

- Optimización del paquete principal Vite y actualización compatible de TestClient/httpx.
- Aviso de borrador sin guardar al cambiar de módulo; por ahora se requiere guardar/confirmar antes de navegar.
- Validación de carga y picos en hosting; aislamiento adicional de perfilado, cola durable y continuidad ante reinicios si se autorizan en otra sesión.
- Mantenimiento autorizado de objetos Storage huérfanos; sin borrar originales referenciados.
- Historial completo de ediciones de Contexto y comparación visual de revisiones. El MVP conserva revisión actual y procedencia en nuevos mensajes; no reescribe resultados históricos.
