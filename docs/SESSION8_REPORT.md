# Sesión 08 — instrumentos y estabilización de tesis

Fecha: 20 de noviembre de 2026 (America/Lima). Repositorio
`Agape-exe/statia-platform`. Rama exclusiva: `fix/cierre-validacion-tesis`.

## Continuidad y alcance

Se verificaron AGENTS, SETUP, ARCHITECTURE e informes 07/6B y el historial. La base
`feat/excel-multihoja` estaba limpia y contenía `7d29c61`, `6e0297d` y `4fa072a`.
Se creó la rama desde ella, sin perder Sesión 07 ni usar reset/rebase/merge.
No hubo push, PR, despliegue, migraciones remotas, modificaciones de Supabase,
cambios de credenciales/entornos reales ni llamadas reales a Gemini o Terra.
La identidad Git existente se conservó, sin coautores artificiales.

La evidencia NHANES y sus resultados correctos es la aportada por el responsable;
no se cargaron sus originales en esta sesión ni se recalcularon resultados
históricos para sustituir esa evidencia. No se modificó ningún archivo del motor
`services/statistics`, sus fórmulas, datos originales o ejecuciones almacenadas.

## Causas raíz verificadas

| Hallazgo reproducible | Consecuencia y corrección |
| --- | --- |
| El PDF se conservaba recortado a 16 000 caracteres y se enviaban solo los primeros 6000, sin búsqueda según consulta. | Preguntas lejanas no llegaban al proveedor. Se guarda extracción acotada con fragmentos/ubicaciones y se recupera según códigos/términos. |
| `page_tree_maximum_page_entries=100` cuenta entradas de diccionarios, no páginas. | Un PDF textual de 42 páginas fallaba antes de alcanzar las 80 anunciadas. Se acotan 4096 entradas y se mantienen 80 páginas explícitas. |
| Rol/extensión y CHECK/MIME solo admitían PDF. | DOCX no podía completar carga/persistencia. Se amplían validador, MIME, UI y una migración local mínima. |
| La acción `files_ready` validaba cualquier propuesta del modelo como un plan solicitado. | Una comprensión podía terminar en error de planificación. Ahora el modo determina el contrato y se descartan planes no solicitados antes de validarlos. |
| Un paso redundante en `components` se rechazaba fuera de una integral o dentro de una integral de un solo paso. | Se normaliza únicamente si coinciden método exacto, procedimiento/envoltura, referencias, roles, orden y ausencia de dependencias; después se revalida todo. |
| «Tabla descriptiva» no acreditaba productos globales solicitados aunque el mismo procedimiento los entregara. Una selección categórica con frecuencias explícitas también podía parecer incompleta. | Se acredita la equivalencia solo contra cobertura real, sin cambiar método ni sustituir productos numéricos/inferenciales. |
| Toda consulta sin solicitud estadística, con resultados existentes, se trataba como discusión de resultados y podía perder metadatos del instrumento. | Una consulta documental conserva su recuperación aunque existan ejecuciones guardadas. |
| La UI de Contexto siempre habilitaba revisión; un PUT idéntico podía crear otra revisión. | Se comparan cambios normalizados y la API devuelve la revisión existente si contenido y revisión esperada coinciden. |
| Se preservaban UUID conocidos en la prosa por defecto. | Se ocultan en presentación y respuestas nuevas; las trazas verificadas siguen disponibles mediante solicitud expresa. |

El backend ya leía el Contexto vigente en cada turno de tesis. No se encontró una
pérdida de objetivos persistidos. Se reforzó el uso de esa revisión frente a
afirmaciones antiguas del historial y se rechaza la negación reproducida de
objetivos guardados. No se dispone del JSON ni las trazas de los fallos reales
intermitentes: no se atribuye su causa exacta al modelo ni se afirma reproducir
su cuota original. La opción de texto documental era falsa por defecto; no se
puede deducir si estaba habilitada en las pruebas reales descritas.

## Lectura PDF y Word realmente implementada

