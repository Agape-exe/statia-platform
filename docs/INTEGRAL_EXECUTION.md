# Ejecución integral por componentes

## Causa y comportamiento

La preparación evaluaba preguntas, incertidumbres y errores como listas globales. Una respuesta desconocida de independencia impedía validar incluso un descriptivo que no dependía de ella. Ahora cada pregunta e impedimento se vincula a sus componentes y se reutilizan `ExecutionSpec`, el catálogo, `prepare`, `validate_spec`, `check_conditions` y el mismo despachador Python.

Cada componente conserva id estable dentro de la propuesta (`component:índice`), variables, método, decisiones, filtros, evidencia, supuestos, preguntas relacionadas, huella, dependencias, advertencias y bloqueo. Sus resultados se relacionan por `source_index` y `completed_run_id`. Los estados de preparación son READY, NEEDS_CLARIFICATION, BLOCKED_UNCERTAINTY, UNSUPPORTED y COMPLETED; los resultados añaden FAILED. RUNNING se representa durante la operación por el estado de ejecución y «Calculando» en la interfaz; no se guardan resultados numéricos antes del commit final.

La preparación conjunta puede ser PARTIALLY_READY. El servidor propone exclusivamente los componentes disponibles; **Ejecutar componentes disponibles** confirma esa selección. Revisar los pendientes o dejar pendiente todo el análisis no calcula nada. Cuando ninguno está listo no se ofrece ejecutar. Si todos están listos se conserva la ejecución completa habitual. Una continuación con todos los pendientes listos se presenta como READY y solicita ejecutar únicamente esos pendientes.

En Titanic, confirmar `survived` como categórica y desconocer independencia permite ejecutar el descriptivo de los registros observados. La correlación inferencial y el ANOVA de Welch permanecen pendientes. No se sustituye Pearson ni ANOVA por otros procedimientos ni se cambia el plan aceptado. Los coeficientes descriptivos y las comparaciones de distribuciones no se presentan como pruebas inferenciales: esta corrección ejecuta los descriptivos ya incluidos en el plan; no crea silenciosamente nuevos componentes de correlación descriptiva o comparación grupal.

Los descriptivos preparados automáticamente excluyen pruebas e intervalos de confianza de media. Las fórmulas y los resultados históricos se conservan. El modo avanzado prepara descriptivos sin IC; cualquier especificación que solicite IC de media debe confirmar independencia explícitamente. El parámetro aditivo `descriptive_intervals=false` evita calcular el IC en este recorrido; media, mediana, SD, varianza, cuartiles y frecuencias mantienen sus fórmulas.

## Seguridad, persistencia y continuación

`ExecutionSpec.partial_execution` permite una selección, sin duplicados ni índices ajenos. El endpoint exige preparación vigente, UUID estable, huella, especificación exacta y confirmación. El proceso acotado vuelve a preparar sobre los originales y comprueba la misma selección. El modo avanzado no puede omitir componentes mediante ese campo sin preparación. Se conservan Auth, RLS, JWT/publicable, leases, límites de recursos, hashes, originales privados e idempotencia.

`AnalysisResult.component_states` registra el estado completo del plan, incluidos los componentes sin resultados. Un run parcial almacena únicamente los cálculos realizados, manteniendo el snapshot íntegro del plan aceptado. El JSON y el manifiesto del ZIP declaran estado parcial, bloqueos y referencias de continuidad. No se crean tablas, valores p ni ceros para procedimientos pendientes. Los recursos previos siguen en sus runs y ZIP privados; una continuación los referencia, sin duplicarlos dentro del ZIP nuevo.

Al volver a preparar, se consultan estados y snapshots de runs de esa propuesta/conversación mediante proyección JSONB paginada, sin cargar tablas ni gráficos. Las huellas por componente incluyen el procedimiento, originales relevantes, decisiones y parámetros. Solo se reutiliza un componente completado con huella compatible y snapshot idéntico. Una respuesta posterior revalida los pendientes; la ejecución siguiente requiere otra confirmación y conserva los resultados anteriores. Datos o decisiones incompatibles requieren preparar de nuevo. El modo avanzado permite una ejecución nueva explícita.

Las dependencias `Plan.components[].depends_on` son prerrequisitos entre índices: se validan referencias/ciclos, se propagan bloqueos y el cálculo sigue un orden topológico. Un fallo impide ejecutar sus dependientes. El catálogo continúa consumiendo columnas de originales, no tablas producidas por otros métodos; no se introducen transformaciones ni uniones. Las familias Holm se mantienen juntas; si una familia necesita recalcularse para mantener el ajuste, se explica y se conservan sus resultados anteriores.

Reintentar un UUID completado con las mismas decisiones recupera el run persistido, incluso después de otra preparación. Otra especificación o snapshot con el mismo UUID se rechaza. La continuación tiene su propia solicitud estable y no sobrescribe el run parcial.

## Conversación y presentación

