# Auditoría Gemini HTTP 503

Fecha: 16 de noviembre de 2026. Rama base actualizada: `df4badd9bb76bf9d25fc99c65f0e370f302c86c1` (`develop`).

## Hallazgos previos a modificar el proveedor

Comparación real de Git: sesión 3 `783ee8095849979baaf8b105151bf75d2092451f` → [PR #4](https://github.com/Agape-exe/statia-platform/pull/4), head `2e026b454e231692e70e57b52b6b20561758da5b`, merge `df4badd`.

| Elemento | Sesión 3 | Sesión 4 |
| --- | --- | --- |
| `SYSTEM` (caracteres Unicode / bytes UTF-8) | 11 895 / 12 066 | 12 659 / 12 844 |
| Transporte `reply_schema()` | Igual | Igual |
| `GeminiProvider.generate`, parámetros y clasificación de errores | Igual | Igual |
| Modelo predeterminado | `gemini-3.5-flash-lite` | Igual |
| SDK declarado | `google-genai>=1.50,<3` | Igual |
| Configuración Gemini | 35 s predeterminados, máximo 45 s; 45 000 caracteres de contexto | Igual |
| Contexto general | `research_context=null` | Igual; no consulta la tabla de tesis |
| Contexto tesis | `null` | Lectura vigente con JWT/RLS, documento validado/redactado, revisión y fecha |
| Conversación | Hasta dos generaciones semánticas | Igual, añade revisión de tesis a metadata |

La diferencia de `SYSTEM` es +764 caracteres (+6,42 %), compartida por ambos tipos de proyecto. No acredita causalidad con HTTP 503. El resto del contexto general conserva su construcción. `config.py` añade validación CORS, sin cambiar parámetros Gemini. `models/chat.py`, `gemini_schema.py`, `gemini_errors.py` y `requirements.txt` no cambiaron en PR #4.

Se compararon también los objetos generados por `build_context` histórico y actual para los escenarios generales B/C/D/F sintéticos: **idénticos en los cuatro casos**, antes de fijar las cuotas explícitas del diagnóstico. Se extrajo únicamente esa función del código versionado para una comparación local sin red. No equivale a recuperar las solicitudes históricas reales de la cuenta.

El esquema tiene 14 campos raíz, 15 objetos, 85 propiedades obligatorias contando repeticiones y profundidad máxima 8 contando raíz, propiedades y elementos de listas. Ocupa 8 471 caracteres Unicode con `json.dumps(..., ensure_ascii=False)` o 8 581 con el escape ASCII predeterminado. Usa objetos/listas/enums/nullable; sin recursión, `$ref`, `additionalProperties`, defaults ni límites internos. La validación estricta de Pydantic y la metodológica son posteriores e independientes.

Se envía `response_schema=reply_schema()`, MIME JSON, `max_output_tokens=7000`, una candidata implícita, sin temperatura/thinking explícitos y sin herramientas; función automática deshabilitada. `HttpOptions.timeout` está en milisegundos. `HttpRetryOptions(attempts=1)` deshabilita reintentos propios del SDK. Statia repite solo ante 429/500/503, una vez, después de 1 s; no repite timeout, 504, red, JSON inválido ni 400. La corrección semántica solo ocurre después de obtener y validar JSON; un 503 no es un error metodológico ni activa esa corrección.

**Defecto confirmado de resiliencia, anterior a sesión 4:** con 45 s por intento, dos intentos por generación y una corrección, el máximo teórico es `2 × (2 × 45 + 1) = 182 s`, superior al límite de 150 s del turno (concesión SQL: 180 s; navegador: 165 s). No explica un HTTP 503 recibido a los 6–9 s, pero puede cortar una corrección lenta y ocultar el diagnóstico original.

Entorno local inspeccionado sin mostrar secretos: Python 3.12.10, `google-genai` 2.34.0, httpx 0.28.1; modelo configurado igual al solicitado y timeout 45 s. Hay una clave configurada; su validez se verificará solo mediante solicitudes sintéticas acotadas. El rango de dependencias permite diferencias entre instalaciones: no existe evidencia de la versión instalada actualmente en Render ni un inventario histórico reproducible del SDK. No se actualizarán dependencias por conjetura.

El conector Render disponible pertenece a otra cuenta; el usuario confirmó que el despliegue se hizo en una distinta. No se consultaron servicios ni secretos de esa cuenta. Para completar la comparación basta ejecutar en la Shell del servicio correcto `python -c "from importlib.metadata import version; print(version('google-genai'))"` y registrar únicamente la versión.

## Evidencia y límites de la investigación

Las cuatro pruebas aportadas por el usuario se consideran evidencia reportada, no reejecuciones de esta auditoría: A/B exitosos (2,66/3,41 s); propuestas múltiples/una descriptiva con HTTP 503 (9,33/6,43 s). Muestran que la misma clave/modelo puede aceptar JSON y el esquema real. No prueban que contenido, tamaño, esquema o sesión 4 causen indisponibilidad: faltan ejecuciones intercaladas bajo igual carga y payloads históricos completos. No se solicitarán datos privados para reconstruirlos.

Google documenta 503 como sobrecarga/indisponibilidad y aconseja backoff con jitter y tope de intentos. Un rechazo por exceso de estados del esquema está documentado como 400; no debe atribuirse automáticamente a un 503. El modelo admite salida estructurada, 1 048 576 tokens de entrada y 65 536 de salida: 7 000 está dentro del límite. Una aproximación por caracteres no sustituye a `count_tokens` ni descarta fallos internos de generación condicionados por contenido.

Fuentes oficiales consultadas: [errores de GenerateContent](https://aistudio.google.com/docs/api-errors?generate-content=true), [reintentos](https://aistudio.google.com/docs/troubleshooting#retry-strategy), [esquemas y complejidad](https://aistudio.google.com/docs/structured-output#limitations), [modelo](https://aistudio.google.com/docs/models/gemini-3.5-flash-lite). Statia continúa usando `models.generate_content`, sin migración de API. La [página pública de estado](https://aistudio.google.com/status) no expuso información verificable de incidentes mediante lectura textual; no se usa como prueba de una caída global ni de ausencia de incidentes.

## Plan de trabajo acotado

1. Crear un diagnóstico A–F de una solicitud por caso, sin persistencia, corrección ni reintentos ocultos; modo seco predeterminado y ejecución real explícita. Comparar opcionalmente el `SYSTEM` histórico conservando modelo, contexto y esquema.
2. Registrar exclusivamente métricas y categorías permitidas; nunca cuerpos de error, prompts, respuestas ni claves. Separar transporte, contrato, metodología y cantidad de propuestas.
3. Limitar cada generación completa a 65 s (incluye espera y dos intentos como máximo), conservando timeout por intento y contrato; dos generaciones consumen como máximo 130 s y dejan margen dentro de los 150 s. Añadir jitter 1–2 s al único reintento; no aumentar intentos/coste máximo. No repetir timeouts, de resultado remoto incierto.
4. Probar SDK real con transporte simulado, cancelación, límites de tiempo, errores y reintentos idempotentes de conversación; ejecutar la suite y controles existentes. No cambiar cálculos, proveedor, modelo, validaciones, infraestructura ni credenciales.

## Resultados reales de esta auditoría

Se enviaron **13 solicitudes reales** en cuatro invocaciones acotadas, siempre con `gemini-3.5-flash-lite`, SDK 2.34.0, MIME JSON, 7 000 tokens de salida máximos, timeout 45 s, funciones automáticas deshabilitadas y **un solo intento**, sin correcciones ni persistencia. No hubo solicitudes reales en las pruebas automatizadas. Los intentos iniciales dentro del sandbox de Windows se detuvieron antes de crear el bucle asyncio: `socketpair` quedó bloqueado; las llamadas de esta tabla se ejecutaron después fuera de esa restricción. Ese bloqueo local no es un HTTP 503 de Google.

| Serie / caso | SYSTEM | Contexto / esquema (caracteres) | Duración (s) | HTTP proveedor | Contrato / propuestas / resultado |
| --- | --- | --- | --- | --- | --- |
| Inicial A: JSON mínimo | 0 | 81 / 128 | 3,391 | 200 | Válido; 0; éxito |
| Inicial B: completo sin dataset | 12 659 | 2 697 / 8 471 | 2,823 | 200 | Válido y validación metodológica aprobada; 0; éxito |
| Inicial C: dataset sin propuestas | 12 659 | 5 501 / 8 471 | 3,781 | 503 | No hay JSON/tokens disponibles; `gemini_unavailable` |
| Inicial D: una descriptiva | 12 659 | 5 401 / 8 471 | 3,884 | 503 | Igual |
| Inicial E: D sin esquema | 12 659 | 5 401 / 0 | 3,512 | 503 | Igual |
| Inicial F: varias propuestas | 12 659 | 5 827 / 8 471 | 2,756 | 503 | Igual |
| Histórico C | 11 895 | 5 501 / 8 471 | 4,222 | 200 | Pydantic válido; 0; fallo local `planning_recommendation_coverage` |
| Histórico D | 11 895 | 5 401 / 8 471 | 4,540 | 503 | `gemini_unavailable` |
| Histórico E | 11 895 | 5 401 / 0 | 3,454 | 503 | Igual |
| Repetición C, cuota explícita | 12 659 | 5 502 / 8 471 | 3,972 | 503 | Igual |
| Repetición D | 12 659 | 5 401 / 8 471 | 4,498 | 503 | Igual |
| Repetición E | 12 659 | 5 401 / 0 | 2,818 | 503 | Igual |
| Repetición histórica D | 11 895 | 5 401 / 8 471 | 5,210 | 503 | Igual |

Tokens reportados por Google (entrada / salida / total): A **25 / 21 / 46**; B **3 436 / 226 / 3 662**; C histórico **4 324 / 534 / 4 858**. `thoughts_token_count` no estuvo disponible. En 503, tokens y cantidad de propuestas son **desconocidos**, no cero. La estimación orientativa del script `(SYSTEM + contexto + esquema)/4` da aproximadamente 6 633 tokens para D actual y 4 515 para E; no es una medida facturada ni un conteo del modelo. El payload HTTP puede diferir por serialización del SDK (capitalización/orden/escapes); las métricas identifican los argumentos efectivos que Statia entrega al SDK, sin almacenar cuerpos HTTP.

El caso C inicial contenía `recommendations_requested=true`: el detector lexical interpreta «no propongas» como solicitud de recomendaciones. Por eso C histórico, aunque obtuvo HTTP 200 y Pydantic válido, falló localmente por cobertura. El script final fija explícitamente la cuota de cada escenario: solo F pide varias propuestas. Se repitió C con `false` y volvió a dar 503. No se modificó el detector productivo en esta auditoría; ese caso lingüístico es independiente del fallo HTTP y queda documentado. D/E son idénticos en contexto y SYSTEM; solo cambia `response_schema`. En E no se añade un esquema al prompt: si Google responde 200, podría fallar Pydantic por no conocer el contrato. Eso sería distinto de indisponibilidad.

## Conclusión y estado

**Estado: Mitigación implementada, pendiente de validación real de recuperación.** Las llamadas reales siguen fallando al generar propuestas: **no se declara el problema corregido ni la demostración validada**. La causa interna exacta del 503 permanece como **investigación inconclusa**.

Confirmado: el endpoint de Google devuelve HTTP 503, antes de Pydantic y las reglas metodológicas. No es el timeout de Statia, un fallo RLS, un cálculo Python ni una respuesta simulada. La clave/modelo funcionan en A/B. Los 503 se reproducen sin `response_schema`, con una sola propuesta, sin propuestas y con las instrucciones anteriores a sesión 4. Por tanto, ni el esquema, ni múltiples planes, ni el incremento de SYSTEM de PR #4 son condiciones necesarias del fallo observado. Esto **no demuestra** que nunca influyan en la generación ni permite afirmar una caída global de Google.

Pendiente: sobrecarga/capacidad asociada a cuenta/región, incidente de Google o fallo interno condicionado por contenido/perfil/contexto. No disponemos del diagnóstico interno de Google ni de un payload histórico exitoso equivalente, y no se puede concluir causalidad desde una muestra pequeña no aleatorizada. Los errores 400 de esquema y 502 de validación local se distinguen explícitamente de un 503 upstream. Un deploy no elimina esta dependencia externa.

## Cambios definitivos y riesgos

- `backend/app/services/gemini.py`: presupuesto de 65 s por generación completa, además del timeout por intento existente, y jitter uniforme de 1–2 s en el único reintento permitido ante 429/500/503. Se conservan el máximo de cuatro llamadas por turno con corrección, el SDK sin reintentos propios y los diagnósticos HTTP. Como solo existe un reintento, no hay una secuencia exponencial de múltiples esperas: añadir más escalones aumentaría coste/latencia sin evidencia de recuperación.
- `backend/scripts/diagnose_gemini.py`: A–F sintéticos, modo seco predeterminado, selección explícita, máximo dos repeticiones y doce llamadas por invocación; comparación del literal histórico SYSTEM sin ejecutar código histórico. Tokens disponibles, contrato Pydantic, metodología y cantidad de planes se registran por separado. Salida 0: seco/éxito; 1: algún escenario fallido; 2: configuración/argumentos inválidos. Sin credenciales, prompts, respuestas ni tracebacks en salida.
- `backend/tests/test_gemini_resilience.py` y `test_gemini_diagnostic.py`: HTTP 429/500/503/504, SDK oficial con transporte simulado y conteo real de peticiones, jitter, cierre/cancelación, timeout durante entrada del cliente/espera/segundo intento, idempotencia HTTP del chat y diagnóstico sin datos sensibles. Se cierran los clientes síncronos propiedad de las pruebas además de su sesión asíncrona. `test_result_conversation.py` amplía un escenario existente con 503, conservación de resultados/artefactos/preparación y contexto de tesis, reutilizando su cálculo. `check_analysis_quality.py` incorpora las nuevas pruebas a lint/formato de CI.
- `docs/SETUP.md`, `docs/ARCHITECTURE.md` y este informe: comportamiento temporal, diagnóstico reproducible y límites de la evidencia.
- `.github/workflows/ci.yml`: los 27 casos nuevos de SDK/diagnóstico corren en un intérprete separado de los 276 casos de aplicación/motor. Ambos bloques son obligatorios; no se omite ninguna prueba ni se altera la barrera de memoria del motor. Es aislamiento del proceso de pruebas, sin cambios de dependencias o de infraestructura desplegada.

Riesgo explícito: después de un primer intento lento, el segundo dispone de menos tiempo; ahora una generación puede terminar con 504 al agotar 65 s, aunque antes hubiera seguido hasta ~91 s. La corrección completa sigue teniendo otros 65 s y el límite global de 150 s continúa vigente. Los tiempos de consulta previa, validación y persistencia no tienen una reserva garantizada por este presupuesto; la protección exterior del turno sigue siendo necesaria. La cancelación local no acredita cancelación del cómputo/facturación remotos; por eso no se reintenta un timeout automáticamente.

No se modifica el contrato público, SYSTEM, modelo, esquema, dependencias, infraestructura, seguridad, contexto de tesis ni cálculos. Contexto: hay redundancia potencial entre últimos mensajes, `goal_evidence` y `previous_understanding`, y el catálogo de métodos añade texto en todos los turnos. Se conservan: reducirlos sin evidencia podría perder decisiones o perjudicar la interpretación/ejecución. El historial ya se acota a 18 entradas de 6 000 caracteres y se reduce por presupuesto; los opcionales (muestras/distribuciones/extractos) se retiran primero, nunca columnas. Las correcciones agregan respuesta previa dentro del límite configurado. No se ha demostrado un problema de complejidad que justifique cambiar el transporte.

La idempotencia significa un mensaje/plan guardado por UUID y payload, no exactamente una generación facturable: un reintento explícito de un turno fallido llama otra vez a Google. Un replay de un turno completado no llama al proveedor. `begin_chat_turn` guarda el mensaje; `fail_chat_turn` libera sin borrar; `finish_chat_turn` persiste respuesta y propuestas de forma atómica. El frontend conserva el UUID y solo repite automáticamente ante renovación Auth (401), no ante 503. Continúan las concesiones/concurrencia SQL existentes.

## Validación local

- Antes de la mitigación: suite dirigida de Gemini/chat/tesis/planificación/resultados: **137 aprobadas** (156,77 s).
- Nuevas pruebas de diagnóstico y resiliencia: **27 aprobadas** (9,53 s), con proveedor/transporte simulados, sin Google. El control adicional de integridad tras 503 inicialmente se probó en otra ejecución estadística (1 aprobada, 33,50 s); finalmente se integra en un escenario de resultados existente para evitar ese cálculo duplicado. La suite final contiene **303 casos**.
- `python -m pytest -q`: **303 aprobadas** (378,26 s) antes de integrar ese control en el escenario existente. Los checks del [PR #5](https://github.com/Agape-exe/statia-platform/pull/5) acreditan la revisión final en Linux.
- Primer CI Linux: **302 aprobadas y 2 fallidas**, ambas HTTP 413 por la barrera real de memoria combinada en pruebas integrales. No eran fallos Gemini ni JSON. Se retiró el cálculo duplicado de la prueba adicional y se cerraron explícitamente los clientes SDK que pertenecen a las nuevas pruebas; no se alteraron barreras, estadísticas ni infraestructura. No se atribuye una causa única a ese pico sin una medición aislada; se conserva esta evidencia y se vuelve a ejecutar CI.
- Segundo CI Linux: **301 aprobadas y 2 fallidas**, en los mismos escenarios integrales por memoria. El cierre de clientes y la reutilización no resolvieron ese pico. Se separan las pruebas SDK nuevas del proceso que ejecuta la barrera RSS (esta mide padre pytest + hijo Python); todos los casos siguen siendo obligatorios. El resultado definitivo de esa validación se registra en los checks del PR, sin afirmar que ese cambio resuelva un problema productivo ni un 503.
- Supabase local, `npm test`: **4 suites SQL/PGlite aprobadas**, incluyendo RLS, integridad, concesiones e idempotencia; no accede al proyecto remoto.
- Frontend: `npm test` **68 aprobadas**; `npm run typecheck`, `npm run lint`, `npm run format:check`, `npm run build` y `npm run test:deployment` **aprobados** (2 pruebas de configuración). No hubo cambios frontend.
- `python scripts/check_analysis_quality.py`: Ruff/lint/formato **aprobados**, 38 archivos; `python -m ruff check --isolated --select E4,E7,E9,F app/services/gemini.py`: **aprobado**. Se evita reformatear todo el módulo preexistente.
- `python -m pip check`: sin dependencias rotas; `python -m compileall -q app scripts tests`: aprobado. `git diff --check`: aprobado.
- Revisión del diff y escaneo local de archivos modificados/nuevos: sin patrones de claves Google/GitHub, JWT ni claves privadas. No se versionan `.env`, logs de respuestas ni archivos de usuarios. Se conservan los metadatos Git auténticos ya configurados; sin coautores añadidos.

Advertencias preexistentes: deprecación Starlette/TestClient y bundle principal Vite >500 kB. No son fallos de estos controles. No se aplicaron migraciones ni se verificaron Supabase/RLS, Render o Vercel reales en esta auditoría. Los mocks prueban orquestación/contratos, no disponibilidad del proveedor ni integración remota.

## Comprobar en local antes de Render

1. Activar el entorno backend Python 3.12 existente. Conservar la clave en `backend/.env`, sin copiarla a comandos/logs ni cambiar el modelo. Revisar la versión con `python -m pip show google-genai` y compararla con Render antes de atribuir diferencias; no actualizarla por ensayo y error.
2. Desde `backend`, ejecutar `python scripts/diagnose_gemini.py` para inspección seca. Luego `python scripts/diagnose_gemini.py --live --cases A B C D E F`: seis llamadas máximas. Puede redirigirse la salida JSONL a un archivo **local fuera de Git**. Salida 1 es un diagnóstico fallido, no un éxito parcial de la integración. No ejecutar un bucle hasta que responda.
3. Si A/B funcionan pero D/F siguen en 503, conservar las métricas y revisar estado/capacidad/cuotas del proyecto con Google. E permite contrastar el esquema sin cambiar el contrato productivo. Opcionalmente una sola comparación `python scripts/diagnose_gemini.py --live --cases D --system-version session3`. No cambiar proveedor/modelo ni debilitar reglas para la demostración.
4. Ejecutar `python -m pytest -q` y `python scripts/check_analysis_quality.py`. Arrancar Uvicorn y Vite con los comandos de SETUP. En un proyecto **general nuevo**, subir un CSV sintético, pedir primero comprensión y después una descriptiva y varias alternativas. Revisar variables, metodología y límites; aceptar no calcula. Ejecutar solo después de confirmar la preparación y comprobar los resultados Python guardados.
5. Ante fallo, recargar: el mensaje debe seguir una sola vez y no deben aparecer planes nuevos. Pulsar Reintentar con el turno conservado; tras éxito, repetir/recargar no debe duplicar propuestas. Revisar `X-Statia-Error`/`X-Gemini-Status`; un 503 upstream debe seguir distinguiéndose de timeout local y fallo metodológico.
6. Repetir en tesis con Contexto confirmado y comprobar revisión vigente, historial y resultados previos intactos. Consultar un resultado guardado, descargarlo y verificar que una explicación fallida no cambie sus cifras. No enviar datos personales para esta comprobación.
7. Solo después de éxitos reales repetibles en D/F y ambos recorridos locales, revisar el PR y desplegar manualmente su SHA en Render, conservando un worker y las variables existentes. Repetir el recorrido autenticado y registrar SHA, versión de SDK y métricas reales; un build/CI verde no certifica disponibilidad Gemini. No se fusiona ni despliega automáticamente.
