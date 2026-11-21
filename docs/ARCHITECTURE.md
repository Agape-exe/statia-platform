# Arquitectura

El [frontend multiproveedor de Sesión 5B](MULTIPROVIDER_FRONTEND.md) obtiene el catálogo
desde `services/chat`, confirma el cambio y envía `expected_provider`. La selección
local solo se confirma mediante respuestas del servidor; 409 recarga el detalle y un
estado incierto bloquea operaciones hasta recuperarlo. La procedencia de cada mensaje
se lee de su propia metadata, sin atribuirla al proveedor actual. Creación rápida y
nuevas finalidades conservan Gemini; muestras/PDF mantienen sus decisiones existentes.

La [integración multiproveedor de Sesión 5A](MULTIPROVIDER_BACKEND.md) añade
`OpenAIProvider` (Responses API, Terra fijo, experimental y deshabilitado por defecto).
`provider_runtime` conserva el protocolo, cuotas locales y métricas por turno;
`providers` selecciona explícitamente el cliente y exige la protección SQL 008 para
Terra. `plan_capabilities` bloquea productos descriptivos sin cobertura o alcance verificable
en generación, aceptación, preparación y ejecución. Gemini conserva su configuración y el valor predeterminado.
La migración aditiva 007 persiste selección por conversación e instantánea por solicitud,
con RPC invoker y eventos bajo RLS. La corrección aditiva 008 separa adquisición legacy
y multiproveedor y protege finalización/procedencia ante rollback; ver [secuencia manual](PR07_SAFE_ROLLOUT.md). Los contratos, validadores compartidos y motor Python
siguen siendo la barrera de planificación/ejecución; ningún fallo cambia de proveedor.

La [ejecución integral por componentes](INTEGRAL_EXECUTION.md) amplía JSONB/contratos existentes y añade la migración 005 para asociar propuestas nuevas a mensajes de la misma conversación. Las ejecuciones parciales y sus continuaciones conservan runs y artefactos inmutables.

La corrección de UX de Sesión 03 incorpora preparación determinista y aclaraciones en el mismo chat. `execution_preparation.py` orquesta la relectura privada compartida con ejecución; `statistics/automatic.py` comprueba originales y catálogo en el proceso acotado existente. `methods.py` reconoce conservadoramente nombres/códigos de planes v1 y preserva alternativas ambiguas. No hay otro motor ni ejecución de código generado.

Las acciones aditivas `prepare_execution`, `clarify_execution` y `cancel_execution` pasan por `begin_chat_turn`/`finish_chat_turn`. `stage_data.execution_preparation` conserva propuesta, respuestas por pregunta con hash y evaluación; cada respuesta del asistente conserva la evaluación en metadata. No se cambia la finalidad, la etapa ni el plan aceptado. El UUID/payload del turno protege mensajes y concurrencia con ejecuciones. No se requiere una migración adicional.

`ExecutionPreparation` v1 diferencia READY, NEEDS_CLARIFICATION, BLOCKED_UNCERTAINTY y UNSUPPORTED. Las aclaraciones tienen estados pending/answered/unknown; una respuesta desconocida se conserva fuera de preguntas activas. `review_execution` reabre explícitamente una respuesta, y `cancel_execution` deja la preparación pausada sin borrar decisiones. La lectura adapta estados anteriores sin cambiar ids/huellas. `request_descriptive` genera y valida otra propuesta en el mismo chat: mantiene el alcance mediante `Plan.filters` opcional, requiere aceptación y conserva el original; si falla Gemini, informa el fallo sin propuesta simulada. No hay migración nueva.

La especificación conserva `decisions_confirmed=false`; la acción final del usuario lo confirma. El request de ejecución añade opcionalmente `preparation_fingerprint`; el servidor contrasta UUID, propuesta, estado, huella y especificación, y el hijo revalida los originales antes de calcular. El UUID automático es estable para propuesta/huella y evita duplicados tras reabrir/repreparar. Los clientes avanzados anteriores siguen usando ExecutionSpec v1 y se someten a las comprobaciones comunes. Detalles en [EXECUTION_UX](EXECUTION_UX.md).

