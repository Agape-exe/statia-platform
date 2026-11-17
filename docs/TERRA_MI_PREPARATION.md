# Preparación aislada de Terra: M e I

Fecha: 16 de noviembre de 2026. Esta entrega prepara pruebas; no acredita que Terra haya superado M o I. No se hicieron solicitudes reales a OpenAI, Gemini ni Supabase. Las respuestas de las pruebas automatizadas son simuladas.

## 1. Estado del repositorio

- Inicio: `fix/auditoria-gemini-503`, sin modificaciones de archivos versionados. Solo estaba sin seguimiento `backend/test_terra_statia_env.py`.
- Se ejecutó `git fetch origin develop`. `origin/develop` quedó en `8274c1241a30e4aa9777c6f7ad8039a4c430dbe4`, cuyo mensaje es `Merge pull request #5 from Agape-exe/fix/auditoria-gemini-503`. Sus padres son `df4badd9bb76bf9d25fc99c65f0e370f302c86c1` y `88a45572c3e733e040fde08ab62eb5fa9549e16e`.
- Rama de preparación: `codex/preparar-terra-m-i`, creada desde ese `origin/develop`. No se alteró la rama local `develop`.
- Sin commits, staging, PR, despliegues ni cambios en servicios remotos. Los tres archivos de esta preparación quedan locales sin seguimiento, además del script histórico.

## 2. Inspección técnica

Se consultaron `AGENTS.md`, `docs/SETUP.md`, `docs/ARCHITECTURE.md` y:

- `backend/test_terra_statia_env.py`.
- `backend/app/models/chat.py`.
- `backend/app/services/gemini.py`, `gemini_schema.py`, `methodology.py`, `independence.py`, `conversation_text.py`, `analysis_context.py`.
- `backend/app/services/statistics/catalog.py`, `preparation.py`, `methods.py`.
- `backend/scripts/diagnose_gemini.py`, `check_analysis_quality.py`.
- Pruebas de diagnóstico Gemini, planificación, planificación heterogénea y los módulos de prueba relacionados del backend.

`AssistantReply` admite hasta cuatro planes. `Plan` v1 conserva variables, procedimiento, método, requisitos, limitaciones, comparación y componentes. `AnalysisComponent` declara familia, método, variables y dependencias por índice. El catálogo admite descripción, Pearson/Spearman, Student/Welch, ANOVA clásico/Welch, t pareada, Mann–Whitney, Wilcoxon, Kruskal–Wallis, chi-cuadrado y Fisher exacto. Su presencia en el catálogo no confirma que sean apropiados para este dataset o diseño.

Los integrales requieren al menos dos familias distintas, cobertura de variables, referencias válidas y dependencias resolubles. No admiten integrales anidados ni componentes inferenciales arbitrarios. La independencia se verifica con evidencia del diseño; no se deduce de filas o identificadores distintos.

## 3. Script histórico de A y D

Existe y se mantuvo **idéntico byte por byte**, sin importarlo ni ejecutarlo. SHA-256 antes/después:

`95d8581522b1635c2f208fc6303ac808fd1e5279a8de09d6dee94298447a5c26`

Sus llamadas A/D y resultados previos no se repitieron. La prueba local extrae únicamente la función `schema_openai` mediante AST, comprueba su equivalencia y verifica el hash. No ejecuta el resto del módulo ni carga su `.env`.

La nueva entrada segura es **`backend/scripts/diagnose_terra.py`**. El script histórico sigue teniendo su comportamiento anterior de autenticación y llamadas pagadas: conservarlo intacto implica que no debe usarse como entrada M/I.

## 4. Escenario M definitivo

Solicitud: analizar características y recomendar entre dos y cuatro alternativas diferenciadas que cubran descripción, comparación y correlación, incluyendo una integral viable. La cobertura puede repartirse entre propuestas y componentes; se admiten dos opciones si su combinación cubre todas las familias pedidas. La integral es obligatoria en este escenario porque el contexto real identifica las cuatro familias como disponibles.

