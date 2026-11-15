# Arquitectura

El navegador conserva Supabase JS para Auth y CRUD de proyectos. `AuthProvider` recupera y renueva la sesión; guards esperan la inicialización y las rutas privadas se remontan al cambiar de usuario. El chat se carga bajo demanda dentro del workspace existente. Presentación en `components`/`pages`, consultas en `services`, clientes en `lib`, contratos en `types`.

`lib/api.ts` adjunta el JWT a FastAPI, renueva una vez ante 401 y permite recuperar acceso si vence la sesión. `core/auth.py` consulta `/auth/v1/user`, sin confiar en una identidad proporcionada por el cliente. REST/Storage usan ese mismo JWT y la clave publicable. No hay `service_role` ni CRUD duplicado de proyectos.

## Persistencia y seguridad

La migración `202611150002_chat.sql` añade `conversations`, `messages`, `project_files`, `conversation_files`, `analysis_proposals` y `chat_requests`. RLS protege las cuatro operaciones por propietario del proyecto; claves compuestas impiden asociar archivos entre proyectos, incluso del mismo usuario. Triggers impiden mover registros entre padres. Los mensajes tienen posición monotónica e historial paginado de 100 en 100.

El bucket privado `project-files` usa `usuario/proyecto/uuid/nombre_seguro`, sin sobrescribir originales. Subir/registrar tienen compensación ante fallos; reutilizar solo crea relaciones. Eliminar chats conserva archivos. Eliminar proyectos borra metadatos por cascada, pero requiere limpieza de objetos físicos huérfanos desde Storage (ver SETUP).

Los RPC son `security invoker` y respetan RLS. `create_conversation` guarda bienvenida/etapa inicial. `begin_chat_turn` guarda el mensaje y adquiere una concesión de 180 s: UUID y payload deben coincidir al reintentar. `finish_chat_turn` guarda respuesta, propuestas, asociaciones y etapa atómicamente; `fail_chat_turn` conserva el mensaje y libera el turno. Una caída permite recuperar la concesión vencida. `decide_proposal` registra decisión y evento en una transacción.

## Conversación, perfilado y proveedor

Etapas: `reuse → instrument → upload_instrument → upload_dataset → understanding → clarification → goal → proposal → ready`. Sin instrumento se pasa a datasets; reutilización con datasets pasa a comprensión. Rechazo vuelve a finalidad, o conserva `ready` si hay otro plan aceptado. Bienvenida e incorporación son lógica explícita. Gemini solo sugiere etapas; el servidor controla transiciones y nunca acepta planes por decisión del modelo.

Tesis requiere aclaraciones metodológicas; general permite explorar sin conocimientos previos. Finalidad y resumen de entendimiento persisten además del historial. `research_context=null` en `build_context` es el punto de integración del futuro Contexto. Un cambio de finalidad queda pendiente en `stage_data.goal_change`; solo la acción del usuario crea otro chat, conservando el anterior y ofreciendo reutilización. Renombrar manualmente desactiva títulos automáticos.

`profiling.py` lee CSV/JSON/XLSX/PDF sin modificar ni combinar originales. Limita bytes, filas, columnas, celdas, hojas, páginas y expansión; un perfilado por proceso. XLSX comprueba ZIP y usa lectura incremental. pypdf limita streams y decodificación; sin texto conserva el PDF y comunica que no hay OCR. Varias hojas requieren elección; después el perfil queda congelado para no alterar referencias de planes.

El perfil calcula tipos físicos, tipos estadísticos tentativos, faltantes, duplicados, cardinalidades, distribuciones, min/max/media y pequeñas muestras. El significado es una hipótesis: un número puede ser identificador o escala.

`GeminiProvider` implementa `Provider` con `google-genai`, modelo configurable, salida Pydantic, timeout, un reintento transitorio y máximo una corrección semántica. Contexto limitado por caracteres, sin archivos completos. Muestras/extractos PDF se habilitan en el compositor; se omiten valores de identificadores detectados y redactan patrones sensibles. La detección es parcial: el usuario debe revisar qué comparte. PDF y mensajes son datos no confiables, sin herramientas de ejecución.

`AssistantReply` representa texto, preguntas, finalidad/título, variables, advertencias, cambio de finalidad y propuestas. `Plan` versión 1 contiene variables `{file_id,sheet,column,role}`, procedimiento, método, justificación, requisitos, limitaciones, productos esperados y relaciones declaradas. Se validan archivos asociados, hojas y columnas exactas; se rechazan identificadores como resultados, comparaciones incompletas, correlaciones inviables y relaciones incompatibles/no confirmadas. Se revalida al aceptar. Supuestos y ejecución corresponden a Sesión 03; no se calculan resultados inferenciales. El futuro motor deberá revalidar el JSON almacenado y los originales: el propietario puede modificar sus filas directamente bajo RLS.

## API

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

Acciones: `message`, `reuse` (`file_ids` opcionales), `new_files`, `instrument_yes`, `instrument_no`, `instruments_done`, `files_ready`, `keep_goal`. Una carga múltiple solicita una comprensión al terminar; se espera si faltan elegir hojas. HTTP: 401 sesión, 403 permisos, 404 recurso ajeno/inexistente, 409 conflicto/ocupado, 413 límites, 422 formato/acción, 429 cuota, 502 proveedor/persistencia, 503 configuración, 504 timeout.

Sin Redis, colas ni arquitectura multiagente. Vercel/Render siguen siendo destinos previstos; no se despliegan en esta sesión. Producción requerirá fallback SPA, orígenes CORS y redirects Auth.
