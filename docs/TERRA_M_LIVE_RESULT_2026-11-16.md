# Terra — Resultado real del escenario M

Fecha: 16 de noviembre de 2026. Rama verificada: `test/preparar-terra-mi`.

**Resultado del diagnóstico: FAILED, categoría `independence`, código de salida 1.** Se realizó exactamente una solicitud autorizada a `gpt-6.1-terra`, con razonamiento `medium`, sin reintentos. A, D e I no se ejecutaron.

## Métricas de la única generación

| Medida | Resultado |
| --- | --- |
| HTTP | 200 |
| Estado del proveedor | completed |
| Duración medida por el diagnóstico | 36,011 s |
| Tokens de entrada | 6 019 |
| Tokens de salida totales | 3 003 |
| Tokens de razonamiento, incluidos en la salida | 267 |
| Tokens de salida visible derivados | 2 736 |
| Tokens de entrada cacheada | 0 |
| Límite de salida configurado | 12 000, incluyendo razonamiento |
| Propuestas generadas | 4 |
| Costo estimado | US$0,021034 |

Tarifas confirmadas por el usuario: entrada US$1,00/millón; caché US$0,05/millón; salida US$5,00/millón. Cálculo: `(6019 × 1 + 0 × 0,05 + 3003 × 5) / 1 000 000`. El razonamiento no se suma de nuevo.

## Validaciones y causa del fallo

- Pydantic / `AssistantReply`: **aprobado**.
- Validación completa nativa `validate_reply`, incluidos planes y cobertura: **aprobada**.
- Validación metodológica de cada uno de los cuatro planes por `validate_plan`: **aprobada**.
- Cobertura por `validate_recommendations`: **aprobada**; descripción, comparación global, correlación e integral.
- Comprobaciones adicionales del escenario M: **fallo `independence` en el primer plan**. El flujo se detuvo antes de completar todas sus comprobaciones adicionales.

La condición que falla es `validate_independence("\n".join(plan.requirements), case.context)`, aplicada por el diagnóstico a todos los planes con `require_pending=True`. Los requisitos del descriptivo piden revisar significado, unidades, categorías, ausencias y atípicos, pero no incluyen independencia pendiente. Sus limitaciones sí dicen: «La independencia desconocida no impide obtener resúmenes descriptivos». La respuesta general y las advertencias también declaran explícitamente la independencia pendiente.

La comprobación adicional exige un supuesto de inferencia incluso al descriptivo sin intervalos inferenciales. Esto señala una restricción demasiado amplia del arnés para esa alternativa; no hubo rechazo de los validadores metodológicos nativos ni afirmación de independencia confirmada. Se conserva **FAILED**: no se corrigieron respuestas, no se cambiaron reglas y no se repitió la solicitud. La aceptación HTTP y contractual no se presenta como aprobación completa de M.

No hubo error del proveedor ni error de contrato. El fallo pertenece al criterio metodológico adicional del diagnóstico.

## Propuestas recibidas

Todas las referencias apuntan al dataset sintético `terra_sintetico.csv`, hoja `tabla`, ID `00000000-0000-0000-0000-000000000002`. `registro_id` no fue seleccionado como resultado. Los cuatro planes mantienen `methodology_confirmed=false`, `comparison=null` y no declaran uniones.

### 1. Descripción de medidas y grupos

- Procedimiento: `descriptive`.
- Variables: `medida_a` (outcome), `medida_b` (predictor), `grupo` (group).
- Método: estadística descriptiva de posición y dispersión para las dos medidas; frecuencias y porcentajes para `grupo`.
- Justificación: conocer la distribución sin depender de una prueba inferencial.
- Limitaciones: describe datos sintéticos, sin causalidad ni generalización; la independencia desconocida no impide resumir registros.
- Supuestos/revisiones pendientes: significado y unidades, categorías, ausencias y atípicos; conservar originales. La independencia no aparece en sus requisitos, lo que dispara el fallo adicional descrito arriba.

