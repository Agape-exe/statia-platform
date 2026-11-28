# Diagnóstico de planificación con Gemini real

El trabajo parte del merge del PR #12 en `origin/develop` (`1a1e462`). La rama local es `fix/robustez-planificacion-gemini`. La evidencia histórica corresponde al planificador 7. El nuevo identificador del planificador es 8.

## Qué se pudo atribuir

| Caso | Evidencia histórica | Reproducción y causa comprobada en local |
| --- | --- | --- |
| E2E-05 | Tanto el chat nuevo como el histórico devolvieron 200 sin tarjeta. El mensaje manual de entregables corresponde a `output_capability` en el código del despliegue. | Gemini eligió `welch_t`. En el primer intento propuso g de Hedges sin especificar correctamente los gl del factor J. En el segundo corrigió esa definición y conservó cinco entregables. El número 2, «Estadístico de prueba global», se tradujo a `global_test`, que el catálogo reserva para pruebas globales. «Tamaño del efecto» tampoco era un producto verificable y la prosa de ese intento prometía un IC del efecto que Python no calcula. La corrección solo conocía la primera regla fallida. |
| Welch manual | El mensaje público permite identificar la categoría, pero no el producto histórico exacto. | La palabra «significativa» coincidía con el patrón de interpretación «significa». El turno seguía en planificación, pero omitía `requested_scope` y el método exigido por el usuario. La reproducción también encontró un rechazo de la definición de Hedges. La misma solicitud manual completó posteriormente el cálculo con Gemini real. |
| E2E-06 | Contexto de tesis persistido y CSV cargado. El 200 sin tarjeta conserva el alcance y no identifica el detalle del intento histórico. | La solicitud directa produjo una propuesta válida en la base. Con la comprensión previa, dos respuestas anunciaron un plan no solicitado durante `files_ready`, ocasionando `proposal_missing`. En otra reproducción, ya en planificación, el resultado numérico tenía tipo tentativo `categorical_or_ordinal`. Media, mediana, DE, extremos y N fueron rechazados por exigir un descriptivo cuantitativo. El contexto de tesis daba la escala, pero no constituía una decisión ligada a archivo, hoja y columna. |
| E2E-07 | El instrumento original describe un puntaje de 0 a 100. El ZIP conserva el plan, especificación y tabla. La variable figura como `outcome`, producto «Resúmenes globales», sin `type_confirmations`. | El perfil reconoce los números, pero las 12 observaciones tienen exactamente 12 valores distintos. El umbral del perfil devuelve `categorical_or_ordinal`. La preparación descriptiva asignaba automáticamente `nominal`, llegaba a «Listo» y el motor ejecutaba correctamente frecuencias para esa especificación. La automatización confirmó el cálculo sin elegir un tipo. La tarjeta había justificado una descripción cuantitativa. |
| E2E-08 | Rechazo aceptado. El servidor devolvió 502 con `component_variables` en la reformulación y 200 sin tarjeta en el reintento. | En dos respuestas reales solicitadas después del rechazo, el plan simple decía «Estadística descriptiva univariada con filtro» y su componente «Estadística descriptiva univariada». El componente trataba `grupo` como predictor y `medicion` como resultado. El esquema de transporte carecía de `Plan.filters` y la restricción solo aparecía en prosa. Borrar el componente habría dejado un análisis sin el filtro ejecutable. Para aislar la reformulación antes de la corrección, la propuesta inicial se sembró con un proveedor controlado. Las dos reformulaciones fueron de Gemini. |

Los registros de los dos intentos se conservaron por separado. La carpeta original de Playwright tiene cronología depurada y archivos de red vacíos. Por indicación de la responsable, la investigación se hizo en local. Es imposible reconstruir el sobre histórico exacto de producción a partir de esas cabeceras y mensajes. Los casos locales anteriores identifican defectos reproducidos con las mismas entradas sintéticas. Se verificó el SHA-256 de los cuatro originales contra `valores_esperados.json`.