El navegador conserva Supabase JS para Auth y CRUD de proyectos. `AuthProvider` recupera y renueva la sesión; guards esperan la inicialización y las rutas privadas se remontan al cambiar de usuario. El chat se carga bajo demanda dentro del workspace existente. Presentación en `components`/`pages`, consultas en `services`, clientes en `lib`, contratos en `types`.

`lib/api.ts` adjunta el JWT a FastAPI, renueva una vez ante 401 y permite recuperar acceso si vence la sesión. `core/auth.py` consulta `/auth/v1/user`, sin confiar en una identidad proporcionada por el cliente. REST/Storage usan ese mismo JWT y la clave publicable. No hay `service_role` ni CRUD duplicado de proyectos.

## Persistencia y seguridad

La migración `202611150002_chat.sql` añade `conversations`, `messages`, `project_files`, `conversation_files`, `analysis_proposals` y `chat_requests`. RLS protege las cuatro operaciones por propietario del proyecto; claves compuestas impiden asociar archivos entre proyectos, incluso del mismo usuario. Triggers impiden mover registros entre padres. Los mensajes tienen posición monotónica e historial paginado de 100 en 100.

El bucket privado `project-files` usa `usuario/proyecto/uuid/nombre_seguro`, sin sobrescribir originales. Subir/registrar tienen compensación ante fallos; reutilizar solo crea relaciones. Eliminar chats conserva archivos. Eliminar proyectos borra metadatos por cascada, pero requiere limpieza de objetos físicos huérfanos desde Storage (ver SETUP).

Los RPC son `security invoker` y respetan RLS. `create_conversation` guarda bienvenida/etapa inicial. `begin_chat_turn` guarda el mensaje y adquiere una concesión de 180 s: UUID y payload deben coincidir al reintentar. `finish_chat_turn` guarda respuesta, propuestas, asociaciones y etapa atómicamente; `fail_chat_turn` conserva el mensaje y libera el turno. Una caída permite recuperar la concesión vencida. `decide_proposal` registra decisión y evento en una transacción.

## Conversación, perfilado y proveedor

Etapas: `reuse → instrument → upload_instrument → upload_dataset → understanding → clarification → goal → proposal → ready`. Sin instrumento se pasa a datasets; reutilización con datasets pasa a comprensión. Rechazo vuelve a finalidad, o conserva `ready` si hay otro plan aceptado. Bienvenida e incorporación son lógica explícita. Gemini solo sugiere etapas; el servidor controla transiciones y nunca acepta planes por decisión del modelo.

Tesis requiere aclaraciones metodológicas; general permite explorar sin conocimientos previos. Finalidad y resumen de entendimiento persisten además del historial. `current_context` relee el documento confirmado de tesis antes de contextualizar Gemini y `build_context` añade su revisión y fecha; general recibe null. La migración aditiva 006 protege `research_contexts` con RLS y un RPC invoker con revisión esperada. Editar/importar requiere revisar y confirmar; el chat no tiene una operación de escritura de Contexto. Los mensajes nuevos registran la revisión usada sin modificar snapshots históricos. Ver [THESIS_CONTEXT](THESIS_CONTEXT.md). Un cambio de finalidad queda pendiente en `stage_data.goal_change`; solo la acción del usuario crea otro chat, conservando el anterior y ofreciendo reutilización. Renombrar manualmente desactiva títulos automáticos.

`profiling.py` lee CSV/JSON/XLSX/PDF sin modificar ni combinar originales. Limita bytes, filas, columnas, celdas, hojas, páginas y expansión; un perfilado por proceso. XLSX comprueba ZIP y usa lectura incremental. pypdf limita streams y decodificación; sin texto conserva el PDF y comunica que no hay OCR. El libro se comprende globalmente antes de elegir una hoja para planes; esa elección queda congelada para no alterar referencias históricas.

El perfil calcula tipos físicos, tipos estadísticos tentativos, faltantes, duplicados, cardinalidades, distribuciones, min/max/media y pequeñas muestras. El significado es una hipótesis: un número puede ser identificador o escala.

El perfil v2 distingue `source_representation`, `inferred_type` y `statistical_type`. Vacíos/nulos reales se cuentan en `missing_confirmed`; marcadores con evidencia numérica en `missing_inferred`; en texto se conservan como `ambiguous_missing` salvo decisión explícita por columna. `missing` suma las dos primeras categorías, no las ambiguas. Se documentan marcadores y advertencias; los años son temporales, los IDs no son medidas y las mezclas inválidas no se convierten ni descartan. Los originales y perfiles anteriores no se reescriben retroactivamente.