Dataset en memoria: CSV sintético determinista de 30 registros, dos medidas cuantitativas (`medida_a`, `medida_b`), una categoría de tres niveles (`grupo`: A/B/C) y un identificador (`registro_id`). Las dos medidas contienen variación no constante. No hay participantes ni archivos reales. Se usa `inspect_file`, el mismo mecanismo de perfilado del diagnóstico Gemini, y después `build_context` real con proyecto general, etapa `goal`, historial sintético, catálogo y referencias exactas. No se comparten muestras.

El contexto conserva `recommendations_requested=true`, `canonical_objectives=true`, ninguna evidencia de independencia y ningún resultado guardado. Las recomendaciones inferenciales son tentativas: deben declarar independencia pendiente y revisión de muestreo, repeticiones, pareamiento y conglomerados. Los tres grupos permiten una comparación global condicionada al diseño; no se permite escoger solo dos ni confirmar metodología.

## 5. Escenario I definitivo

Se construye por separado con el mismo dataset sintético y una solicitud explícita de **una única propuesta integral**, con dos o más procedimientos distintos y compatibles. No obliga a combinar las tres familias; por ejemplo, descripción más correlación condicionada a revisión del diseño es suficiente.

La detección real de `build_context` produce `recommendations_requested=false` sin sobrescribir el indicador. `check_recommendations` permanece activado: su regla de múltiples recomendaciones simplemente no aplica a este pedido. Se comprueban componentes, variables raíz, archivos/hojas/columnas, métodos, cobertura, dependencias, ausencia de anidamiento, supuestos pendientes y ausencia de metodología confirmada.

## 6. Contratos, validadores y transporte OpenAI

Cada respuesta completa pasa por `AssistantReply.model_validate_json` y después por `validate_reply(..., validate_plans=True, check_recommendations=True)`. Se conservan las reglas de referencias, objetivos, tipos, metodología, independencia y cobertura de Statia. No se usa recuperación parcial, corrección automática ni relajación de validadores.

Comprobaciones adicionales del diagnóstico: cantidad y familias solicitadas, confirmación pendiente del usuario, correspondencia método/familia del catálogo, compatibilidad del número de grupos, identificación de independencia pendiente en cada plan, referencias de componentes y rechazo de identificadores como medidas. Se amplía la detección de afirmaciones numéricas e independencia a los campos libres de la respuesta y de los planes, además de la prosa principal.

**M e I usan exactamente el esquema convertido de D.** La conversión recursiva elimina `nullable`, representa la nulabilidad con `type=[tipo,"null"]`, requiere todos los campos de cada objeto y aplica `additionalProperties=false`. No exporta el esquema Pydantic ni cambia sus contratos. La API recibe `text.format` con `type=json_schema`, `strict=true`, `reasoning.effort=medium` y `store=false`, sin herramientas.

El transporte Gemini/D ya incluye `components`. Omite `schema_version`, `filters` raíz y `depends_on`; Pydantic conserva sus valores predeterminados internos (`1`, `[]`, `[]`). Por ello el modelo puede generar integrales de componentes independientes entre sí, pero este experimento no evalúa generación de dependencias explícitas. Las dependencias vacías son válidas; las pruebas locales también verifican dependencias explícitas válidas, ciclos e índices inexistentes contra el contrato interno, sin cambiar el transporte.

