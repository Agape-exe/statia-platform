# Corrección focalizada de los P1 del PR #7

Base auditada: `d04a67980a414bd85e84449ef624a242ea02e099`.
Rama: `feat/integracion-multiproveedor-backend`. Trabajo exclusivamente local.
Este informe complementa, sin sustituir, la evidencia de la primera corrección.

## Diagnóstico y reproducciones

**P1-A.** `validate_products()` retornaba anticipadamente en planes sin descriptivos
y, en una integral mixta, exigía que todos los productos pertenecieran al catálogo
descriptivo. Por eso un plan descriptivo + Pearson + ANOVA de Welch funcionaba sin
las etiquetas inferenciales, pero añadir `Valores p` o `Coeficientes de correlación`
lo convertía en `output_scope`. Además, la preparación validaba cada componente
aislado contra todos los productos de la integral.

**P1-B.** Dos respuestas podían superar validaciones distintas sin conservar el
mismo compromiso. La segunda solo tenía que ser ejecutable; no había un contrato
de productos derivado del usuario. `retain_valid_plans()` podía rescatar planes
sin resolver la finalidad completa y borraba preguntas. `reply_result()` tampoco
revalidaba los compromisos antes de construir el resultado persistible.

Reproducción contra el **app real del SHA auditado**, extraído mediante `git archive`
en una carpeta temporal, sin cambiar de rama ni copiar credenciales:

```powershell
cd backend
.\.venv\Scripts\python scripts/reproduce_pr07_p1.py
```

El script espera que las aserciones del comportamiento corregido fallen en esa
versión histórica. No importa código `app` actual en el proceso histórico.

| Caso | SHA auditado | Corregido |
| --- | --- | --- |
| Integral sin etiquetas inferenciales adicionales | Validación, preparación y cálculo correctos | Conservado |
| Integral con p; con coeficientes; con ambos | Tres fallos `output_scope` | Los tres casos validan, preparan y calculan productos reales |
| Tres productos expresos → segundo intento con uno | Persiste la propuesta reducida, con Gemini y Terra simulados | Aclaración, sin nueva propuesta aceptable |
| Corrección con tres componentes descriptivos y los tres productos | Válida | Conservada, sin recortar `expected_outputs` |
| Producto obligatorio sustituido por una salida genérica o dividido entre alternativas | Podía perderse el compromiso | Bloqueado; una única finalidad exige los productos juntos |
| Producto desconocido sustituido por uno más limitado | No había barrera de alcance | Se solicita decisión; no se asume que lo sugerido por el modelo fuera obligatorio |

## Cobertura de productos

`statistics/catalog.py` registra `output_products` junto a cada método del catálogo
existente. Es un campo aditivo del catálogo de procedimientos, no de Plan v1 ni
del contrato de transporte de los proveedores. No se añadió otro catálogo paralelo
de métodos ni se cambiaron funciones, fórmulas o resultados numéricos.

- Los productos descriptivos conservan la cobertura por archivo, hoja, variable y
  agrupación. Un descriptivo agrupado no acredita globales ni frecuencias del grupo.
- `Valores p` exige un método del catálogo que los produzca, familia compatible,
  variables utilizables y, al ejecutar, el componente seleccionado y su diseño.
- Los coeficientes exigen correlación compatible. ANOVA o un descriptivo no pueden
  suplirla. Pearson/Spearman solo acreditan productos comunes cuando el método está
  pendiente; el IC de Pearson no es un producto común y sigue bloqueado en ese caso.
- Se reconocen también salidas históricas verificables: coeficientes o matriz,
  estadístico global, medias por grupo y cambio pareado con incertidumbre. La
  estimación pareada requiere método compatible, dos medidas y un identificador.
- `Componente N: producto` liga la salida a ese componente (numeración desde 1).
  Una salida ligada no toma prestados resultados de otro componente.
- Un post hoc necesita `posthoc=welch_holm` confirmado en `ExecutionSpec`; el texto
  del proveedor no lo activa. Los IC descriptivos deshabilitados tampoco se cubren.
  Las pruebas comprueban tanto opciones deshabilitadas como resultados realmente
  calculados con las opciones habilitadas.
- La evaluación local de un componente en preparación no le exige producir las
  salidas ajenas. Antes de informar todo listo o reutilizar todo completado se
  revisa el conjunto de componentes y opciones. Ejecución conserva la revisión
  estricta completa; no se relajan sus controles mediante la opción interna local.

La cobertura estructural de una propuesta no acredita datos calculables ni diseño
confirmado. La preparación y ejecución siguen releyendo los originales, revisando
tamaños, constantes, tipos, ausencias, decisiones y métodos; nunca se inventan cifras.

## Conservación del alcance

