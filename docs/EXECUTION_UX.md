# Corrección UX de ejecución — Sesión 03

## Causa y recorrido actual

El recorrido anterior exponía ExecutionSpec v1 como un formulario obligatorio: el navegador comenzaba con métodos, tipos y decisiones vacíos, aunque parte del alcance ya estaba en el plan aceptado. No había un preparador del servidor que distinguiera decisiones derivables de información metodológica desconocida.

Ahora aceptar sigue guardando el plan sin calcular. **Ejecutar análisis** prepara sobre originales privados; muestra una pregunta imprescindible o **Análisis preparado** con objetivo, método, archivos/hojas, filtros, grupos, confianza y límites. Una segunda acción explícita confirma la ejecución. **Ver detalles** permite auditar la procedencia. **Opciones avanzadas** abre el formulario conservado, precargado cuando existe una preparación READY; abrirlo no cambia ni confirma decisiones.

## Decisiones y límites

| Statia puede preparar | Requiere información humana cuando no está documentada |
| --- | --- |
| Referencias, roles y filtros del plan; hojas/columnas releídas | Independencia, relaciones entre unidades y emparejamiento |
| Grupos presentes y método compatible con catálogo/roles/datos | Significado de códigos y escala de una variable ambigua |
| 95 %, bilateral y casos disponibles por procedimiento | Ausencias frente a categorías legítimas en marcadores ambiguos |
| Welch para comparaciones genéricas de medidas según 2 o 3–20 grupos | Justificación de igualdad de varianzas si se aceptó un método clásico |
| Chi-cuadrado/Fisher para asociaciones genéricas según estructura/esperadas | Relación lineal o por rangos cuando el plan de correlación no define un método |
| Frecuencias prudentes para códigos de escala desconocida en descriptivos | Orden ordinal, unidades e hipótesis que el archivo no documenta |
| Ausencias nulas/vacías y marcadores no numéricos con evidencia cuantitativa consistente | Cambios sustanciales del objetivo/método, que requieren revisar la propuesta |

El resultado separa evidencia `verified`, inferencias `inferred` y respuestas `user`. El diseño propuesto por Gemini no se convierte en evidencia de independencia. La aceptación general tampoco la acredita. Una evidencia metodológica explícita del historial se reutiliza; una sola respuesta de diseño se comparte entre componentes que utilizan la misma tabla y diseño. No se elige por valores p ni se usa Shapiro como criterio absoluto.

Se conserva la multiplicidad fijada en el plan. Si no está definida y hay una familia múltiple, se propone Holm y se explica como decisión automática revisable; los intervalos permanecen individuales. No se activan comparaciones post-hoc por significación. No se inventan unidades, escalas ordinales, hipótesis, relaciones ni supuestos.

El usuario puede contestar con opciones sencillas, **No lo sé**, o expresiones inequívocas en el compositor, como «son datos faltantes». Una respuesta desconocida conserva el bloqueo y explica por qué importa. **Volver al chat** conserva el plan y permite pedir una propuesta descriptiva en la misma conversación. Esta alternativa se propone y acepta por separado: no se cambia silenciosamente un plan inferencial. Preparar/ejecutar un plan suficientemente definido no requiere Gemini; generar otra propuesta o interpretar texto complejo sigue sujeto a su configuración/disponibilidad. El texto complejo no se convierte silenciosamente en una confirmación.

## Contratos, persistencia y seguridad

- Plan v1, ExecutionSpec v1 y resultados existentes se conservan. La preparación es un contrato nuevo `ExecutionPreparation` v1 con READY / NEEDS_CLARIFICATION / UNSUPPORTED, borrador, evidencia, preguntas, impedimentos, archivos/hashes, huella y UUID estable.
- `decisions_confirmed` permanece falso al preparar. La acción final del usuario confirma la especificación. `validate_spec` permite revisar un borrador sin alterar ese valor y sigue exigiendo confirmación al ejecutar.
- Turn añade tres acciones y los campos opcionales `proposal_id`, `question_id` y `answer`. ExecuteRequest añade `preparation_fingerprint` opcional; los clientes anteriores pueden seguir enviando su especificación confirmada.
- Los RPC existentes guardan preguntas, respuestas y evaluaciones en `stage_data.execution_preparation`, `messages.metadata` y `chat_requests`. Se conservan etapa, finalidad y propuesta aceptada. No hay migración nueva ni reescritura de planes/resultados previos.
- Cada pregunta está ligada por hash al plan y a los originales. Cambiar archivos/hojas/columnas o decisiones obliga a revalidar; las respuestas antiguas dejan de aplicarse al cambiar el alcance. El UUID automático deriva de propuesta/huella: repetir la misma preparación reutiliza el intento y el resultado, sin duplicar cálculos/eventos.
- El servidor verifica estado aceptado, pertenencia, UUID, huella y especificación; el hijo vuelve a evaluar los originales antes de calcular. El modo avanzado conserva controles comunes y no puede reemplazar silenciosamente un método explícito por otro.
- Se reutilizan JWT del usuario, clave publicable, RLS, Storage privado, bloqueo de conversación, semáforo, límites de bytes/celdas/tiempo/RSS, hashes, exportación y reconciliación existentes. No se introduce service_role, otro motor ni código generado por Gemini.