`GeminiProvider` implementa `Provider` con `google-genai`, modelo configurable, timeout por intento, un reintento transitorio con jitter de 1–2 s y máximo una corrección semántica. Cada generación completa tiene un presupuesto de 65 s, incluyendo cliente, espera y reintento; ambas generaciones consumen como máximo 130 s dentro del turno de 150 s. El SDK mantiene `attempts=1` para evitar multiplicar llamadas. No se repiten timeouts ni errores de red con resultado remoto incierto. `gemini_schema.reply_schema()` define un contrato de transporte con objetos, listas, tipos básicos y enums; no exporta `AssistantReply.model_json_schema()`. Excluye `additionalProperties`, defaults, referencias y límites internos para evitar incompatibilidades del subconjunto Schema del proveedor. `AssistantReply` y `Plan` siguen validando íntegramente el JSON recibido antes de la validación semántica y persistencia. No hay ramas específicas por modelo. La [auditoría HTTP 503](GEMINI_503_AUDIT.md) documenta las pruebas reales, sus límites y el diagnóstico sintético A–F.

Contexto limitado por caracteres, sin archivos completos. Muestras/extractos PDF se habilitan en el compositor; se omiten valores de identificadores detectados y redactan patrones sensibles. La detección es parcial: el usuario debe revisar qué comparte. PDF y mensajes son datos no confiables, sin herramientas de ejecución. Los errores incluyen `X-Statia-Error` (`gemini_schema`, `gemini_model`, `gemini_quota`, `gemini_permissions`, `gemini_credentials`, `gemini_timeout`, `gemini_connectivity`, etc.) y, si hubo respuesta HTTP, `X-Gemini-Status`. Se clasifica el detalle del proveedor sin devolverlo ni registrarlo: logs solo con categoría interna y código HTTP. Un 400 no se reintenta ni se atribuye automáticamente a complejidad.

`AssistantReply` representa texto, preguntas, finalidad/título, variables, advertencias, cambio de finalidad y propuestas. `Plan` versión 1 contiene variables `{file_id,sheet,column,role}`, procedimiento, método, justificación, requisitos, limitaciones, productos esperados y relaciones declaradas. Se validan archivos asociados, hojas y columnas exactas; se rechazan identificadores como resultados, comparaciones incompletas, correlaciones inviables y relaciones incompatibles/no confirmadas. Se revalida al aceptar. La Sesión 03 revalida el contrato almacenado y relee originales en un proceso acotado antes de calcular; la aceptación sigue sin ejecutar. El motor nunca confía únicamente en estos perfiles: el propietario puede modificar sus filas directamente bajo RLS.

## API

Los campos opcionales aditivos `Plan.components` y `Plan.comparison` permiten reconstruir decisiones en Sesión 03 sin otra tabla ni migración. El integral declara procedimientos y variables; Welch registra grupos, filtros/estratos, diseño, observaciones válidas/ausentes, independencia, atípicos, normalidad, varianzas, efecto/estandarizador e intervalos previstos, propósito y multiplicidad justificada. Se validan antes de proponer y aceptar. Los planes antiguos siguen legibles y una aceptación repetida no los reinterpreta. `clarification_required` distingue impedimentos reales de preguntas opcionales; se conservan las restricciones metodológicas.

La procedencia de mensajes se reconstruye mediante `metadata.request_id` y payloads existentes de `chat_requests`: acciones como `files_ready` se envían con `kind=action`, sin convertirse en finalidad. `goal_evidence` contiene solicitudes estadísticas reales. `stage_data` guarda la pregunta de actualización tras reutilización y la decisión de alcance por especie; respuestas inequívocas se resuelven sin Gemini. Se usan nombres legibles en prosa y IDs solo en referencias estructuradas. La corrección semántica acotada devuelve al modelo la respuesta anterior, dentro del límite de contexto, para que pueda corregirla en vez de regenerar a ciegas.

OpenAPI en `/docs`. Rutas privadas bajo `/projects/{project_id}` con Bearer:

| Método y ruta | Función |
| --- | --- |
| GET / POST `conversations` | Listar / crear; `source_conversation_id` opcional para nueva finalidad confirmada |
| GET / PATCH / DELETE `conversations/{id}` | Detalle / renombrar / eliminar |
| GET `conversations/{id}/messages?before={position}` | Historial anterior |
| POST `conversations/{id}/turns` | Texto/acción con `request_id` UUID idempotente |
| POST `conversations/{id}/files` | Multipart `file` y `file_role` |
| GET `files` | Catálogo ligero para reutilización |
| PUT `files/{id}/sheet` | Elegir hoja mediante `{title: nombre_hoja}` |
| GET `files/{id}/profile` / `download` | Perfil / descarga privada |
| PATCH `conversations/{id}/proposals/{proposal_id}` | Aceptar/rechazar sin ejecutar |

Acciones: `message`, `reuse` (`file_ids` opcionales), `new_files`, `instrument_yes`, `instrument_no`, `instruments_done`, `files_ready`, `keep_goal`. Una carga múltiple solicita una comprensión al terminar; se espera si faltan elegir hojas. HTTP: 401 sesión, 403 permisos del usuario, 404 recurso ajeno/inexistente, 409 conflicto/ocupado, 413 límites, 422 formato/acción, 429 cuota, 502 proveedor/persistencia, 503 configuración o servicio Gemini no disponible, 504 timeout local o del proveedor. Credenciales/permisos del proveedor usan 502 con diagnóstico propio para no confundirlos con la sesión Supabase.

Sin Redis, colas ni arquitectura multiagente. Sesión 04 prepara Render con Python 3.12/un worker, Vercel con fallback SPA y validación de configuración pública, y CORS exacto. Los despliegues y redirects Auth los configura manualmente el usuario: [DEPLOYMENT](DEPLOYMENT.md). No se modificaron cuentas remotas.

## Ajustes finales del asistente

El workspace del asistente ocupa `100dvh` con columnas flexibles, historial plegable y transcripción con scroll propio; el compositor permanece dentro del panel. `ConversationHistory`, `ChatComposer` y `useChatScroll` concentran presentación, teclado/IME y seguimiento/paginación. Conservan servicios, UUID de reintento y bloqueo de mutaciones existentes.

`titles.py` deriva títulos breves de la finalidad auténtica cuando falta la sugerencia; el fallback permanece provisional hasta elegir un plan. `202611150003_chat_titles.sql` actualiza ese título dentro de `decide_proposal`, respetando el bloqueo, la idempotencia y `title_manual`.

La independencia se conserva como supuesto pendiente salvo evidencia metodológica suficiente informada por el usuario; filas distintas no la garantizan. La detección de evidencia es conservadora, no una verificación empírica del diseño. Los objetivos nuevos incluyen nombres de columnas junto a etiquetas legibles para auditar referencias y componentes al proponer y aceptar. Esa comprobación no interpreta exhaustivamente toda prosa libre. La g de Hedges con SD combinada exige ν_H=n1+n2−2 en su corrección, separado de Welch–Satterthwaite. El contrato de transporte Gemini, el perfilado y los planes ya aceptados se conservan.

## Validación de alternativas heterogéneas

`validate_reply` conserva la validación estricta por defecto y se reutiliza al aceptar. Se separan las referencias/afirmaciones de la respuesta, la viabilidad de cada `Plan` y la cobertura de las recomendaciones. Una descripción sin propuestas no tiene cuota de planes; una aclaración imprescindible puede devolverse sin propuestas. Códigos numéricos ambiguos no se convierten en medidas continuas por su representación física.

`assess_reply` reúne incumplimientos por alternativa y todas las columnas explícitas omitidas de su objetivo/método. Hay una sola corrección semántica. `requested_scope.py` deriva compromisos de productos de los mensajes del usuario y los guarda en `stage_data.requested_scope` JSONB v1; no los deriva del proveedor. Si el alcance es ambiguo, histórico truncado o incompleto tras la corrección, se pide una decisión sin propuestas listas para aceptar. Si la segunda respuesta conserva alternativas independientes válidas y no tiene un impedimento global, `retain_valid_plans` revalida ese subconjunto con aviso de respuesta parcial y conserva preguntas; nunca elimina una aclaración esencial para rescatar planes. Una finalidad con varios productos exige cubrirlos juntos, también en `reply_result()` y aceptación nueva. No mezcla planes de distintos intentos ni inventa alternativas. La cuota de cobertura no se presenta como cumplida. Errores de contrato o proveedor conservan el reintento idempotente. Plan v1 y el transporte de los proveedores no cambian; no hay migración SQL nueva. Ver [informe focalizado P1](PR07_P1_REPORT.md).