| Formato | Soporte y ubicación | Límites/advertencias |
| --- | --- | --- |
| PDF textual | `pypdf` existente; texto por página, fragmentos solapados y referencia a página. | Orden visual aproximado; tablas/columnas pueden perder estructura. Páginas sin texto o fallidas se identifican. Sin OCR. Cifrado/daño incompatible se rechaza. |
| DOCX Word sin macros | ZIP/OPC y XML seguro; párrafos y tablas en orden XML, encabezados/pies, notas, comentarios y texto de cuadros recuperable sin duplicarlo. Referencias por parte y párrafo. | No renderiza Word ni inventa páginas, numeración automática o texto de imágenes. Revisiones/objetos/etiquetas no recuperables generan aviso parcial. |
| DOC antiguo | **No admitido.** Error explícito para convertir una copia a DOCX o PDF. | Es un formato binario OLE distinto; no se incorpora un conversor externo o del sistema. |
| DOCM, macros, objetos activos y cifrados | **No admitidos.** | No se ejecuta ningún contenido ni se abre una relación externa. |

El original admitido permanece privado, intacto, con nombre/formato/tamaño,
metadatos y descarga. Reutilización autorizada dentro del mismo proyecto conserva
el objeto y sus referencias; no se habilitan vínculos entre proyectos distintos.

Límites: 10 MB y el máximo de carga configurado; tamaño expandido configurado
(30 MB por defecto); 500 entradas ZIP, relación máxima 200:1 por entrada y 8 MiB
por XML interpretado; CRC, nombres duplicados/rutas peligrosas y cifrado verificados;
DTD, entidades y referencias externas prohibidas mediante `defusedxml`, también
en UTF-16. PDF: 80 páginas y límites de decodificación de pypdf. Proceso cancelable:
20 s, hijo hasta 192 MiB y API+hijo hasta 450 MiB observados cada 100 ms. Los picos
entre mediciones no son una garantía de contención del sistema operativo.

Extracción conservada: 240 000 caracteres incluyendo solapamientos, hasta 600
fragmentos, estados `extracted`/`partial`/`no_text`, texto, advertencias y ubicación.
`extracted` significa texto recuperado por el extractor, nunca fidelidad visual ni
lectura completa por el modelo. La vista previa sigue acotada a 16 000 caracteres.