La migración aditiva **005** vincula propuestas nuevas mediante `source_message_id` con clave foránea a un mensaje de la misma conversación. El RPC guarda mensaje y propuestas en la misma transacción. Las asociaciones nuevas de archivos generan eventos con posición persistida. Aceptaciones y resultados siguen utilizando eventos existentes. La aceptación nueva ya no menciona el calendario de desarrollo; no se reescriben mensajes históricos.

El frontend intercala propuestas y preparaciones junto a sus mensajes, siguiendo posiciones del servidor; el resultado ocupa su evento de ejecución. La paginación mantiene estos vínculos. Una propuesta cuyo mensaje de origen aún no está cargado espera esa página. Las propuestas históricas sin vínculo se conservan en una sección expresamente identificada, sin asignarles una cronología ficticia.

Las propuestas decididas y las preparaciones usadas quedan plegadas. El GET identifica la ejecución de la preparación actual incluso si su evento está fuera de la página. Los controles históricos no confirman ni ejecutan de nuevo. Los resultados parciales ofrecen revisar los componentes pendientes.

Cada resultado tiene un ancla estable por run. Tras recuperar el evento persistido, la vista navega a su tarjeta si el usuario sigue la ejecución. Si se ha desplazado para leer el historial, conserva esa posición y muestra **Ver resultado disponible**. La navegación actúa sobre el área de mensajes y no desplaza toda la página.

El asistente elimina el breadcrumb, título y descripción repetidos, mantiene un h1 accesible sin ocupar espacio y usa proyecto/conversación en el encabezado compacto. Conserva identidad, navegación, renombrado, eliminación, nuevo chat, historial plegable y compositor visible. Se ocultan listas vacías y se presentan nombres de archivo, hoja, columna y marcador en lugar de referencias JSON internas. La prosa del proveedor no confirma independencia ni garantiza intervalos fuera del catálogo.

## Instalación y validación

Aplicar `supabase/migrations/202611160005_chat_timeline.sql` después de 001–004. No repetir ni editar migraciones aplicadas. Reiniciar API y frontend para cargar contratos consistentes antes de probar.

Las regresiones cubren Titanic original (891×15), nombres sintéticos, múltiples archivos, todos listos, ninguno ejecutable, incertidumbre selectiva, dependencias/ciclos, continuidad, integridad ZIP, hashes y reintentos. La prueba HTTP utiliza rutas, proceso Python, tablas, gráficos y exportación reales con Auth/REST/Storage en memoria. SQL/PGlite comprueba transacciones, vínculo de propuesta, RLS, aislamiento y eventos. El frontend verifica orden, parcialidad, controles, scroll manual, navegación por identidad, historial, listas y referencias legibles.

Una llamada real a Gemini con el perfil público de Titanic produjo una propuesta integral que superó `AssistantReply` y los validadores del servidor. No acredita una conversación autenticada con Supabase remoto. Las pruebas nuevas de persistencia y Storage usan dobles y SQL local; queda pendiente comprobar la migración y el recorrido autenticado con dos cuentas remotas.

Los resultados finales de comandos y de navegador se registran en `VALIDATION.md`. No hay cambios de fórmulas inferenciales ni procedimientos estadísticos nuevos. Se mantienen los límites y advertencias de infraestructura de `STATISTICAL_ENGINE.md`.


## Archivos de esta corrección

- `README.md`
- `backend/app/api/chat.py`
- `backend/app/models/analysis.py`
- `backend/app/models/chat.py`
- `backend/app/services/analysis.py`
- `backend/app/services/analysis_exports.py`
- `backend/app/services/conversation.py`
- `backend/app/services/execution_preparation.py`
- `backend/app/services/methodology.py`
- `backend/app/services/statistics/automatic.py`
- `backend/app/services/statistics/engine.py`
- `backend/app/services/statistics/numerics.py`
- `backend/app/services/statistics/preparation.py`
- `backend/app/services/statistics/procedures.py`
- `backend/scripts/check_analysis_quality.py`
- `backend/tests/test_automatic_preparation.py`
- `backend/tests/test_integral_execution.py`
- `backend/tests/test_statistics.py`
- `docs/ARCHITECTURE.md`
- `docs/EXECUTION_UX.md`
- `docs/INTEGRAL_EXECUTION.md`
- `docs/SETUP.md`
- `docs/STATISTICAL_ENGINE.md`
- `docs/VALIDATION.md`
- `frontend/src/components/AnalysisResultCard.tsx`
- `frontend/src/components/ComponentStates.tsx`
- `frontend/src/components/ExecutionPreparationCard.tsx`
- `frontend/src/components/ExecutionReview.tsx`
- `frontend/src/components/ProposalCard.tsx`
- `frontend/src/components/StatisticalChat.tsx`
- `frontend/src/hooks/use-chat-scroll.ts`
- `frontend/src/index.css`
- `frontend/src/pages/Workspace.tsx`
- `frontend/src/test/analysis.test.tsx`
- `frontend/src/test/chat-scroll.test.tsx`
- `frontend/src/test/chat.test.tsx`
- `frontend/src/types/analysis.ts`
- `frontend/src/types/chat.ts`
- `supabase/migrations/202611160005_chat_timeline.sql`
- `supabase/tests/analysis.test.mjs`
- `supabase/tests/chat.test.mjs`