## Cambios de contrato y ejecución

- El esquema de Gemini toma métodos del catálogo y productos con ID canónico y ámbito. Por ejemplo, `t_statistic`, `difference_interval` y `mean_interval` son decisiones distintas. Cada componente integral indica su propio método. El servidor convierte el transporte nuevo a Plan v1 y etiquetas en español antes de validar o persistir. Los planes históricos siguen admitiendo sus etiquetas y el transporte de Terra conserva su forma previa.
- El contexto del proveedor incluye los productos verificables por método. La preparación y ejecución vuelven a comprobar método, diseño, variables y opciones, incluida la atribución a componentes. La definición del IC de una comparación queda acotada al estimando implementado. Se conservan los controles sobre Hedges, significación, independencia y multiplicidad.
- Una comprensión de archivos con Gemini utiliza un esquema específico sin propuestas. Los planes simples llevan una lista vacía de componentes. El diagnóstico identifica productos y métodos incompatibles en la corrección semántica existente y conserva el alcance si los intentos se agotan.
- Los filtros de filas tienen referencias y niveles explícitos. Un rol exclusivo de filtro permite seleccionar observaciones sin convertir la columna en un agrupador o predictor del procedimiento. La relectura de la tabla y la validación de la especificación conservan el filtro aceptado. El reconocimiento de igualdades en el mensaje coteja nombres y niveles reales. Es una gramática acotada.
- Para las columnas numéricas de significado ambiguo, la aplicación guarda la decisión explícita del investigador. Cuando el plan enumera productos cuantitativos pide la escala en chat. En un resumen pendiente del tipo lo pregunta durante la preparación. Las frecuencias solicitadas expresamente siguen disponibles. El instrumento aporta evidencia metodológica únicamente con consentimiento.
- La identidad y los datos de la captura solo se usaron en el entorno de prueba. El código productivo registra categorías e índices. Los datos de la captura completa, el contexto, el alcance, la corrección efectiva y los resultados de validación están en el expediente local depurado `Statia-Diagnostico-Gemini-20261127`. Las muestras para reproducción sin red están en `backend/tests/fixtures/gemini_planning_v7`. Los nombres 01, 02, 08 y 09 corresponden a intentos previos a la corrección. Los nombres con prefijo v8 proceden de validaciones posteriores. El plan `accepted-07.json` proviene del ZIP original, con identificadores reemplazados.

## Archivos

| Área | Archivos afectados |
| --- | --- |
| Contrato del proveedor y conversación | `gemini_schema.py`, `gemini.py`, `reply_contract.py`, `openai_provider.py`, `conversation.py`, `execution_preparation.py`, `planning_errors.py` |
| Plan y capacidades | `models/chat.py`, `requested_scope.py`, `methodology.py`, `plan_capabilities.py`, `descriptive_feasibility.py`, `statistics/catalog.py`, `statistics/automatic.py`, `statistics/preparation.py` |
| Presentación | `frontend/src/components/ProposalCard.tsx` utiliza el nombre español del método registrado. |
| Validación | `test_real_planning_contract.py`, sus fixtures, `test_app.py`, `test_automatic_preparation.py`, `test_execution_uncertainty.py`, `test_plan_capabilities.py`, `test_planning.py`, `test_openai_provider.py`, `test_terra_diagnostic.py` y `scripts/diagnose_terra.py` |


## Validación y presupuesto

Las 17 comprobaciones nuevas fallaron antes de editar la aplicación. Incluían el plan exportado con la decisión nominal, la categoría de Welch, el filtro ausente, el reconocimiento de la solicitud manual y el contrato de productos de los 13 métodos. Después se añadieron los casos de reproducción con sobres reales y las pruebas de filtros ambiguos.

