# Conversación sobre resultados y revisión de pendientes

## Causas confirmadas

`process_turn` enviaba todos los mensajes de preparaciones NEEDS_CLARIFICATION, BLOCKED_UNCERTAINTY o PARTIALLY_READY a `preparation_turn`. Un texto ajeno a las opciones se trataba como respuesta metodológica inválida; con preguntas vacías podía repetir el resumen de preparación. Además, `saved_results_context` excluía deliberadamente frecuencias y limitaba tablas numéricas: faltaban agregados categóricos ya calculados. En el frontend, «Revisar componentes pendientes» invocaba `prepare_execution` mediante `onContinue`.

## Enrutamiento y conservación

Las acciones estructuradas conservan prioridad. `preparation_message_route` reconoce respuestas de la pregunta activa; «No lo sé» repetido puede conservar una incertidumbre ya registrada. El resto de las consultas sigue al asistente conversacional. Las respuestas breves ambiguas reciben una pregunta de intención, sin resolver supuestos. Preguntar qué significa independencia ya no equivale a declarar independencia desconocida; delegar la elección del análisis tampoco contesta una pregunta metodológica.

La aplicación reutiliza Gemini para comprender las preguntas libres; no introduce un clasificador basado exclusivamente en palabras clave para toda la conversación. Las pistas de interpretación/revisión y el detector existente de solicitudes estadísticas protegen la finalidad. En modo de consulta se rechazan propuestas o cambios de finalidad, se conserva etapa/título/objetivo y no se modifica la preparación. El mismo enrutamiento determina cuándo hace falta el bloqueo del motor: consultar resultados no solicita Python ni ese bloqueo.

## Contexto de resultados guardados

Se reutiliza `saved_results_context`, siempre filtrado por proyecto y conversación autenticados. Incluye hasta tres ejecuciones completas, parciales o fallidas, estados por componente, motivos, supuestos, estadísticas, agrupación calculada y tablas agregadas. Una ejecución fallida sin resultado aporta su error, sin cifras. Se puede identificar una ejecución por UUID o solicitar el primer resultado; esto no amplía el acceso entre proyectos.

Se incluyen frecuencias y porcentajes efectivamente calculados, además de medias, medianas y dispersión. Los nombres sensibles, identificadores reconocibles y agrupaciones identificadoras se excluyen o reducen; no se envían observaciones originales. En consultas de resultados, el inventario de archivos se reduce a referencias y tipos, sin muestras ni estadísticas de perfil que pudieran confundirse con el análisis ejecutado.

Los límites son explícitos: hasta ocho componentes, seis tablas por componente, doce filas cuantitativas o veinte de frecuencias por tabla, veinte categorías y 16 000 caracteres de contexto agregado. Se indican omisiones; el contexto completo también respeta `gemini_context_chars`. Si no está disponible una tabla conjunta por grupo, no se permite deducirla de frecuencias marginales ni inventar un cálculo. Los hashes y las referencias de continuidad mantienen la procedencia entre ejecuciones.

Se conserva la validación inferencial y se amplía a formas explícitas de cifras descriptivas y porcentajes, con redondeo y notación científica. Se rechazan afirmaciones de significación/causalidad sobre un contexto exclusivamente descriptivo. Estas comprobaciones y las instrucciones del proveedor no constituyen una verificación semántica universal de toda frase natural; si faltan agregados, el asistente debe reconocerlo y consultar los recursos guardados antes de proponer recalcular.

## Revisión de componentes

`AnalysisResultCard` abre/cierra `PendingComponentsReview` con estado local. Reutiliza `ComponentStates`, el resultado ya cargado y las aclaraciones de la preparación actual/archivada. Muestra métodos, variables, bloqueos y respuestas registradas. Abrir detalles no envía turnos, no llama a Gemini, no ejecuta Python ni duplica resultados. Los registros históricos sin estados completos muestran una advertencia compatible, sin inventar la causa del bloqueo.

Seleccionar otra respuesta solo modifica un borrador local. **Guardar respuesta y preparar pendientes** envía la aclaración estructurada; **Volver a preparar componentes pendientes** inicia la preparación explícita. El backend revalida datos/decisiones y conserva componentes completados compatibles. Calcular los pendientes sigue necesitando confirmación posterior. Una aclaración histórica que no está en la preparación vigente requiere volver a preparar, en lugar de enviar una respuesta obsoleta.

El encabezado usa `latest_analysis_run`, un resumen de solo lectura, para distinguir parcial, completado, calculando o fallo. Sin ejecuciones mantiene los estados de preparación/plan existentes. No se modifican mensajes históricos, cronología, scroll ni compositor. No hay migración SQL nueva ni cambios de fórmulas, motor, originales, Auth, RLS, recursos o ZIP.

## Validación y límites externos

Regresiones con datos genéricos: consultas consecutivas tras un parcial y durante una revisión con aclaración activa, frecuencia/mediana/dispersión, incertidumbre, respuestas explícitas, rechazo de números inventados, privacidad, fallos y selección de resultados antiguos. Las pruebas HTTP usan rutas y cálculo reales con Auth/REST/Storage y proveedor controlados. Las pruebas UI verifican que revisar no envía `prepare_execution`, que editar requiere guardar explícitamente y que el encabezado parcial persiste al remontar.

Integración HTTP adicional con **Gemini real** y datos sintéticos agregados: explicó medias/frecuencias por grupo, desviación estándar y el bloqueo de Pearson en tres consultas consecutivas. Finalidad y preparación quedaron idénticas; se conservó una ejecución y no aumentaron las descargas de originales. El primer intento recibió HTTP 503 del proveedor y conservó igualmente el estado. Auth/REST/Storage fueron dobles locales: no acredita Supabase remoto autenticado.

La herramienta de navegador no estuvo disponible: la conexión falló tanto al abrir como al reiniciar. No se atribuye una prueba visual nueva ni se reutilizan capturas anteriores como evidencia de esta corrección. Queda repetir en navegador autenticado con el chat real: preguntar por el parcial, abrir/cerrar pendientes sin mensajes nuevos, guardar una respuesta explícitamente, revalidar y confirmar la ejecución posterior. Los archivos y servidores temporales de QA se retiraron.

Archivos principales: `backend/app/services/conversation.py`, `execution_preparation.py`, `analysis_context.py`, `gemini.py`, `backend/app/api/chat.py`; `AnalysisResultCard.tsx`, `PendingComponentsReview.tsx`, `StatisticalChat.tsx`, tipos, estilos y regresiones. Los comandos y resultados finales se registran en `VALIDATION.md`.