`statistics/catalog.py` declara productos estructurados junto a sus métodos reales. `plan_capabilities.py` contrasta descriptivos por columna/agrupación e inferenciales por método, familia, variables y opciones de ejecución. Una salida `Componente N: producto` solo puede cubrirla ese componente. Productos comunes a métodos alternativos no eligen el método; IC y opciones pendientes no se acreditan por esa vía. La preparación verifica cada componente localmente y el conjunto antes de informar todo listo; ejecución conserva la revisión completa. Ninguna de estas validaciones modifica fórmulas ni amplía el catálogo de cálculos.

`PlanningError` aporta categorías internas en el punto de validación. Logs: solo intento, índice y categoría permitida; nunca mensajes de excepción, nombres de archivo/columna, prompts, respuestas, credenciales ni registros. `metadata.planning_validation` guarda el diagnóstico seguro de los intentos completados; un fallo terminal incluye `X-Statia-Error: planning_validation` y categorías en `X-Statia-Validation`. La g combinada se valida conjuntamente en definición/corrección: exige una asignación explícita de los gl de J a n1+n2−2 y rechaza usar los de Welch; encontrar el denominador de la SD combinada no basta.


## Motor y resultados (Sesión 03)

`models/analysis.py` define ExecutionSpec y AnalysisResult v1 separados de Plan v1. `statistics/catalog.py` declara el catálogo y `procedures.py` despacha exclusivamente funciones registradas. `preparation.py` reutiliza el perfilado, respeta hojas y aplica decisiones por archivo/columna, filtros y estratos aceptados; no usa overrides globales para ejecución. Tipos físicos y significado estadístico siguen separados. Los descriptivos de archivos múltiples se ejecutan de forma independiente; no hay joins.

`api/analysis.py` autentica con el mismo JWT; `services/analysis.py` coordina relectura, cálculo y persistencia. `analysis_worker.py` ejecuta un hijo Python por API, con control real de tiempo/RSS y terminación del árbol de procesos (incluido el lanzador de venv en Windows). Perfilado y ejecución comparten semáforo. No hay workers adicionales, colas ni promesas de continuidad tras una caída HTTP; reiniciar un intento fallido vuelve a calcular.

La migración `202611150004_analysis_results.sql` añade `analysis_runs` y `analysis_artifacts`, FK compuestas, índices, RLS, RPC invoker y bucket privado `analysis-results`. `begin_analysis_run` bloquea la conversación, verifica el plan aceptado y su snapshot, compara UUID/payload y concede un token por intento. Conversación y ejecución se bloquean en ese orden también al finalizar. Un índice impide dos ejecuciones activas por conversación. Los turnos de chat respetan la concesión del cálculo. A los 180 s un inicio o consulta recupera la ejecución interrumpida como fallida.

Los recursos se suben a `usuario/proyecto/ejecucion/token_intento/ruta_generada`. `finish_analysis_run` comprueba la existencia de los objetos, inserta metadatos, cambia estado y crea un evento de chat en una transacción. Antes no se presenta como completada. Un fallo conocido compensa objetos; si se pierde la respuesta de commit se consulta el estado antes de borrar. Ante estado remoto incierto se conservan objetos para evitar destruir una finalización válida. El mantenimiento debe eliminar huérfanos de intentos y proyectos borrados; no hay un servicio automático de recolección.

Resultados tienen estados completed/partial/failed por ejecución y componente. Guardan especificación, plan original, hashes de originales, dependencias, exclusiones, medidas, tablas, supuestos y rutas de gráficos. Los JSON no contienen NaN/Infinity; una medida no finita se registra como null con advertencia y estado parcial. REST/Storage siguen con JWT y clave publicable, sin credenciales administrativas. RLS protege aislamiento, no acredita la veracidad de JSON que el propio dueño altere mediante acceso directo; los contratos se revalidan al ejecutar y antes de contextualizar Gemini.