`requested_scope.py` construye un contrato finito de productos exclusivamente con
mensajes de usuario y acciones autenticadas. No usa `detected_goal`, `primary_goal`,
resúmenes ni los `expected_outputs` del primer intento como fuente de obligaciones.
El contexto enviado al proveedor contiene los compromisos por separado; el control
efectivo se ejecuta en el servidor en ambos intentos y antes de persistir.

Se reconocen nombres del catálogo y formas acotadas de listas. No es interpretación
universal de lenguaje natural. Productos desconocidos, calificativos no verificables,
negaciones o referencias libres a componentes conducen a aclaración. La lista debe
conservar tanto las etiquetas exigidas como los componentes que las producen.

Si una salida del proveedor es desconocida y no existe alcance verificable del
usuario, se pide aclaración sin convertir esa sugerencia en requisito expreso y sin
aprobar automáticamente una sustitución más limitada. Puede usarse una sola generación
en ese caso. El máximo sigue siendo dos; no hay nuevas llamadas ni reintentos.

Una confirmación explícita como `Confirmo alcance: Resúmenes por grupo.` o
`Cambio de alcance: ...` puede revisar el contrato. `Sí`, `Continúa` o el silencio
no eliminan productos pendientes. Sin confirmación, nuevas menciones se acumulan.
Las preguntas conceptuales y discusiones sobre resultados no crean finalidades nuevas.

**Alternativas parciales:** sin compromisos de productos conjuntos, o cuando el
usuario declara alternativas independientes, se conservan alternativas válidas con
un aviso que dice que no se completaron todas. Cada alternativa retenida debe cumplir
sus compromisos esenciales. Se conservan las preguntas; una aclaración esencial
impide rescatar propuestas definitivas. Para un mismo análisis, productos repartidos
entre propuestas alternativas no acreditan una propuesta completa.

La aceptación nueva revalida el contrato actual y devuelve 422 `requested_scope`
sin cambiar el estado si falta un producto. El replay de una decisión histórica
ya aceptada conserva el comportamiento previo. UUID, procedencia y replay de turnos
completados siguen usando los RPC actuales, sin cambios de proveedor.

## Persistencia y compatibilidad histórica

El contrato se guarda de forma aditiva en `stage_data.requested_scope` JSONB, con
versión 1, productos, incertidumbre, modalidad y referencias de solicitudes del
usuario (acotadas a 30), más la posición hasta la que se procesaron mensajes. Esa
posición permite recuperar productos de turnos fallidos antes de un `Continúa`
posterior; un fallo del proveedor no los borra. Se escribe mediante la finalización atómica existente.
No requiere migraciones ni cambia Plan v1, sus snapshots, los resultados o la
atribución de turnos históricos.

Sin ese campo se revisan los mensajes auténticos disponibles. Si el historial de
30 mensajes está truncado, se exige confirmación de alcance en lugar de asumir que
no había compromisos anteriores. Los mensajes del modelo y resúmenes no sustituyen
la evidencia ausente. Los planes existentes no se reescriben.

La fixture positiva de `test_gemini.py` ahora especifica t pareada, identificador
y medidas cuantitativas sintéticas suficientes. Conserva todas sus aserciones;
su antigua promesa de cambio con método y pareamiento indefinidos tiene una nueva
regresión negativa explícita. No se convierte una expectativa insegura en una
excepción del validador ni se modifican evidencias históricas de Terra.
La reevaluación de la evidencia Terra ahora exige aclaración también para sus
salidas inferenciales libres/condicionales: antes se omitía toda validación de
productos por no contener descriptivos. Se conserva la comprobación de todos los
bytes y hashes, sin cambiar el archivo de evidencia ni adaptar sus planes.

## Validación final local

| Comprobación | Resultado |
| --- | --- |
| Backend en 23 procesos por módulo | **527 aprobadas, cero fallos y cero omisiones locales** |
| Nuevas regresiones inferenciales | 20 aprobadas; validación, preparación, cálculo real y HTTP con ambos proveedores simulados |
| Nuevas regresiones de alcance | 29 aprobadas; reducción, sustitución, ambigüedad, alternativas, preguntas, persistencia, aceptación, fallos, historial y replay |
| Bloqueo descriptivo original | 13 aprobadas, incluidos aceptación, preparación y ejecución históricas incompatibles |
| Rollback real y protección SQL | 10 aprobadas; backend anterior/auditado, 007 sola y 007 + 008, mismo UUID, proveedor/modelo, concurrencia, replay y RLS |
| Frontend sin cambios | 68 pruebas + 2 controles de configuración aprobados |
| TypeScript, lint, formato y build frontend | Aprobados; sin despliegue |
| PostgreSQL local WASM (`npm test` en `supabase`) | 5 aprobadas; cero omisiones |
| Ruff y formato del script de calidad | Aprobados; 54 archivos |
| Lint adicional de módulos heredados modificados | Aprobado |
| Sintaxis (`compileall`) y dependencias (`pip check`) | Aprobadas; sin nuevas dependencias |
| Diff y secretos | Aprobados; sin coincidencias de credenciales locales ni archivos privados añadidos |
| Hashes y alcance | 007, 008, motor numérico, diagnóstico y evidencia Terra intactos; sin cambios frontend |
| Reproducción del SHA auditado | Confirmados exactamente 3 fallos inferenciales y 2 de recorte; el control sin productos inferenciales pasa |
| CI de estos cambios | No ejecutada: no se hizo push |

