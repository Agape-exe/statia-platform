# Revisión local del criterio de independencia de M

Fecha: 16 de noviembre de 2026. Rama: `test/preparar-terra-mi`.

**Las cuatro propuestas reales persistidas de M superan los criterios corregidos.** El fallo histórico se conserva intacto. Esta conclusión corresponde a las propuestas y a la prosa guardadas; no constituye una reproducción completa de `AssistantReply`, porque la ejecución original no conservó todos sus campos.

## Causa exacta

El diagnóstico llamaba incondicionalmente a `validate_independence("\n".join(plan.requirements), context)`. El valor predeterminado `require_pending=True` exigía expresiones de advertencia pendiente incluso para una descripción de los registros observados sin inferencia. Además, otra condición obligaba a que `requirements` contuviera literalmente una mención a independencia.

El primer plan real pedía revisar significado, unidades, categorías, ausencias y atípicos. No incluía independencia en `requirements`; sus `limitations` sí explicaban que la independencia desconocida no impide obtener resúmenes descriptivos. La primera condición lanzó `PlanningError(category="independence")` antes de llegar a la segunda y antes de revisar todos los controles adicionales restantes.

La regla era excesivamente restrictiva: confundía un supuesto necesario para inferencia con un requisito para describir los registros observados, y restringía la ubicación de las advertencias a un solo campo. El catálogo de Statia distingue la descripción de registros de los intervalos de confianza de la media, que sí requieren independencia para inferir.

## Corrección limitada al diagnóstico

Se modifican únicamente `backend/scripts/diagnose_terra.py` y `backend/tests/test_terra_diagnostic.py`, además de añadir los informes separados de esta revisión.

- Una propuesta descriptiva o exploratoria sin inferencia no necesita declarar independencia pendiente. Las advertencias pertinentes pueden figurar en requisitos o limitaciones. Continúa prohibido afirmar falsamente independencia confirmada.
- Si una descripción solicita inferencia o intervalos de confianza, sí requiere advertencia explícita de independencia pendiente. Se reconocen exclusiones explícitas como «sin inferencia» o «sin intervalos de confianza».
- Comparación y correlación deben reconocer independencia pendiente en requisitos, limitaciones o método. Una mera revisión de tipos en otra frase no satisface este requisito.
- Los integrales se revisan por componentes. Una advertencia general del plan puede cubrir sus componentes inferenciales; una advertencia restringida al descriptivo, Pearson u otra familia no cubre familias diferentes. La prosa de otra propuesta o una advertencia global de la respuesta no sustituye la restricción de cada plan.
- Una advertencia es una restricción de planificación, nunca evidencia confirmatoria del diseño ni autorización para ejecutar. `methodology_confirmed=false` y las comprobaciones nativas se conservan.

`validate_reply(..., validate_plans=True, check_recommendations=True)` sigue siendo la primera validación completa de la respuesta. Se mantienen sin relajaciones los controles de referencias, objetivos, tipos, catálogo, grupos, componentes, cobertura, dependencias, identificadores, afirmaciones numéricas y falsas confirmaciones.

La revisión usa reglas conservadoras sobre texto libre y nombres de métodos/familias. No es un verificador semántico exhaustivo. Las reglas productivas de `independence.py`, `methodology.py`, Gemini, contratos, catálogo y motor no se modificaron.

## Pruebas locales

- **90 pruebas específicas aprobadas** en 3,73 s: las 64 anteriores y 26 casos adicionales. Incluyen descripción sin inferencia, advertencias en limitaciones, comparación y correlación con independencia pendiente, omisiones esenciales, componentes integrales con advertencias generales o de alcance restringido, falsas confirmaciones, intervalos descriptivos, negaciones y regresión sobre las propuestas reales guardadas.
- **232 pruebas relevantes aprobadas** en 18,36 s: diagnóstico Terra, diagnóstico Gemini, planificación, planificación heterogénea, Gemini y resiliencia. Una advertencia de deprecación de Starlette/FastAPI TestClient sobre `httpx`, sin fallos.
- Ruff aislado de los dos archivos modificados: lint y formato aprobados. `scripts/check_analysis_quality.py`: aprobado, 39 archivos formateados. Sintaxis Python comprobada mediante compilación.
- Frontend: TypeScript, lint y compilación aprobados; permanece la advertencia de Vite por un chunk superior a 500 kB. No se cambió código frontend ni se desplegó el build.
- Cero solicitudes reales a OpenAI o Gemini y cero consumo adicional de créditos. Las pruebas HTTP utilizan transporte simulado. No se ejecutó I contra un proveedor.