Referencias de diseño: [estructura WordprocessingML de Microsoft](https://learn.microsoft.com/en-us/office/open-xml/word/structure-of-a-wordprocessingml-document),
[formato binario DOC de Microsoft](https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-doc/ccd7b486-7881-484c-a137-51170af7cc22),
[protecciones de defusedxml](https://pypi.org/project/defusedxml/) y
[limitaciones de extracción de pypdf](https://github.com/py-pdf/pypdf/blob/main/docs/user/extract-text.md).

## Recuperación, consentimiento y planificación

- Búsqueda léxica local, sin embeddings, base vectorial o red: códigos exactos,
  términos y vecinos con opciones; prioridad a coincidencias en varios documentos.
  Hasta diez fragmentos/12 000 caracteres por turno, con omisiones y ubicaciones.
- `share_instrument_text` sigue siendo autorización explícita. La UI muestra
  proveedor y estado fuera del desplegable; la autorización corresponde al
  proyecto/conversación/proveedor y se retira al cambiar explícitamente proveedor.
  Los mensajes anteriores continúan en el historial compartido; desactivarla no
  equivale a borrar lo ya compartido.
- Sin autorización, texto accesible o coincidencia, una consulta documental recibe
  una explicación determinista del límite, sin consumir una llamada al proveedor.
  No encontrar un código no prueba que no exista fuera de lo recuperado.
- Instrumentos históricos se releen de forma efímera desde Storage solo con
  autorización; no se sobrescriben metadatos históricos ni originales. Esta
  ampliación puede costar otra lectura en turnos posteriores.
- Gemini y Terra comparten el contrato por intención: comprensión, documento,
  metodología y planificación. No se convierten respuestas metodológicas en
  planes ni se bloquean por un alcance estadístico pendiente de otro turno.
- Códigos sin evidencia, citas literales entre «» inexistentes y afirmaciones
  observadas de lectura completa se rechazan mediante controles finitos. No son
  una garantía universal contra toda paráfrasis incorrecta o prompt injection;
  la fidelidad de respuestas reales debe comprobarse manualmente.
- Una corrección semántica como máximo, cuotas y reintentos de transporte sin
  aumento. Se reservan hasta 4000 caracteres del contexto para comunicar fallos;
  si lo indispensable no cabe, se devuelve 413 sin truncar silenciosamente la
  evidencia documental ni cambiar el alcance.
- Se distinguen errores de respuesta/documento (`response_validation`, categoría
  `document_evidence`), planes (`planning_validation` y categorías), formato,
  proveedor, límites e internos. Permanecen los request ID, replays y bloqueos.

## Contexto, resultados y gráficos

Contexto muestra «Contexto confirmado · Revisión N» y cambios pendientes. Ordenar
claves adicionales o reponer el valor original no genera una revisión. Se permite
editar y confirmar revisiones posteriores. El 409 conserva el borrador; una
recarga que lo reemplace sigue requiriendo confirmación del usuario. General no
consulta ni requiere Contexto; chat no lo guarda.

UUID, run_id, rutas privadas y fechas ISO se omiten por defecto sin quitar las
trazas de almacenamiento. Los resultados históricos no se reescriben.
La vista local «Distinguir valores presentes y respuestas sustantivas» exige que
el investigador seleccione las categorías de no información; no infiere su
significado por etiquetas particulares. Solo presenta el desglose si la tabla
de frecuencias está completa. Mantiene N/Ausentes/porcentajes originales y
explica sus denominadores. La selección local no se persiste, no se envía al
proveedor y no cambia exportaciones ni se aplica a futuros análisis.

No se modificaron gráficos estadísticos, etiquetas históricas, fórmulas o
resultados guardados. Se conservaron sus controles y descargas. Las mejoras
visuales de esta sesión son estados de lectura/consentimiento/Contexto y el
desglose optativo junto a frecuencias; no una nueva interpretación automática.

## Validaciones automatizadas

| Comprobación | Resultado final |
| --- | --- |
| Backend completo, 29 módulos en procesos aislados | Consolidado: **634 aprobadas, 1 omitida**, sin fallos pendientes |
| Primera pasada general backend | 633 aprobadas, 1 fallo de huella histórica, 1 omitida; 702,05 s |
| Revisión final del módulo de auditoría Terra | 98 aprobadas y 1 omitida; resuelve el único fallo de la pasada general |
| Regresión dirigida final de instrumentos/contratos/proveedor | 79 aprobadas; retoque categórico final y alcance/interpretación: otras 64 aprobadas |
| Frontend completo | **127 aprobadas en 12 archivos** |
| Presentación final de trazas privadas | 10 aprobadas en 2 archivos tras el último ajuste de presentación |
| PostgreSQL/PGlite local | **6 suites aprobadas**, incluida migración DOCX, RLS y reutilización |
| Configuración de producción frontend | **2 aprobadas** |
| TypeScript, oxlint, Prettier y build | Aprobados; sin advertencias nuevas de lint |
| Calidad Python | 70 archivos con lint/formato aprobados; lint adicional de módulos históricos modificados aprobado |
| `pip check` | Sin dependencias rotas |
| API local existente | `/health`: 200; listado privado sin JWT: 401; sin llamada a proveedores ni autenticación remota |
| Diff y secretos | Aprobados; sin patrones de secretos, cambios del motor, entornos reales ni evidencia histórica |

El consolidado backend reemplaza únicamente el resultado fallido del módulo Terra
por su revalidación; no se presenta como una segunda pasada completa. La prueba
omitida es `test_legacy_a_d_bytes_and_converter_unchanged_without_import_or_execution`
en `test_terra_diagnostic.py`: falta `backend/test_terra_statia_env.py`, evidencia
A/D local no versionada. No se inventó ni se llamó al proveedor para reemplazarla.
La evidencia M existente conserva exactamente su SHA-256, planes y prompt congelado;
su prueba reconstruye explícitamente el contrato anterior sin la nueva bandera de
consentimiento. El contrato actual se comprueba por separado.

Advertencias existentes: deprecación Starlette/TestClient y chunk base Vite de
500,98 kB. No se amplían dependencias ni se cambia el empaquetado para ocultarlas.
No se ejecutaron llamadas reales a Gemini/Terra, validaciones con documentos del
investigador, RLS/Storage remoto, migración remota, vista real en navegador ni
medición/despliegue Render: son los pendientes externos del recorrido manual.

Fixtures documentales generadas en memoria, sin documentos de usuarios:
PDF textual simple, multipágina y pregunta/opciones en páginas distintas; sin
texto, cifrado, dañado, fuera de límites y fallo parcial de extracción. DOCX con
párrafos, tablas, Unicode, encabezado, secciones, cuadro de texto, enlaces externos,
XML/OPC inválido, entradas duplicadas, ZIP cifrado, binario Office cifrado,
expansión/entradas peligrosas y DTD/entidades UTF-16. Contenido de instrucciones
maliciosas permanece como dato no confiable. Pregunta sintética después de más
de 16 000 caracteres en ambos formatos; código ausente no se inventa.

La batería existente cubre CSV cuantitativo/categórico, XLSX una/múltiples hojas,
JSON tabular, faltantes, identificadores/códigos ambiguos y motor real. Los
recorridos nuevos cubren General y Tesis con Contexto confirmado, sin instrumento,
PDF, DOCX, instrumentos múltiples, comprensión sin propuesta, consulta documental,
plan simple normalizado en una llamada, plan incompatible rechazado, resultados
existentes con documento, revisión sin cambios, conflictos, cambio Gemini/Terra
con estado conservado y permisos de descarga. El recorrido histórico de tesis
sin Contexto permanece en la suite. PostgreSQL/RLS local usa PGlite con Auth y
Storage emulados; las pruebas HTTP usan Auth/Storage y proveedores simulados.

Regresiones encontradas durante el desarrollo (todas corregidas localmente): clasificación demasiado amplia
de una respuesta metodológica como consulta documental; pérdida de fragmentos al
existir resultados; alias descriptivos incompletos; expectativa antigua de generar
planes desde `files_ready`; controles de prueba que asumían un solo `role=status`
y consentimiento transferible entre proveedores; la auditoría de contexto histórico también requería separar la bandera nueva del contrato congelado. Se corrigieron y se actualizaron
los casos con intención explícita. No se redujeron validaciones metodológicas para
obtener una prueba aprobada. Pendientes al cierre: ver estado final.

## Dependencias, migraciones y entorno

- Nueva dependencia: `defusedxml>=0.7.1,<1`, instalada localmente en versión 0.7.1;
  rueda Python pura de aproximadamente 25 KB. Protege XML sin requerir lxml,
  python-docx, LibreOffice, antiword, OCR ni paquetes del sistema en Render.
- Una migración local necesaria: `202611200009_instrument_docx.sql`. La base
  anterior rechaza DOCX por CHECK de tipo/rol y MIME. Se conserva bucket privado,
  políticas RLS, límites y todas las filas. Aprobada en SQL local; **no aplicada
  a Supabase remoto**. No se requieren migraciones para Contexto/resultados.
- Variables nuevas: **ninguna**. Entornos reales y secretos sin cambios.

## Inicio local

Se observaron servidores existentes en `127.0.0.1:8001` y `localhost:5173`; no se
detuvieron ni se duplicaron. El frontend local ya apunta a API puerto 8001.
Si hace falta reiniciar, desde la raíz, en terminales separadas:

```powershell
Set-Location backend
.\.venv\Scripts\python -m pip install -r requirements-dev.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8001
```

```powershell
Set-Location frontend
npm ci
npm run dev
```

No hace falta cambiar claves ni variables para arrancar con la configuración
local existente. No iniciar otra copia si los puertos siguen ocupados.

## Plan de validación real pendiente

1. En una fase autorizada, revisar/aplicar solo 009 al entorno de validación y
   comprobar MIME, privacidad y RLS. Con esquema previo no probar DOCX como si
   estuviera habilitado. Esta sesión no autorizó ni ejecutó ese cambio remoto.
2. Tesis: abrir Contexto confirmado, comprobar botón sin cambios, editar/confirmar
   otra revisión y provocar conflicto desde dos pestañas sin perder borrador.
   Repetir General y tesis sin Contexto, sin exigir hipótesis descriptivas.
3. Cargar PDF textual largo, PDF escaneado, PDF protegido y DOCX real con tablas,
   encabezados/Unicode y numeración; contrastar preguntas/opciones y advertencias
   con Word/visor PDF. Descargar y verificar que el original coincide.
4. Consultar pregunta lejana y código inexistente, sin consentimiento y con él.
   Contrastar las ubicaciones citadas, literal/paráfrasis y ausencia de códigos
   inventados con Gemini y Terra reales. Cambiar proveedor, reautorizar y recargar.
5. Repetir con instrumentos de otra disciplina y CSV categórico/cuanti, XLSX de
   una/múltiples hojas y JSON con faltantes/códigos ambiguos. Generar/aceptar un
   descriptivo simple en una llamada; rechazar un plan incompatible. No unir hojas.
6. Consultar resultados guardados y después el instrumento; verificar ausencia
   de UUID/rutas en respuestas habituales y detalles verificados al pedirlos.
   Contrastar el desglose optativo de no información sin cambiar tablas, porcentajes
   o ZIP. Los conteos reales aportados de 6161/5703/458 siguen pendientes de este
   recorrido manual; no son reglas ni fixtures productivas.
7. Con dos cuentas reales verificar aislamiento de archivos, conversaciones,
   metadatos, descargas y resultados por API/REST/Storage. Comprobar vista móvil y
   escritorio con servicios reales. Medir RSS/tiempo en Render en una fase posterior
   autorizada; no hubo despliegue en esta sesión.

## Estado final

**NO APTO todavía para dar por habilitado el recorrido manual integral DOCX en
el entorno remoto**: se debe confirmar la ampliación 009 del esquema, preparada
y probada localmente pero no aplicada en esta sesión por instrucción expresa.
No se inspeccionó el esquema remoto y no se presupone que ya admita DOCX. Esto no se presenta como fallo de pruebas ni autoriza
aplicarla automáticamente. El código local queda preparado para revisión y
validación controlada tras ese requisito. Los archivos/proveedores reales,
RLS/Storage real y Render son validaciones pendientes; no se sustituyen por mocks.

## Archivos y commits locales

Commits funcionales, todos locales:

- `b2da72a` — `docs(sesion08): registrar plan correctivo y continuidad local`.
- `6ee83a5` — `fix(instrumentos): admitir DOCX y recuperar texto documental con límites`.
- `e1d6661` — `fix(asistente): separar consultas de planes y validar equivalencias seguras`.
- `ea92e01` — `fix(contexto): distinguir revisiones confirmadas de cambios pendientes`.
- `74eb1c2` — `fix(interfaz): aclarar consentimiento documental y lectura académica de resultados`.
- `14cf271` — `test(auditoria): conservar el contrato histórico de Terra ante metadatos nuevos`.
- `docs(sesion08): documentar validaciones, límites y requisito de esquema` — cierre
  documental de este informe; consultar el hash en `git log -1 --oneline`.

Archivos modificados o añadidos respecto a `4fa072a` (44):

```text
backend/app/api/chat.py
backend/app/api/research_context.py
backend/app/services/conversation.py
backend/app/services/conversation_text.py
backend/app/services/gemini.py
backend/app/services/instrument_context.py
backend/app/services/instrument_worker.py
backend/app/services/instruments.py
backend/app/services/interpretation_guards.py
backend/app/services/openai_provider.py
backend/app/services/planning_errors.py
backend/app/services/profiling.py
backend/app/services/reply_contract.py
backend/app/services/requested_scope.py
backend/requirements.txt
backend/scripts/check_analysis_quality.py
backend/tests/test_chat_api.py
backend/tests/test_gemini_resilience.py
backend/tests/test_instruments.py
backend/tests/test_profiling.py
backend/tests/test_research_context.py
backend/tests/test_terra_diagnostic.py
backend/tests/test_thesis_stability.py
docs/ARCHITECTURE.md
docs/SESSION8_PLAN.md
docs/SESSION8_REPORT.md
docs/SETUP.md
frontend/src/components/AnalysisResultCard.tsx
frontend/src/components/ChatComposer.tsx
frontend/src/components/DatasetCard.tsx
frontend/src/components/ProjectData.tsx
frontend/src/components/ResponseMeaning.tsx
frontend/src/components/StatisticalChat.tsx
frontend/src/components/ThesisContext.tsx
frontend/src/lib/chat-text.ts
frontend/src/lib/research-context.ts
frontend/src/test/chat.test.tsx
frontend/src/test/providers.test.tsx
frontend/src/test/session6.test.tsx
frontend/src/test/session6b.test.tsx
frontend/src/test/thesis-stability.test.tsx
frontend/src/types/chat.ts
supabase/migrations/202611200009_instrument_docx.sql
supabase/tests/instruments.test.mjs
```