Los errores esperados del arnés histórico son evidencia de los defectos del SHA
auditado, no fallos de la validación final. Los proveedores son dobles y transportes
simulados; PostgreSQL ejecuta SQL real compilado a WASM. No se presenta esto como
integración con servicios remotos.

Desglose de los 23 módulos backend:

| Módulo `test_*.py` | Aprobadas |
| --- | ---: |
| analysis_api | 7 |
| app | 10 |
| automatic_preparation | 35 |
| chat_api | 12 |
| execution_uncertainty | 12 |
| gemini_diagnostic | 10 |
| gemini_resilience | 17 |
| gemini | 41 |
| heterogeneous_planning | 20 |
| inferential_products | 20 |
| integral_execution | 10 |
| openai_provider | 36 |
| plan_capabilities | 13 |
| planning | 54 |
| profiling | 30 |
| provider_rollback | 10 |
| provider_selection | 17 |
| requested_scope | 29 |
| research_context | 5 |
| result_conversation | 5 |
| statistics_additional | 8 |
| statistics | 27 |
| terra_diagnostic | 99 |

Se repitieron los módulos afectados tras las últimas correcciones de conversación.
La pasada final está aprobada. Se corrigieron regresiones de interpretación de
resultados y de alternativas genéricas contra el catálogo; no se eliminaron sus
aserciones. Continúan avisos existentes de Starlette/TestClient y de tamaño del
chunk Vite; no impidieron las pruebas o el build.

## Archivos de esta corrección

| Área | Archivos |
| --- | --- |
| Catálogo y productos | `backend/app/models/analysis.py`, `backend/app/services/plan_capabilities.py`, `backend/app/services/statistics/catalog.py`, `methods.py` |
| Integración y preparación | `backend/app/services/gemini.py`, `backend/app/services/statistics/automatic.py`, `preparation.py` |
| Alcance, alternativas y persistencia | `backend/app/services/requested_scope.py`, `conversation.py`, `planning_validation.py`, `planning_errors.py`, `backend/app/api/chat.py` |
| Regresiones | `backend/tests/test_inferential_products.py`, `test_requested_scope.py`, fixture de `test_gemini.py`, reevaluación conservadora de `test_terra_diagnostic.py` |
| Reproducción y calidad | `backend/scripts/reproduce_pr07_p1.py`, `check_analysis_quality.py` |
| Documentación | Este informe, `docs/ARCHITECTURE.md`, `docs/SETUP.md` |

## Límites y estado operativo

- Catálogo y gramática finitos: la prosa no verificable puede requerir una aclaración
  adicional. No se promete reconocer toda formulación posible ni crear productos nuevos.
- Las opciones que Plan v1 no expresa, como habilitar post hoc, requieren una decisión
  de ejecución explícita; nombrarlas no configura el cálculo.
- No hubo llamadas reales a Gemini/OpenAI, créditos, accesos a Supabase/Vercel/Render,
  despliegues, variables modificadas ni migraciones remotas.
- 007 y 008 permanecen intactas. Gemini sigue predeterminado y Terra deshabilitado.
  El motor numérico y los archivos históricos de evidencia permanecen intactos.
- La CI remota continúa correspondiendo a `d04a679`: estos cambios no se han publicado.
  La revisión independiente y los pendientes operativos documentados siguen vigentes.

## Commits locales

- `48c0d80` — `fix(planes): validar productos inferenciales con el catálogo del motor`.
- `f066eee` — `fix(chat): conservar los productos solicitados durante la corrección`.
- Cierre documental: `docs: registrar correcciones y pruebas de los P1 del PR 7`.

Los commits permanecen exclusivamente en la rama local indicada, sin push ni otro PR.

**Decisión: APTO para actualizar el PR #7 y solicitar otra auditoría independiente.**
Se apoya en las reproducciones antes/después, la conservación de alcance y las
regresiones, además de las comprobaciones de calidad. No equivale a autorizar merge,
despliegue ni habilitación de Terra. No se publicaron estos cambios.
