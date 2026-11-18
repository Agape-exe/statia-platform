# Backend multiproveedor (Sesión 5A)

Gemini sigue siendo el predeterminado. Terra es una alternativa experimental de
planificación e interpretación, **no declarada preparada para producción**. Ambos usan
el mismo contexto redactado, instrucciones, `AssistantReply`, `Plan`, referencias exactas,
validadores metodológicos y numéricos, corrección semántica y persistencia. Solo Python
ejecuta estadísticas después de las decisiones y confirmaciones existentes.

## Configuración y migración

Configurar solo en backend, según `.env.example`:

| Variable | Predeterminado | Alcance |
| --- | --- | --- |
| `OPENAI_TERRA_ENABLED` | `false` | Habilitación experimental explícita del servidor |
| `OPENAI_API_KEY` | vacío | Credencial secreta exclusivamente del backend |
| `OPENAI_TIMEOUT_SECONDS` | 60 | Presupuesto completo por generación, entre 5 y 65 s |
| `OPENAI_MAX_OUTPUT_TOKENS` | 12000 | Máximo de salida por solicitud, incluidos tokens de razonamiento; 256–16000 |
| `GEMINI_MAX_OUTPUT_TOKENS` | 7000 | Máximo de salida Gemini; 256–16000 |
| `AI_REQUESTS_PER_MINUTE` | 20 | Ventana móvil por proveedor y proceso; 1–120 |
| `AI_MAX_REQUESTS_PER_TURN` | 4 | Solicitudes por turno, incluidas correcciones/reintentos; 1–4 |

El identificador HTTP permitido es `openai` y su modelo fijo es `gpt-6.1-terra`.
No existe un campo HTTP ni una variable para elegir otro modelo OpenAI. Gemini
conserva `GEMINI_MODEL`. Mantener las claves fuera de `VITE_*`, respuestas y logs.
El servidor arranca sin claves; el catálogo informa disponibilidad sin exponerlas.

La instalación requiere 007 y la corrección aditiva 008 antes del backend corregido.
No repetir 007 si ya existe ni revertir sus funciones al recuperar el backend. Ver
[secuencia manual y recuperación segura](PR07_SAFE_ROLLOUT.md); no se aplicaron migraciones remotas.
Es transaccional y aditiva: añade `conversations.assistant_provider` con default Gemini
y `chat_requests.provider/model`. Las conversaciones y solicitudes previas corresponden
a Gemini; el modelo histórico desconocido queda `null`. Los mensajes antiguos mantienen
sus bytes/metadata: no se inventa una atribución exacta de modelo.

Los tres RPC nuevos son `security invoker`, con `search_path` vacío y ejecución solo
para `authenticated`. Se conserva el RLS por propietario y el JWT/clave publicable
de REST/Storage; no se usan credenciales administrativas. Las firmas de los RPC previos
siguen disponibles para compatibilidad. Los nuevos campos también quedan bajo RLS.
Como en el resto de Statia, RLS aísla usuarios; no acredita la veracidad de snapshots
que el mismo propietario pueda alterar directamente por REST.

## Contrato HTTP para la siguiente sesión frontend

Todas las rutas requieren Bearer y pertenecen a `/projects/{project_id}`:

| Operación | Contrato |
| --- | --- |
| `GET /assistant-providers` | `{default:"gemini", providers:[{id,name,model,experimental,enabled,configured}]}` |
| `POST /conversations` | Añade `provider:"gemini"|"openai"`, opcional con default Gemini; conserva `source_conversation_id` |
| `PATCH /conversations/{id}/provider` | `{provider:"openai",expected_provider:"gemini"}`; devuelve conversación actualizada |
| `GET /conversations` y `GET /conversations/{id}` | Conversación incluye `assistant_provider` |
| `POST /conversations/{id}/turns` | Conserva su contrato y UUID; usa la selección persistida |

