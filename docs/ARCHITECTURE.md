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

`profiling.py` lee CSV/JSON/XLSX/PDF sin modificar ni combinar originales. Limita bytes, filas, columnas, celdas, hojas, páginas y expansión; un perfilado por proceso. XLSX comprueba ZIP y usa lectura incremental. pypdf limita streams y decodificación; sin texto conserva el PDF y comunica que no hay OCR. Varias hojas requieren elección; después el perfil queda congelado para no alterar referencias de planes.

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