Se realizaron **49 solicitudes reales a Gemini de un máximo autorizado de 54**. Las primeras 11 corresponden a la investigación en la base, 23 a la integración local de FastAPI y motor con repositorio de pruebas y 15 al recorrido final de Chromium con todas las dependencias reales. La corrección semántica y los intentos fallidos están incluidos. Terra recibió cero solicitudes reales.

Para los cinco E2E finales, Chromium usó React, FastAPI, Gemini, Auth, PostgreSQL, REST y Storage reales. Supabase se inició en Docker con una instancia local aislada y las nueve migraciones existentes. Los scripts se ejecutaron desde una copia privada del expediente original. Los resultados se recuperaron desde la interfaz y se volvieron a comprobar leyendo el JSON de cada ZIP.

| Recorrido | Resultado verificado |
| --- | --- |
| E2E-04 | Tarjeta, aceptación, cálculo y ZIP. 20 válidos, media y mediana 19,5, DE muestral 5,9160797831. |
| E2E-05 | A y B tuvieron 8 y 10 observaciones, medias 16 y 31,5. Diferencia A − B −15,5. La ejecución dio t = −2,9866219081519176, gl = 10,362546464549377 y p bilateral = 0,013153584070293227. Los tres valores coincidieron con una nueva llamada a SciPy sobre el CSV con tolerancia relativa de 1e−12. La primera pasada del navegador se detuvo en la aclaración de independencia porque el selector no reconocía el botón. Tras corregirlo en la copia del script, se reabrió la misma propuesta aceptada y se terminó la ejecución y la descarga. |
| E2E-06 | Contexto confirmado y recargado. La propuesta se aceptó y se ejecutó un resumen cuantitativo de 12 observaciones, media 57,3333333333, mediana 56,5 y DE muestral 10,8488234245. |
| E2E-07 | La consulta sin consentimiento ocultó el identificador. Tras autorizar los fragmentos, Gemini citó el identificador sintético. Se ejecutó el descriptivo cuantitativo de puntaje_total y el ZIP contenía los mismos 12 válidos, la media, mediana y DE esperadas. |
| E2E-08 | Se rechazó la propuesta inicial. La nueva tarjeta conservó el filtro grupo = A. Se aceptó, preparó y ejecutó sobre ocho filas. La media y mediana fueron 16 y la DE muestral 3,9279220242. |

La persistencia, aceptación, preparación, ejecución y descarga se verificaron con CSV en estos recorridos reales. Las suites locales cubren adicionalmente XLSX, JSON, conversaciones históricas y planes integrales. Los 13 métodos se revisaron mediante contrato y pruebas del motor. El ensayo real con Gemini se limitó a los casos acordados.

La revisión final también detectó que las decisiones añadidas al contexto podían empujar un libro ancho por encima de su presupuesto tras la primera reducción. La compactación final reutiliza las mismas reglas para los detalles opcionales y conserva las columnas de la hoja activa. Este ajuste y la detección conservadora de filtros ambiguos se verificaron con las suites locales tras el recorrido de Chromium.

## Cierre

La suite completa de backend sobre el código final aprobó 766 pruebas en una ejecución serial. Una prueba se omitió por ausencia de la evidencia histórica privada A/D de Terra. Starlette emitió un aviso de deprecación de TestClient. Frontend aprobó 134 pruebas y dos verificaciones de configuración de despliegue. También pasaron TypeScript, lint, formato, compilación, la comprobación de calidad Python y dependencias. Vite sigue advirtiendo sobre un chunk de aproximadamente 501 kB. Las seis pruebas de base de datos aprobaron con PGlite y el recorrido de navegador ejercitó las nueve migraciones en Supabase local.

Distribución de las 49 solicitudes reales: 11 en diagnóstico, 23 en integración de API con persistencia controlada y 15 en los cinco E2E de Chromium con Supabase real. Las pruebas automatizadas offline utilizaron fixtures. Terra tuvo cero solicitudes reales. El árbol se preparó en dos commits locales para abrir PR a develop. La verificación del despliegue corresponde a la actualización posterior por la responsable del proyecto.