Una nueva finalidad crea por defecto otra conversación Gemini; no hereda Terra
silenciosamente. La selección OpenAI requiere tanto habilitación como clave. Un cambio
de proveedor requiere disponibilidad del destino. El usuario puede seguir creando
conversaciones Gemini y usar flujos deterministas aunque falte su clave.

Frontend deberá añadir selector Gemini/Terra, etiqueta experimental, disponibilidad y
estados de carga/fallo; informar **antes de confirmar** que el destino recibirá los próximos
mensajes y el contexto compartido, que puede incluir historial previo, perfiles y resultados
agregados. Mantener los controles existentes de muestras/PDF. Al cambiar selección,
enviar `expected_provider`, actualizar desde la respuesta y gestionar 409 recargando.
No enviar modelos arbitrarios ni guardar claves. No se modificó frontend en esta sesión.

Las respuestas nuevas incluyen `metadata.selected_provider` y `metadata.generation`
con proveedor, modelo solicitado, número de solicitudes y métricas seguras por generación
(incluido `response_model` cuando el proveedor lo informa y tiene formato seguro).
Las respuestas deterministas usan `generation:{source:"deterministic"}`. Frontend deberá
mostrar procedencia histórica desde esa metadata, nunca desde la selección actual;
para mensajes previos sin metadata indicar modelo histórico no registrado. Los eventos
`provider_selected` documentan cambios explícitos sin reescribir mensajes o resultados.

## Concurrencia, consumo e idempotencia

`begin_provider_chat_turn` bloquea la fila de conversación, comprueba selección/modelo y
adquiere directamente el turno con serialización con ejecuciones Python y el
payload original. En 008 ya no delega a `begin_chat_turn`: el RPC legacy solo permite
Gemini sin modelo vinculado y replay completado, y lanza conflicto para cualquier
destinatario/modelo que el backend anterior no puede acreditar. Fija el destinatario/modelo en `chat_requests` antes de generar. Los
triggers impiden cambios durante turnos o cálculos activos, incluso por escritura REST
directa; el cambio y su evento se guardan en una transacción.

Un replay completado conserva su resultado sin llamar a ningún proveedor, incluso tras
un cambio de selección. Reintentar un turno fallido con otro proveedor o un modelo de
servidor distinto devuelve 409: requiere una nueva solicitud explícita con otro UUID.
Un payload distinto con el mismo UUID sigue siendo conflicto. Cambiar proveedor no
borra propuestas, preparaciones, decisiones, resultados, recursos ni mensajes.

OpenAI hace una solicitud por generación, sin herramientas, redirecciones, reintentos HTTP
ni fallback. Usa Responses API, `store:false`, esfuerzo `medium` y el mismo conversor
estricto de objetos cerrados/campos requeridos/nullable validado en las pruebas aisladas.
No se importa ni ejecuta el diagnóstico durante el flujo productivo. La orquestación
permite como máximo una corrección semántica, que **puede consumir una segunda solicitud**.
Un error HTTP, timeout, JSON inválido o respuesta incompleta no activa esa corrección.
Gemini conserva su único reintento transitorio existente y presupuesto de 65 s; sus
solicitudes también consumen los límites nuevos. Dos generaciones caben dentro del
presupuesto del turno de 150 s y su concesión de 180 s.

Las cuotas reservan solicitudes antes de contactar al proveedor. Son barreras locales,
no una cuota monetaria o distribuida: reiniciar el proceso reinicia la ventana y varios
workers multiplican el límite. Mantener un worker como prescribe Statia. El contexto
continúa limitado por caracteres; no hay un conteo exacto previo de tokens de entrada.
Para limitar también la corrección pagada, configurar `AI_MAX_REQUESTS_PER_TURN=1`.
Un timeout/cancelación puede dejar consumo remoto desconocido; no se consulta ni se
reintenta automáticamente esa generación.