### 2. Comparación global entre grupos

- Procedimiento: `group_comparison`.
- Variables: `medida_a` (outcome), `grupo` (group).
- Método: ANOVA de Welch global para las categorías A, B y C, sin excluir grupos.
- Justificación: comparar medias globalmente admitiendo varianzas desiguales.
- Limitaciones: inferencia tentativa; el contraste global no identifica por sí solo los pares que difieren ni establece causalidad.
- Supuestos/revisiones pendientes: independencia según diseño, muestreo, repeticiones, pareamiento y conglomerados; significado de variables, tamaños disponibles, distribuciones, atípicos y adecuación de la aproximación; tratamiento de ausencias sin alterar originales.

### 3. Relación entre las medidas

- Procedimiento: `correlation`.
- Variables: `medida_a` (outcome), `medida_b` (predictor).
- Método: correlación de Pearson y gráfico de dispersión.
- Justificación: ambas medidas son cuantitativas y Pearson resume asociación lineal.
- Limitaciones: inferencia tentativa hasta revisar diseño; sensibilidad a relaciones no lineales; ausencia de interpretación causal.
- Supuestos/revisiones pendientes: significado y unidades, forma de la relación, atípicos, independencia y supuestos distribucionales para inferir; disponibilidad conjunta de ambas medidas, conservando los datos originales.

### 4. Exploración integral

- Procedimiento: `integral`.
- Variables: `medida_a` (outcome), `medida_b` (predictor), `grupo` (group).
- Método: descripción, ANOVA de Welch global y correlación de Pearson.
- Justificación: combinar una visión descriptiva con comparación global y asociación entre medidas.
- Limitaciones: componentes inferenciales tentativos; descripción sin necesidad de confirmar independencia; ANOVA global no identifica pares por sí solo y correlación sin causalidad.
- Supuestos/revisiones pendientes: significados, unidades, ausencias y atípicos; independencia según diseño; distribuciones por grupo, linealidad, adecuación inferencial, finalidad y estrategia de multiplicidad.

| Componente | Método del catálogo | Variables | Compatibilidad de familia |
| --- | --- | --- | --- |
| descriptive | descriptive | medida_a, medida_b, grupo | Aprobada |
| group_comparison | welch_anova | medida_a, grupo | Aprobada |
| correlation | pearson | medida_a, medida_b | Aprobada |

La validación nativa del integral aprobó las referencias y cobertura de variables, tres procedimientos distintos, ausencia de anidamiento y dependencias. Todos los componentes tienen `depends_on=[]`; el orden local resoluble es `[0,1,2]`. Las tres familias/métodos coinciden con el catálogo. ANOVA de Welch incluye las tres categorías observadas. Estas comprobaciones locales de compatibilidad no ejecutaron cálculos ni hicieron llamadas adicionales.

## Evidencia y estado final

La evidencia estructurada está en [TERRA_M_LIVE_RESULT_2026-11-16.json](TERRA_M_LIVE_RESULT_2026-11-16.json): métricas, propuestas, advertencias y validaciones de la única respuesta sintética. Se omitieron credenciales, encabezados, cuerpo crudo del proveedor y contenido de razonamiento.

El payload coincide con el revisado antes de la autorización: SHA-256 `fddbe4c16ab13504686a07f1c8a89b2e334963ae5b61c3cba25b4388bcf3b7a8`. Los hashes de los dos scripts, las pruebas y el documento de preparación siguen idénticos. Solo se añaden los informes locales JSON y Markdown de resultados. No se modificó código productivo, Gemini, FastAPI, Supabase o el motor. Sin commits, PR, pushes ni despliegues.

**Detenido tras la única generación.** I permanece sin ejecutar. Se recomienda revisar el alcance de la condición adicional del descriptivo antes de decidir la siguiente prueba; esta entrega no implementa esa revisión ni cambia el resultado registrado.