## Reevaluación de la evidencia real

Se leyó directamente `TERRA_M_LIVE_RESULT_2026-11-16.json`; no se sustituyeron sus propuestas por fixtures sintéticos. Se comprobó que el contexto, esquema, instrucciones y payload reconstruidos coinciden con las cuatro huellas SHA-256 registradas antes de la generación real.

Cada propuesta se releyó como `Plan`, traduciendo únicamente el nombre del campo de auditoría `pending_assumptions` a `requirements`. Se ejecutaron los validadores nativos por plan, las comprobaciones adicionales corregidas y las comprobaciones de prosa sobre los campos guardados. No se fabricó una respuesta raíz `AssistantReply`.

| Propuesta real | Validación de Plan | Metodología nativa local | Criterios adicionales corregidos |
| --- | --- | --- | --- |
| Descripción de medidas y grupos | Aprobada | Aprobada | Aprobados; descripción sin inferencia |
| Comparación global entre grupos | Aprobada | Aprobada | Aprobados; independencia pendiente |
| Relación entre las medidas | Aprobada | Aprobada | Aprobados; independencia pendiente |
| Exploración integral | Aprobada | Aprobada | Aprobados por componente |

El integral mantiene tres componentes compatibles: descripción, ANOVA de Welch global y Pearson. El descriptivo no requiere independencia para resumir registros; los dos componentes inferenciales están cubiertos por la advertencia pendiente del plan. Se conservan cobertura de variables y familias, referencias exactas y dependencias válidas. La respuesta, preguntas y advertencias persistidas también superan los controles de prosa. No se encontraron otros incumplimientos en el contenido guardado.

La llamada antigua sobre los requisitos del primer plan vuelve a producir exactamente la categoría `independence`. Esto reproduce el fallo inicial sin invocar al proveedor.

## Alcance y datos ausentes

El archivo original conserva las propuestas, respuesta conversacional, preguntas, advertencias, métricas y resultados de validación. No conserva el cuerpo crudo de Responses ni estos campos originales de `AssistantReply`: `suggested_stage`, `detected_goal`, `suggested_title`, `clarification_required`, `involved_file_ids`, `selected_variables`, `confirmation_required`, `goal_change`, `goal_change_reason`, `context_summary`.

Tampoco conserva explícitamente `schema_version`, `joins` o `filters` de cada plan. La vista local aplica sus valores predeterminados del contrato (`1`, `[]`, `[]`), identificados como tales, sin presentarlos como campos observados. `schema_version` y los filtros raíz no forman parte del transporte usado; el informe histórico también documenta la ausencia de uniones. La validación nativa completa de la respuesta original consta como aprobada, pero no puede repetirse íntegramente con los datos disponibles.

Por ello el resultado nuevo es **`passed_for_persisted_evidence`**. No se cambia el `failed` histórico a `success` ni se afirma haber demostrado que todos los campos originales ausentes superarían los controles adicionales que no llegaron a ejecutarse.

## Trazabilidad y estado final

Los dos archivos originales mantienen exactamente estos hashes:

- JSON: `62c6e9021c08cbb796851a5a2d077e6a9ca1422d34feb5e0235b529349130758`.
- Markdown: `8410964e4a8f729af84f78c26cfb1696ecaa5e6ebd34fb7ef89713b3459edfa1`.

El script histórico A/D también permanece intacto. Los resultados separados de esta revisión están en [TERRA_M_INDEPENDENCE_REVIEW_2026-11-16.json](TERRA_M_INDEPENDENCE_REVIEW_2026-11-16.json), con el hash de la fuente y del diagnóstico corregido, comprobaciones por plan, campos ausentes y estado original preservado.

**M supera los criterios corregidos sobre la evidencia persistida**, con la limitación de reproducción completa indicada. Corresponde avanzar a una prueba I independiente solo cuando el usuario la autorice; conviene conservar su `AssistantReply` completo, sin credenciales ni contenido privado, para permitir una reevaluación íntegra posterior.

Sin llamadas nuevas, cambios productivos, commits, PR, pushes ni despliegues. I permanece sin ejecutar contra el proveedor.