`ExecutionReview` exige selección explícita del método; nunca interpreta palabras del método libre. Tipos, orden ordinal, marcadores, independencia/pareamiento, igualdad para clásicos y multiplicidad se revisan antes del envío. El UUID y decisiones pendientes se conservan en sessionStorage por proyecto/conversación/propuesta, sin archivos ni tokens adicionales; al reabrir se exige confirmar otra vez. Cambiar decisiones genera otra solicitud. `AnalysisResultCard` permite tablas, gráficos privados como blobs revocables y descargas; `AnalysisResults` pagina 50 registros y agrupa por conversación. No se altera el compositor ni el historial.

`analysis_context.py` aporta hasta tres ejecuciones recientes con agregados pertinentes, conteos de omisiones y límites de contexto. No envía originales ni tablas de frecuencias completas. Gemini puede explicar resultados guardados y proponer otras ejecuciones, pero nunca calcular ni sobrescribir medidas. Las afirmaciones inferenciales explícitas con símbolos se contrastan con cifras guardadas y redondeo; este control no es un verificador semántico exhaustivo de toda prosa. El texto se mantiene separado de las tablas canónicas. Sin Gemini, la interpretación determinista, persistencia y descargas siguen funcionando. Las preguntas sobre resultados conservan la finalidad y la etapa cuando no proponen otra investigación.

Fórmulas, contratos de API, métodos y límites: [motor estadístico](STATISTICAL_ENGINE.md).


## Correcciones locales de Sesión 6

`requested_scope` reconoce solicitudes habituales y separa exclusiones; las
restricciones comprobables se revalidan al proponer, aceptar, preparar y ejecutar.
Una exclusión de post hoc se conserva como producto restrictivo del plan. ANOVA
Welch global conserva `comparison=null` y todas las categorías observadas; el
contrato `comparison` sigue describiendo comparaciones de dos grupos.

`variable_types.py` reconoce una confirmación explícita por columna inequívoca en
el chat y añade `Plan.type_confirmations` (opcional, backend). La validación aplica
una vista temporal del perfil, sin reescribirlo; la preparación relee el original,
conserva el tipo confirmado y la ejecución rechaza decisiones incompatibles. No
se permite convertir identificadores o fechas en medidas por esta vía. Los planes
anteriores conservan su contrato y decisiones predeterminadas.

Datos consulta el catálogo privado, carga perfiles bajo demanda y descarga por los
servicios de chat existentes. Las nuevas subidas guardan `metadata.content_sha256`;
una carga idéntica del mismo proyecto, rol y formato reutiliza su ID y vínculo. Un
lock serializa cargas en un proceso. No hay unicidad atómica entre procesos ni
compactación de históricos. XLSX con perfil congelado puede crear otra referencia
para seleccionar una hoja diferente. No se incorporan migraciones.

Chat usa react-markdown y remark-gfm sin HTML, con enlaces permitidos y tablas con
scroll propio. Los resultados nuevos pueden añadir `Assumption.origin`; distingue
la declaración del investigador de una comprobación automática. La lectura de
resultados previos no cambia sus cifras ni su procedencia almacenada.

La cuota conserva el código público de error; solo el límite por minuto expone un
Retry-After calculado. Cada proveedor tiene su presupuesto por proceso. No hay
reintentos pagados adicionales ni cambios de cuotas. Ver [informe local](SESSION6_REPORT.md).


## Corrección final de Sesión 6B

La cobertura de resúmenes agrupados reconoce los productos que las comparaciones
registradas ya calculan, para su resultado y agrupador exactos. No acredita globales,
frecuencias ni variables de otros componentes. El alcance diferencia «p global» del
alcance descriptivo; conserva Welch cuando se pide inequívocamente y reconoce sus gl.
Una corrección fallida del proveedor conserva alcance/exclusiones sin pedir redefinir
una solicitud clara. Solo se reconstruyen cachés antiguas si toda su evidencia de
usuario está en el historial completo disponible; no se recortan historiales truncados.