Se registran identificadores seguros de solicitud/respuesta y tokens disponibles de
entrada/salida/cache/razonamiento, sin sumar razonamiento otra vez a la salida OpenAI.
Los ausentes quedan `null`; no se inventan tarifas ni costos. Los logs `Provider generation`
usan nivel INFO: habilitar ese logger en el servidor para conservar métricas también de
intentos fallidos. El estado por turno usa ContextVar para evitar mezclar métricas concurrentes.
No se guardan prompts, contenido de razonamiento, cabeceras ni cuerpos de error crudos.

Los diagnósticos OpenAI usan `X-Statia-Error: openai_*` y `X-OpenAI-Status` cuando existe
respuesta HTTP. Distinguen configuración, esquema, modelo, credenciales, permisos, cuota,
indisponibilidad, conectividad, timeout, generación incompleta, negativa y contrato inválido.
`provider_request_limit` es cuota local; `planning_validation` conserva las categorías
estadísticas compartidas. No se atribuye un 401 OpenAI a la sesión Supabase del usuario.

## Límite descriptivo de la prueba I

`describe()` calcula resúmenes por grupo cuando existe `role=group` y excluye esa
columna de las frecuencias. Un solo componente no produce simultáneamente el resumen
global, el agrupado y las frecuencias del agrupador que prometió I.

La corrección del bloqueo A usa un catálogo finito de productos, no una interpretación
exhaustiva mediante patrones. `validate_products` contrasta el alcance y las columnas
contra los componentes, hojas y archivos declarados. Distingue resúmenes globales,
por grupo, frecuencias globales, por grupo y del agrupador. La integral puede separar
estos productos en componentes descriptivos de alcances distintos sin ampliar cálculos.

La regla se comparte en generación/corrección semántica, aceptación, preparación y
validación de ejecución, también dentro del hijo Python. Una incompatibilidad devuelve
`output_capability`; un texto no reconocible devuelve `output_scope` y exige aclarar
el alcance en una propuesta revisada. No se recortan `expected_outputs` ni se reescribe
el plan histórico. `warn_capabilities` ya no añade limitaciones ni repara nada.

Los productos canónicos son: «Resúmenes globales», «Resúmenes por grupo», «Frecuencias
categóricas», «Frecuencias categóricas por grupo» y «Frecuencias de la variable de
agrupación». Su alcance cubre las columnas pertinentes declaradas por el plan, por tabla;
no se adivinan subconjuntos a partir de prosa. Los alias exactos históricos genéricos
(p. ej. «Tabla descriptiva», «Tablas y gráficos») solo describen los productos ordinarios
del componente, sin acreditar productos globales o frecuencias adicionales. La lista
cerrada vive en `plan_capabilities.py`; frases fuera de ella requieren aclaración.
Los controles inferenciales existentes permanecen independientes y no se relajan.

Las instrucciones nuevas de producción se agregan a las de ambos proveedores. El
`SYSTEM` exportado histórico y el diagnóstico aislado conservan sus bytes/payloads.
La evidencia M original se mantiene: las propuestas con productos no verificables
ahora se bloquean, aunque hubieran aprobado reglas metodológicas anteriores.

## Validación y pendientes

Las pruebas usan `httpx.MockTransport`, repositorio controlado y PostgreSQL WASM con
Auth/Storage emulados. No llaman a modelos ni consumen créditos. La suite SQL aplica
001–006, crea historial y después aplica 007; la reproducción de rollback compara 007 sola con 007 + 008 para comprobar compatibilidad, RLS,
privilegios, replay, instantáneas, eventos y bloqueos. Esto no acredita una instalación
remota Supabase. La regresión del motor sigue usando Python determinista con datasets
sintéticos. Los informes históricos del PR #6 permanecen intactos.

Pendientes externos: revisión/aplicación manual de 007/008 en el entorno autorizado,
prueba de aislamiento con dos cuentas reales, autorización separada para cualquier
prueba pagada y revisión del selector frontend. La publicación original del PR activó
una preview automática de Vercel; estas correcciones permanecen locales, sin push,
despliegues ni cambios productivos.