## Archivos modificados

Backend: `app/models/analysis.py`, `app/models/chat.py`, `app/api/chat.py`, `app/services/analysis.py`, `app/services/conversation.py`, el nuevo `app/services/execution_preparation.py`; en `app/services/statistics/`, nuevos `automatic.py` y `methods.py`, y ajustes de `preparation.py`, `engine.py`, `worker.py`. Pruebas: nuevo `tests/test_automatic_preparation.py` y cobertura de calidad en `scripts/check_analysis_quality.py`.

Frontend: nuevo `src/components/ExecutionPreparationCard.tsx`; ajustes de `ExecutionReview.tsx`, `ProposalCard.tsx`, `StatisticalChat.tsx`, `src/types/analysis.ts`, `src/types/chat.ts`, `src/index.css` y regresiones en `src/test/analysis.test.tsx` / `src/test/chat.test.tsx`.

Persistencia: solo regresiones adicionales en `supabase/tests/analysis.test.mjs`; no se modifican migraciones. Documentación: README, ARCHITECTURE, STATISTICAL_ENGINE, SETUP, VALIDATION y este informe. Los archivos temporales de QA no se publican.

## Validación y pasos manuales

La evidencia automatizada y de servicios está en [VALIDATION](VALIDATION.md). Se probaron los originales de Penguins/Titanic y nombres arbitrarios, todos los métodos existentes, ambigüedad, independencia desconocida, retención de categorías, filtros, efectos, cambios de originales, planes antiguos, reintentos, preparación repetida y modo avanzado.

En navegador local se usaron componentes y rutas FastAPI reales con datos sintéticos, repositorio/Auth en memoria y Gemini deshabilitado. Se verificaron 1440×900, 1366×768 y 390×844: sin desbordamiento horizontal y con compositor dentro del viewport (bordes inferiores aproximados 881,2 / 749,2 / 835,2 px). Se resolvió «No lo sé» sin inferir la respuesta, se aclaró una ausencia y el diseño, se ejecutó desde el resumen sin abrir el formulario, se consultaron resultados y después se revisaron opciones avanzadas e historial móvil. No acredita Supabase remoto, teléfono físico ni teclado virtual.

Para validar con servicios reales:

1. Comprobar migraciones 001–004 en el proyecto correcto y reiniciar API/Vite. Esta corrección no agrega SQL de instalación; no repetir migraciones aplicadas.
2. Con una sesión de cuenta A, aceptar una propuesta, preparar, responder, recargar y comprobar persistencia en el mismo chat. Confirmar desde el resumen; abrir Resultados y descargar ZIP/recursos.
3. Penguins: conservar filtro Adelie y orden female−male, aclarar NA de sexo y diseño. Debe usar 152 filas filtradas y 146 completas (73/73), diferencia ≈ −674,657534 g. Los originales no cambian.
4. Titanic: fare por pclass categórica; Welch ANOVA con tres grupos de 216/184/491. Una t simultánea para esos tres grupos debe rechazarse.
5. Probar marcadores legítimos, «No lo sé», método incompatible, fallo y reintento, doble clic y preparación idéntica desde otra pestaña/dispositivo. Un original modificado obliga a preparar de nuevo.
6. Revisar opciones avanzadas, cambios permitidos y bloqueo de cambios sustanciales de método. Comprobar el chat con Gemini deshabilitado: preparación suficiente y cálculo siguen funcionando; una nueva propuesta debe informar la falta del proveedor.
7. Con cuenta B, comprobar aislamiento REST/Storage de conversaciones, aclaraciones, ejecuciones y artefactos de A. Validar también dos proyectos de una misma cuenta.

Los planes antiguos con prosa ambigua, integrales sin componentes o información metodológica insuficiente requieren aclaración o una propuesta revisada. No hay intérprete universal de prosa ni garantía automática del diseño. Se conservan los límites de recursos, métodos, efectos/IC y ausencia de colas durables descritos en STATISTICAL_ENGINE.