`GET /projects/{project_id}/files/{file_id}/rows?offset=0&limit=50` autentica, comprueba
propiedad/proyecto y usa REST/Storage con JWT y clave publicable. Contrato `FileRows`.
`data_preview.py` lee el original acotado y devuelve hasta 100 filas por solicitud;
el navegador pide 50, únicamente al abrir «Ver datos» o cambiar de página. Relee el
objeto original por página; no hay índice persistente, caché nueva ni migración.
CSV conserva texto, espacios, ceros y marcadores; JSON conserva números sin pérdida
de precisión; XLSX utiliza la hoja seleccionada, fórmulas literales y fechas ISO.
No modifica archivos ni perfiles y no envía registros a IA. PDF sigue en metadatos.

`interpretation_guards.py` cubre patrones observados de asimetría no acreditada,
procedencia inventada y guardado ambiguo en Contexto. Usa la misma corrección
semántica acotada existente, no nuevos reintentos. No es un verificador científico
exhaustivo de prosa. Los UUID de ejecución validados se distinguen de IDs de archivo;
la presentación de un marcador legado no reescribe su mensaje histórico.

El hotfix final muestra la selección pendiente de Excel directamente en el chat;
conserva el único disparo existente de comprensión tras carga/selección.
`descriptive_feasibility.py` anticipa en `validate_plan` los bloqueos descriptivos
conocidos del perfil, tanto al generar como al aceptar. La cardinalidad de subconjuntos
filtrados sigue validándose con datos reales durante preparación. No cambia el motor
ni los planes históricos. Ver [validación y límites](HOTFIX_FINAL_REPORT.md).

## Excel multihoja (Sesión 07)

`workbook.py` abre cada subida una vez con `read_only=True`, procesa hojas
secuencialmente y conserva `workbook_profile_version=1` / `sheet_profiles` en
JSONB existente. Cada entrada registra hoja, estado, advertencias y un perfil
v2 independiente si es examinable. No exige esquemas comunes. Una hoja vacía,
sin encabezados tabulares o fuera de límites no inventa conteos ni impide
examinar otras dentro del presupuesto. Conserva 30 hojas, límites configurados
de bytes/expansión/filas/columnas/celdas y añade un máximo agregado de
`min(400000, MAX_ROWS * MAX_COLUMNS)` celdas de registros por inspección global.
La revalidación de una hoja explícita solo perfila esa hoja.

La comprensión envía `workbook_sheets` al proveedor compartido por Gemini y
Terra: estructura, tipos tentativos, ausencias y avisos, sin muestras ni valores
de otras hojas. Si el contexto no alcanza, conserva todas las hojas y conteos,
reduce detalles de columnas y declara `columns_omitted`; la hoja ejecutable no
se recorta. Si aún no cabe, responde 413. No presupone relaciones ni combina
hojas. Generar/aceptar/ejecutar mantiene la validación de `selected_sheet`.

`GET files/{id}/rows?sheet=...` y `GET files/{id}/profile?sheet=...` son consultas
privadas sin mutaciones. Sin parámetro mantienen la hoja histórica. Datos
conserva una selección local por archivo, reutiliza perfiles disponibles y
remonta la tabla al cambiar de hoja para reiniciar paginación y descartar
respuestas tardías. El original sigue descargándose íntegro. `PUT .../sheet`
conserva el rechazo 409 una vez fijado el perfil y revalida ese estado dentro
del semáforo antes de escribir (un worker por proceso, como en SETUP).

Los libros antiguos se amplían de forma efímera al consultar perfiles o
comprender archivos; no se persisten ni reemplazan su perfil, selección, hashes
u otros metadatos históricos. El navegador reutiliza esa respuesta durante la
vista; una nueva consulta de un libro antiguo puede requerir otra lectura. La
interpretación de resultados históricos no exige volver a descargar el libro.
No hay nueva tabla, migración, caché global de originales ni credenciales nuevas.

El catálogo de productos reconoce N válido, media, mediana, DE muestral, mínimo
y máximo y comprueba que exista cobertura cuantitativa descriptiva global. No
convierte N/media/DE por grupo en una solicitud global adicional. La caché de
alcance usa recognizer_version=3 y solo se reconstruye con evidencia completa
del usuario. Se conserva el límite de solicitudes y la única corrección existente;
no se cambian fórmulas ni el motor. Ver [informe de validación](SESSION7_REPORT.md).


## Instrumentos y estabilidad de tesis (Sesión 08)

