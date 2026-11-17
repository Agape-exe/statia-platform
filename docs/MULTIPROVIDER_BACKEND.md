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

Aplicar manualmente **solo** `supabase/migrations/202611170007_assistant_providers.sql`
después de 001–006, revisando el proyecto y su historial. No se aplicó en esta sesión.
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
delega a `begin_chat_turn`, conservando la serialización con ejecuciones Python y el
payload original. Fija el destinatario/modelo en `chat_requests` antes de generar. Los
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

Se elige **advertir**, mediante una regla determinista para cualquier descriptivo agrupado,
en vez de interpretar toda prosa libre o ampliar el motor. El aviso se añade a las
advertencias de respuesta y limitaciones del plan nuevo, conservando las restricciones
anteriores. La aceptación de esos planes devuelve también el aviso; los históricos
no se reescriben. Si se requieren todos esos productos, solicitar planes separados y
revisarlos antes de ejecutar. La advertencia no demuestra cobertura completa de cualquier
promesa textual ni corrige automáticamente un plan. No se añaden cálculos ni uniones.

## Validación y pendientes

Las pruebas usan `httpx.MockTransport`, repositorio controlado y PostgreSQL WASM con
Auth/Storage emulados. No llaman a modelos ni consumen créditos. La suite SQL aplica
001–006, crea historial y después aplica 007 para comprobar compatibilidad, RLS,
privilegios, replay, instantáneas, eventos y bloqueos. Esto no acredita una instalación
remota Supabase. La regresión del motor sigue usando Python determinista con datasets
sintéticos. Los informes históricos del PR #6 permanecen intactos.

Pendientes externos: revisión/aplicación manual de 007 en el entorno autorizado,
prueba de aislamiento con dos cuentas reales, autorización separada para cualquier
prueba pagada y revisión del selector frontend. No hay despliegue ni cambios productivos.
