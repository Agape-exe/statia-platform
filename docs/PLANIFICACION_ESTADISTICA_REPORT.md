# Estabilización de la planificación estadística

## Base y versión desplegada

La rama `fix/estabilidad-planificacion-estadistica` parte de `origin/develop` en `189bca538e4f833a8df9657eeeb75f5bce5eca97`, obtenido con `git fetch origin develop`. La rama `develop` local estaba 34 commits por detrás, por lo que se usó la referencia remota recién actualizada. Al iniciar, el árbol estaba limpio en `fix/estabilizacion-instrumentos-ux-sesion9`, con el commit local `3ca6c80` por delante de su rama remota. Ese commit sigue en su rama original.

GitHub registra un despliegue de Vercel completado para `189bca5` y las tres comprobaciones de CI aprobadas para esa revisión. Quedan por confirmar el alias de Vercel consultado durante E2E-05 y el SHA activo del backend de Render. [Commit base](https://github.com/Agape-exe/statia-platform/commit/189bca538e4f833a8df9657eeeb75f5bce5eca97) · [Despliegue de Vercel](https://vercel.com/melissa-workspace/statia-platform/BCguxHC6LEFZtRqrCaXv9dhfRiwP)

## Reproducción en la base

Las primeras tres pruebas de regresión se ejecutaron contra `189bca5` antes de editar la aplicación. Las tres fallaron en la API HTTP local con un dataset sintético y un proveedor controlado.

| Caso | Evidencia en la base | Causa confirmada |
| --- | --- | --- |
| Welch bloqueado | HTTP 200, etapa Aclaraciones, cero consultas al proveedor y «Siguen pendientes los productos solicitados: Media». | `process_turn` retornaba `scope_question` antes de generar. `product_request` leía «compare la media» como el producto descriptivo `mean` y «casos completos» activaba `unresolved`. La confirmación posterior volvía a activar esa ambigüedad. |
| Propuesta inexistente | HTTP 200 y texto «He estructurado formalmente la propuesta solicitada» guardado sin filas de propuesta. | La pregunta entraba como consulta metodológica. El contrato permitía una consulta sin objetos y el filtro textual no detectaba el anuncio ni la referencia a la tarjeta. Se guardaba la prosa y se conservaba la etapa. El componente de React muestra tarjetas a partir de las filas asociadas al mensaje, así que no tenía una tarjeta que renderizar. |
| Variables del plan y componentes | Dos generaciones controladas, HTTP 502, `X-Statia-Error: planning_validation` y `X-Statia-Validation: component_variables,output_capability`. | Un único componente duplicaba las variables de resultado y agrupación del plan en orden inverso. La normalización exigía igualdad posicional y `validate_methodology` rechazaba los componentes de un plan simple. La segunda validación de alcance, sobre el mismo plan inválido, añadía un fallo de cobertura. El mensaje observado en smoke admite otras causas de `component_variables`. Sin el sobre de ese turno, el mismo origen concreto en producción queda sin confirmar. |

## Cambios

| Archivos | Cambio y motivo |
| --- | --- |
| `requested_scope.py`, `statistics/methods.py` | Distinguen el objetivo de comparar medias, los productos exigidos y las decisiones de ausencias. El alcance conserva los métodos elegidos y excluidos por el usuario, los comprueba contra la familia de cada componente y distingue los promedios globales de los agrupados. Los alcances antiguos solo se reconstruyen automáticamente cuando el historial disponible contiene toda la evidencia de usuario necesaria. |
| `plan_capabilities.py`, `statistics/catalog.py` | Acreditan las medias en descriptivos agrupados cuando la cobertura de variables y grupos es verificable. El catálogo declara los grados de libertad que las dos pruebas t independientes ya calculan. |
| `conversation_text.py`, `conversation.py` | Una petición de explicar la aclaración activa recupera la pregunta guardada y conserva la etapa. Las consultas metodológicas generales siguen pasando por el proveedor y conservan la planificación pendiente. El servidor deriva el anuncio de las propuestas explícitas de los objetos validados que el turno va a guardar. |
| `reply_contract.py`, `interpretation_guards.py`, `gemini.py` | El contrato común de Gemini y Terra conserva indicios estructurados de una propuesta ausente y verifica las afirmaciones de disponibilidad o instrucciones sobre tarjetas en la prosa. Los incumplimientos usan la corrección semántica acotada. Si persisten, la API devuelve un error recuperable. Los cambios de finalidad y las propuestas se validan en turnos separados. |
| `reply_contract.py`, `planning_validation.py` | Se elimina un componente redundante si coincide exactamente con el plan o, en una comparación simple, si solo se invierte el orden de las mismas dos referencias con roles inequívocos. Los roles, las referencias, el método, las dependencias y el orden de las categorías siguen sujetos a validación. Los diagnósticos distinguen el sobre, la integridad de los planes y la cobertura del alcance. |
| `test_planning_stability.py`, `test_session6b.py`, `test_frequency_contract.py`, `test_app.py`, `frontend/src/test/chat.test.tsx` | Pruebas HTTP, de ejecución y de interfaz. Cubren la solicitud y la confirmación originales, formulaciones de Welch, conversaciones nuevas e históricas, reformulación, recuperación de propuestas, XLSX y JSON reutilizados, otro contraste, medias globales y agrupadas, exclusiones, datos incompatibles y las cabeceras de error. `/health` expone `X-Statia-Planning-Version: 7`. |

La corrección usa los perfiles de los archivos asociados. Los validadores de referencias, diseño y productos siguen activos. La aceptación guarda el plan y la preparación revisa los originales. La ejecución requiere confirmación explícita y calcula con el motor Python. La suite comprueba el contexto de tesis, el consentimiento documental y las propuestas integrales por sus rutas existentes.

### Diagnóstico de un turno fallido

| Cabecera o categoría | Qué identifica |
| --- | --- |
| `X-Statia-Error: response_validation` con `proposal_missing` | Una consulta trajo un anuncio o una indicación estructurada de propuesta sin tarjeta disponible. |
| `X-Statia-Error: planning_validation` con `component_variables` | El sobre contiene un plan, pero su estructura de componentes es incompatible. `objective_variables` identifica, por separado, una diferencia entre la selección y el objetivo o el método. |
| `X-Statia-Validation: internal_contract` | La respuesta o su plan carece de una forma interna válida. Los errores de transporte, formato del proveedor y cuota conservan sus códigos propios. |

Los registros de planificación incluyen intento, índice y categoría. Las pruebas verifican las cabeceras del fallo con variables incompatibles y la ausencia de tarjeta o mensaje de disponibilidad después del rechazo.

## Validación de Welch con el CSV original

La regresión optativa lee `grupos_welch.csv` desde la ruta asignada a `STATIA_WELCH_CSV`. El archivo privado se conservó byte a byte y queda fuera de Git. El flujo local usa la API FastAPI, el perfilado, la aceptación, la preparación y el motor Python reales. La sesión, el repositorio, Storage y la respuesta del proveedor están controlados por pruebas. La interfaz se comprueba por separado mediante Testing Library.

La prueba recupera la propuesta guardada, la acepta, responde las decisiones metodológicas que solicita preparación, comprueba el bloqueo del cálculo sin confirmación y ejecuta Welch por el endpoint normal. Verifica además que repetir el mismo UUID recupera la misma ejecución.

| Magnitud | Resultado contrastado |
| --- | ---: |
| N en A / B | 8 / 10 |
| Media en A / B | 16 / 31,5 |
| Diferencia A − B | −15,5 |
| Estadístico t | −2,9866219081519167 |
| Grados de libertad | 10,362546464549375 |
| Valor p bilateral | 0,013153584070293232 |

La referencia independiente se obtiene con `scipy.stats.ttest_ind(a, b, equal_var=False, alternative="two-sided")`. La comprobación del resultado de Statia utiliza una tolerancia relativa de `1e-12`.

## Reproducción local

El siguiente comando se ejecuta desde `backend` con el entorno virtual y el archivo privado disponibles.

```powershell
$env:STATIA_WELCH_CSV = 'C:/ruta/privada/grupos_welch.csv'
.\.venv\Scripts\python -m pytest -q tests/test_planning_stability.py
```

Sin la variable se ejecutan las regresiones sintéticas y se omite la prueba optativa del CSV original.

## Backend

La suite completa de pytest en Windows aprobó 727 pruebas, incluidas las 22 regresiones nuevas y la ejecución con el CSV original. Se omitió una prueba que necesita evidencia histórica A/D de Terra ausente del checkout. `check_analysis_quality.py`, Ruff sobre los archivos modificados y `pip check` pasaron. El runner emitió el aviso de deprecación de Starlette sobre `httpx` en `TestClient`.

## Frontend

Vitest aprobó 134 pruebas. Las dos pruebas de configuración de despliegue, TypeScript, lint, formato y compilación pasaron. Vite informó un tamaño de 501 kB para el chunk principal. La prueba añadida comprueba que la aclaración aparece sin botón de aceptación y que ese botón solo aparece cuando el servicio devuelve una propuesta asociada al mensaje.

## Base de datos

Las seis pruebas de Supabase aprobaron con PGlite, incluidas las transacciones de chat y resultados, RLS, aislamiento y reutilización. Esta comprobación se ejecutó localmente. La corrección conserva las migraciones existentes.

## Alcance externo y preparación del PR

La reproducción local no requiere Gemini real ni usa Terra como sustituto de una validación de Gemini. El recorrido real de generación en Vercel, Render y Supabase queda pendiente de una prueba autorizada con el proveedor real. Los controles de prosa cubren señales estructuradas y patrones verificables. Una formulación desconocida sigue sujeta a la cobertura finita del reconocedor y del filtro. Los historiales truncados conservan el alcance previo hasta disponer de suficiente evidencia o un cambio explícito del usuario.

E2E-06, E2E-07 y E2E-08 se beneficiarían si fallaron por un producto descriptivo inferido indebidamente, un anuncio sin objeto o un componente redundante equivalente. Si el proveedor devolvió variables ausentes, roles incompatibles, componentes realmente distintos o un método inaplicable, la propuesta seguirá siendo rechazada. Los escenarios, solicitudes y trazas de esos tres casos no estaban disponibles para reproducirlos por identificador.

La revisión previa a la publicación reprodujo un caso adicional. Si el nombre del método venía entre comillas invertidas, la preparación podía tratarlo como ausente y elegir otro método. Se conservan los métodos y productos escritos de esa forma, y se omiten como términos estadísticos las referencias a columnas identificadas. La regresión cubre también la confirmación de varianzas al preparar una t de Student.

La rama desactiva el despliegue automático de Vercel mediante una regla específica en `frontend/vercel.json`. La regla permite revisar el PR y ejecutar GitHub Actions sin habilitar una vista previa de esta rama.