`instruments.py` unifica PDF/pypdf y Word DOCX/ZIP+defusedxml. Valida bytes,
contenedor OPC, partes principales, namespaces, CRC, entradas, expansión y
compresión. Rechaza DTD/entidades incluso en XML UTF-16, macros, objetos activos,
cifrado y formatos incompatibles. No extrae a disco, no ejecuta documentos ni
resuelve relaciones externas. `instrument_worker.py` procesa originales por
stdio en un hijo cancelable con timeout/RSS observada; reutiliza únicamente
la terminación de procesos existente, sin cambiar el motor estadístico.

Metadatos aditivos JSONB: `instrument_extraction_version`, `extraction_status`,
`extracted_chars`, `fragments` (texto, ubicación y desplazamiento), advertencias
y páginas/partes. `text_excerpt` conserva una vista previa compatible de 16 000
caracteres. El límite total recuperado es 240 000 caracteres con solapamientos
y 600 fragmentos; nunca acredita que imágenes, orden visual o etiquetas de
numeración estén íntegros. PDF conserva ubicación por página; DOCX por parte
y párrafo. El archivo original sigue en el mismo bucket privado y con JWT/RLS.
La migración 009 es necesaria por los CHECK/MIME que antes solo admitían PDF;
no modifica políticas, tablas ni registros históricos. No se ejecutó en remoto.

`instrument_context.py` busca términos/códigos sin embeddings, red ni significado
inferido. Comparte solo fragmentos autorizados por `share_instrument_text`, hasta
diez/12 000 caracteres por turno, con ubicaciones y omisiones. Las coincidencias
de distintos códigos/documentos preceden a vecinos con posibles opciones. El
proveedor recibe texto como dato no confiable y debe distinguir literal/paráfrasis/
inferencia. Se rechazan códigos sin evidencia y citas literales entre «» no
recuperadas; estos controles finitos no acreditan toda la semántica de una respuesta.
Sin consentimiento o coincidencias documentales, responde el servidor sin llamada
al proveedor. Con autorización, los originales históricos pueden reextraerse
efémeramente; no se sobrescriben sus metadatos. Mensajes ya enviados siguen
formando parte del historial; revocar el envío nuevo no borra ese historial.

Los modos `understanding`, `document`, `methodology` y `planning` distinguen
consultas de propuestas. Los primeros no aplican alcance pendiente de planes ni
cuotas de recomendaciones y descartan planes no solicitados antes del contrato
interno, tanto en Gemini como Terra. `reply_contract.py` normaliza un único paso
redundante solo si coinciden procedimiento (o envoltura integral), método exacto,
referencias/roles/orden y ausencia de dependencias; luego se ejecutan todos los
validadores existentes. Un método distinto no se convierte. Los alias descriptivos
por defecto acreditan productos explícitos solo tras comprobar cobertura real.
Comprensión no define finalidad ni guarda planes. Resultados existentes tampoco
suprimen la recuperación de una consulta documental.

Se reserva hasta 4000 caracteres del presupuesto total del proveedor para la
corrección semántica ya existente; el resto del contexto indispensable debe caber
o se devuelve 413. Las categorías distinguen validación de respuesta/documento y
de planificación; los errores de transporte/formato/cuota conservan sus códigos.
No cambian cuotas, reintentos, idempotencia, catálogos ni fórmulas.

`current_context` sigue leyendo la revisión vigente confirmada en cada turno de
tesis. La UI compara el borrador normalizado, no el orden de claves adicionales,
y muestra revisión y cambios pendientes. La API devuelve la revisión existente
si recibe el mismo documento y la revisión esperada; las escrituras nuevas siguen
el RPC con control de conflictos. No hay guardado desde chat ni dependencia de
Contexto para General.

La presentación oculta trazas técnicas por defecto sin modificar IDs persistidos.
Una solicitud expresa puede mostrar IDs de ejecuciones verificados. La vista
`ResponseMeaning` requiere selección local del investigador sobre categorías de
no información, comprueba que la tabla de frecuencias esté completa y distingue
valores presentes/respuestas sustantivas/ausencias registradas. No reescribe
resultados, porcentajes, gráficos ni exportaciones y no transmite esa selección al
proveedor. Detalles y pendientes: [Sesión 08](SESSION8_REPORT.md).
