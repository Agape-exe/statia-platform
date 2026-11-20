# Sesión 07 — Excel multihoja y navegación de datos

Fecha: 20 de noviembre de 2026. Base `develop` / `origin/develop`: `44227f6`.
Rama local: `feat/excel-multihoja`. Sin push, PR, merge, despliegues, cambios de
entorno ni operaciones sobre Supabase remoto. Proveedores/Auth/Storage simulados
en las pruebas; no se llamó a Gemini ni Terra reales.

## Causas y cambios

- XLSX multihoja devolvía solo nombres de pestañas y detenía el flujo hasta elegir
  una. Ahora se perfila el libro en una apertura incremental y secuencial, con
  perfiles independientes y estados explícitos para hojas no examinables.
- El contexto de IA usaba únicamente `metadata.profile` de la hoja elegida.
  Ahora añade estructura global acotada, sin filas ni valores de otras hojas,
  para proyectos General y Tesis. Nunca presume correspondencia entre filas.
- Datos consultaba exclusivamente `selected_sheet`. El parámetro opcional
  `sheet` en registros/perfil y el selector visual permiten recorrer otras
  hojas y sus columnas, dimensiones, ausencias y perfiles, reiniciando páginas.
  No se modifica la referencia de conversaciones, propuestas ni resultados.
- El motor produce las seis medidas descriptivas solicitadas, pero sus nombres
  no figuraban como productos verificables del plan. Se añadieron alias ligados
  a cobertura cuantitativa real y la equivalencia comprobada con «Resúmenes
  globales», sin ampliar capacidades del motor. Se mantiene diferenciación con
  N/media/DE por grupo para conservar Welch.
- La cuota 429 original no se reprodujo con la configuración local actual
  (`AI_MAX_REQUESTS_PER_TURN=4`). El flujo existente puede consumir hasta cuatro
  solicitudes: generación y corrección, cada una con un reintento transitorio.
  Sin trazas del turno original no se puede atribuir su agotamiento con certeza.
  El desajuste de productos sí es reproducible y queda corregido; la regresión
  genera y acepta la propuesta con una única solicitud y sin aclaraciones.
  No se cambió la cuota, los reintentos ni los validadores metodológicos.

## Compatibilidad, límites y pendientes

- Sin uniones ni motor nuevo para análisis conjunto del libro. Los planes siguen
  usando la hoja fijada de cada referencia. Para analizar otra, seleccionar una
  referencia aún no perfilada o adjuntar nuevamente el libro como referencia.
- Perfiles antiguos: ampliación temporal bajo demanda, sin sobrescribir JSONB
  histórico; puede requerir releer el original al abrir otra vista. Las subidas
  nuevas y la navegación en una vista reutilizan perfiles disponibles.
- Se conservan límites de archivo/ZIP, 30 hojas, filas, columnas y longitud de
  celda. Límite global adicional: como máximo 400 000 celdas de registros, o
  `MAX_ROWS * MAX_COLUMNS` si es menor. Hojas omitidas tienen motivo explícito.
- El proveedor conserva conteos y estados de todas las hojas; puede omitir
  detalles de columnas con `columns_omitted`. Si el contexto indispensable
  todavía supera el límite, devuelve 413 en lugar de truncar JSON.
- La comprobación RSS es local en Windows, no certifica Render de 512 MB.
  Mantener un worker y el semáforo compartido con análisis. La relectura de
  originales por página continúa siendo la estrategia existente.
- Pendientes externos: revisión manual con libros completos del investigador,
  respuestas reales de ambos proveedores, RLS/Storage con dos cuentas reales y
  medición en Render. No se sustituyen esas comprobaciones por mocks/PGlite.
- Dependencias, variables de entorno y migraciones nuevas: **ninguna**.

## Archivos

- Backend: `api/chat.py`; servicios `profiling.py`, `workbook.py`,
  `data_preview.py`, `gemini.py`, `conversation.py`, `requested_scope.py` y
  `plan_capabilities.py`.
- Frontend: componentes `ProjectData.tsx`, `DatasetRows.tsx`, `DatasetCard.tsx`,
  `StatisticalChat.tsx`; `services/chat.ts` y `types/chat.ts`.