La estructura coincide con las reglas documentadas de [Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses). La aceptación del esquema por **este modelo** sigue pendiente de una llamada real autorizada. La [referencia Responses](https://developers.openai.com/api/reference/resources/responses/methods/create) define los estados, errores y uso; `max_output_tokens` incluye salida visible y razonamiento, según la [documentación de razonamiento](https://developers.openai.com/api/docs/guides/reasoning?api-mode=responses).

## 7. Cambios locales

Solo se añaden:

- `backend/scripts/diagnose_terra.py`: construcción y validación local M/I, modo seco, llamada individual explícita y métricas.
- `backend/tests/test_terra_diagnostic.py`: pruebas sintéticas de seguridad, contrato, metodología, cobertura, errores y consumo.
- `docs/TERRA_MI_PREPARATION.md`: este informe y comandos reproducibles.

Gemini sigue siendo el proveedor productivo. No se implementa `OpenAIProvider`, no se conecta OpenAI a FastAPI y no se modifican contratos, motor estadístico, Supabase ni frontend.

## 8. Validaciones locales

- Pruebas nuevas: `python -m pytest tests/test_terra_diagnostic.py -q`: **64 aprobadas**, 2,29 s. Cubren simulaciones M/I válidas, M con dos/cuatro propuestas, I con dos/tres familias, referencias inválidas, identificadores, anidamiento, cobertura, catálogo, número de grupos, dependencias válidas/cíclicas/inexistentes, independencia falsa, cifras en prosa/planes/componentes, contratos inválidos y comportamiento de red.
- Suite completa: `python -m pytest tests -q`: **367 aprobadas**, 289,31 s; una advertencia de deprecación de Starlette/FastAPI TestClient sobre `httpx`. No es una llamada real ni un fallo del diagnóstico. La primera ejecución restringida no avanzó y se interrumpió; la ejecución fuera del sandbox terminó correctamente.
- Modo predeterminado ejecutado: dos registros `dry_run`, contexto/esquema local válidos, `requests_attempted=0`, métricas de proveedor y validación de respuestas en `null`. No se declara éxito de Terra en modo seco.
- El transporte simulado comprueba un solo POST, sin redirecciones ni reintentos, tanto en éxito como en 429/503, errores HTTP, timeout, conectividad y respuestas inválidas. El modo seco no construye un cliente HTTP ni lee credenciales OpenAI.
- Sintaxis/AST y compilación Python de los archivos nuevos válidos. El script histórico pasó `py_compile` sin ejecutar A/D; hash íntegro y equivalencia del conversor comprobados por la prueba local.
- Ruff aislado de ambos archivos nuevos: lint y formato aprobados. `scripts/check_analysis_quality.py`: aprobado, 39 archivos con formato correcto. `python -m pip check`: sin dependencias rotas.
- Frontend, sin cambios de código: `npm run typecheck`, `npm run lint` y `npm run build` aprobados. El primer build restringido falló por EPERM/lectura de dependencias nativas; el build fuera del sandbox pasó. Vite dejó una advertencia de chunk superior a 500 kB, sin impedir la compilación.
- Revisión de diff y espacios finales aprobada, incluido el contenido de los archivos nuevos sin seguimiento. Sin coincidencias de patrones de claves OpenAI/Google o JWT en los tres archivos añadidos. Sin cambios versionados ni staged; se comprobó que backend productivo, diagnóstico Gemini, frontend y Supabase coinciden con el commit base.

Estos resultados acreditan el arnés local y las regresiones del repositorio, **no una validación real de M/I con Terra**.

## 9. Límites y riesgos pendientes

- No está confirmado el acceso actual del modelo ni la aceptación remota del esquema M/I. Los éxitos previos A/D son evidencia histórica proporcionada por el usuario.
- Los validadores detectan estructuras, referencias y patrones metodológicos; no prueban exhaustivamente que toda prosa libre carezca de hipótesis inventadas, afirmaciones de diseño o cifras disfrazadas. La revisión humana sigue siendo necesaria y queda marcada en la salida. El diagnóstico no imprime ni persiste respuestas completas.
- Los planes son propuestas tentativas, no especificaciones de ejecución autorizadas. No se confirma independencia ni se ejecutan cálculos de los análisis propuestos. El perfilado sintético sí genera el contexto estadístico habitual de Statia.
- Las dependencias explícitas no se generan en este transporte, como se explica arriba.
- Los topes de tokens son presupuestos iniciales, no una garantía de que el modelo complete el JSON. `incomplete`, incluso con JSON aparentemente válido, se rechaza. También se rechazan negativas, respuestas fallidas, mensajes incompletos y salidas de herramientas. No hay reparación ni segundo intento.
- Un timeout/error de conexión puede haber consumido créditos remotamente. Se informa incertidumbre sin repetir la solicitud; uso ausente queda en `null`, nunca se inventa cero.
- No se validaron tarifas comerciales del modelo. La ejecución exige tarifas configuradas y una referencia/fecha; no reutiliza los valores fijos históricos de A/D. La estimación no representa un límite de gasto facturado.
- El timeout HTTP es de 110 s por operación de lectura/escritura y 10 s de conexión; no constituye un plazo absoluto de pared de 110 s. La latencia total se mide aparte.

## 10. Llamadas y presupuesto

Preparación: **cero solicitudes reales y cero créditos de proveedor**. Ejecución futura: máximo una solicitud para M y una para I, en invocaciones independientes; dos como máximo si se autorizan ambas. Sin `/models`, consultas de autenticación, redirecciones, SDK con reintentos, herramientas ni solicitudes ocultas.

Se empieza con `medium`. Topes: M = 12 000, I = 8 000 tokens de salida totales, incluyendo razonamiento. M reserva más por sus hasta cuatro planes y componentes; I solo devuelve un integral. No se cambia automáticamente el esfuerzo o el tope tras un fallo.

La salida JSONL registra escenario, modelo, límites, latencia, HTTP, categoría segura, estado, validación, cantidad de propuestas y huellas SHA-256 de contexto, esquema, instrucciones y payload. Registra entrada, salida total, razonamiento, salida visible derivada y entrada cacheada cuando se proporcionan. El costo usa salida total una sola vez, nunca suma de nuevo razonamiento. Sin tarifa de caché usa entrada completa como estimación conservadora. Las tarifas utilizadas y la huella de su referencia también quedan registradas. No se imprimen claves, excepciones ni detalles/payloads del proveedor.

## 11. Comandos exactos en PowerShell

Desde la raíz del repositorio, preparación sin red (ambos escenarios):

```powershell
Set-Location 'C:\Users\carlo\OneDrive\Escritorio\TesisAI\statia-platform'
& .\backend\.venv\Scripts\python.exe .\backend\scripts\diagnose_terra.py
```

Preparación individual: añadir `--case M` o `--case I`, sin `--live`.

**Solo después de autorización explícita**, configurar las tarifas vigentes de la cuenta/modelo (USD por millón), con punto decimal y referencia fechada. No son claves:

```powershell
$terraInput = Read-Host 'Tarifa de entrada USD por millón'
$terraOutput = Read-Host 'Tarifa de salida USD por millón (incluye razonamiento)'
$terraPricingSource = Read-Host 'Referencia y fecha de las tarifas configuradas o verificadas'
```

M, exactamente una solicitud:

```powershell
& .\backend\.venv\Scripts\python.exe .\backend\scripts\diagnose_terra.py --case M --live --input-usd-per-m $terraInput --output-usd-per-m $terraOutput --pricing-source $terraPricingSource
```

I, exactamente una solicitud:

```powershell
& .\backend\.venv\Scripts\python.exe .\backend\scripts\diagnose_terra.py --case I --live --input-usd-per-m $terraInput --output-usd-per-m $terraOutput --pricing-source $terraPricingSource
```

`OPENAI_API_KEY` se lee solo con `--live`, primero del entorno y luego de `backend/.env`, sin sobrescribir el entorno ni mostrarla. Falta de clave, tarifas o escenario detiene la ejecución antes de red. Opcionalmente añadir `--cached-input-usd-per-m` con su tarifa verificada para descontar caché; los comandos anteriores estiman sin descuento. No ejecutar el script histórico A/D ni repetir un comando tras un error sin nueva autorización.

Repetir pruebas locales (sin llamadas a proveedores):

```powershell
Set-Location .\backend
& .\.venv\Scripts\python.exe -m pytest tests/test_terra_diagnostic.py -q
& .\.venv\Scripts\python.exe -m pytest tests -q
& .\.venv\Scripts\python.exe scripts/check_analysis_quality.py
```

## 12. Recomendación

Los escenarios están preparados para pruebas reales individuales una vez que el usuario las autorice y configure tarifas vigentes. No se declara que Terra haya aprobado M/I por los éxitos simulados. La integración multiproveedor y cualquier ejecución estadística permanecen fuera de esta preparación.