- Validación: `test_excel_multihoja.py`, `test_hotfix_final.py`,
  `test_session6b.py`, `excel-multihoja.test.tsx`, `chat.test.tsx`,
  `check_analysis_quality.py` y `measure_workbook_memory.py`.
- Documentación: este informe, `SETUP.md` y `ARCHITECTURE.md`.

## Validaciones

Fixtures generadas con estructuras distintas: cuantitativa de una hoja,
multihoja heterogénea, Unicode/espacios, vacías/no tabulares, mixtas y ausencias,
identificadores de alta cardinalidad, CSV/JSON y límites de bytes/expansión/
hojas/filas/columnas/celdas. Regresión Iris usa el extracto de sepal.length
de sus tres especies, no el libro completo de cinco columnas del usuario:
N=50 en cada hoja; medias 5.006, 5.936 y 6.588; DE muestral Setosa 0.3524896872.
El mismo contrato se prueba con otro nombre de variable en XLSX/CSV/JSON.

Resultados al cierre:

| Comprobación | Resultado |
| --- | --- |
| Backend completo, 27 módulos en procesos aislados como CI | 595 aprobadas, 0 fallidas, 1 omitida |
| Regresión Excel final con ejecución real de Setosa | 22 aprobadas; retoques posteriores: 3 de navegación/avisos y 6 de traza, aprobadas |
| Frontend completo | 122 aprobadas en 11 archivos |
| Regresión visual tras separar avisos por hoja | 3 aprobadas |
| Supabase local / PGlite | 5 aprobadas, sin servidor remoto |
| Configuración de producción frontend | 2 aprobadas |
| TypeScript, lint, formato y build | Aprobados |
| Calidad Python, 64 archivos y lint adicional de módulos históricos modificados | Aprobados |
| `pip check`, revisión de diff y búsqueda de secretos en cambios | Aprobados |

La prueba omitida es la comprobación de evidencia histórica A/D en
`test_terra_statia_env.py`: es un archivo local no versionado ausente en este
checkout. No se generó evidencia real ni se llamó al proveedor para reemplazarlo.
Advertencias no bloqueantes: deprecación existente de Starlette/TestClient y
bundle principal de Vite de 500.98 kB, ligeramente por encima de su aviso de
500 kB. No se cambiaron dependencias ni se rediseñó el empaquetado.

La regresión XLSX ejecuta el motor Python con N=50, media=5.006 y DE
muestral=0.3524896872; después consulta Versicolor y Virginica y verifica
inmutabilidad de la ejecución y selección histórica. El proveedor simulado
registra exactamente una solicitud al generar la propuesta.

Medición sintética con API cargada: cuatro hojas, 400 000 celdas, archivo
1 737 696 bytes; RSS basal 96.16 MiB, máximo observado 118.14 MiB, 3.62 s
de perfilado en Windows. Sin llamadas de red ni archivos de usuarios.

Durante el desarrollo se detectó y corrigió una regresión del reconocimiento
de N/media/DE por grupo; la suite dirigida posterior pasó 64 pruebas. La
instalación local de frontend estaba desactualizada respecto a develop y se
sincronizó con `npm ci`, sin modificar manifiestos ni lockfiles. Las pruebas
HTTP se ejecutaron fuera del sandbox porque TestClient se detenía en Windows.

## Inicio local

Backend, desde `backend`:

```powershell
./.venv/Scripts/python -m uvicorn app.main:app --reload
```

Frontend, desde `frontend`:

```powershell
npm run dev
```

Reutilizar las variables locales existentes según SETUP. No hace falta habilitar
proveedores para consultar hojas, perfiles y originales; la comprensión con IA
requiere un proveedor configurado y autorizado.

Commits locales, con la identidad Git existente y sin coautores añadidos:

- `7d29c61` — `fix(planes): reconocer productos descriptivos sin ampliar el alcance`.
- `6e0297d` — `feat(datos): comprender libros Excel y navegar hojas sin alterar planes`.
- `docs(sesion07): documentar validaciones y límites de Excel multihoja` — cierre
  documental; consultar su identificador en `git log -3 --oneline`.

Estado final: **APTO para validación manual**, con las comprobaciones externas
pendientes indicadas arriba. Sin regresiones conocidas pendientes al cierre.
