# Informe técnico local: bloqueos del PR #7

17 de noviembre de 2026. Rama única `feat/integracion-multiproveedor-backend`.
Base auditada: `f6df957af358e5cf6f2c781a936c16d3e16b8aff`. Al iniciar, Git estaba
limpio y el PR #7 abierto hacia `develop`, en ese SHA, sin fusión automática.

## 1. Causas comprobadas

**A — Productos descriptivos.** `expected_outputs` no se contrastaba con la cobertura
de los componentes. `warn_capabilities` añadía texto a las limitaciones, pero no impedía
aceptar, preparar o calcular. `describe()` usa la agrupación y omite esa columna de
las frecuencias; no añade automáticamente otra ejecución global. Por eso un cálculo
correcto de una parte del plan podía aparecer como `completed` sin todos los productos.

**B — Rollback.** 007 añadía proveedor/modelo y los verificaba en
`begin_provider_chat_turn`, pero delegaba en `begin_chat_turn`. El RPC legacy seguía
aceptando solicitudes OpenAI y el backend anterior elegía su cliente Gemini. Devolver
un estado nuevo al legacy tampoco basta: esa versión puede continuar ante estados que
no reconoce. Era necesario denegar la adquisición mediante excepción SQL.

## 2. Solución A y alcance verificable

`validate_products` usa un catálogo finito de cadenas normalizadas y cobertura por
archivo/hoja/columna y agrupación. No pretende interpretar cualquier frase mediante
expresiones regulares ni acreditar todos los productos estadísticos posibles.

- Distingue resúmenes globales, por grupo, frecuencias categóricas globales, por grupo
  y de la variable agrupadora. Cada clase exige cobertura estructural de sus columnas.
- Las frases descriptivas no reconocibles devuelven `output_scope`: requieren aclarar
  el alcance en una propuesta revisada. Una cobertura insuficiente devuelve
  `output_capability`. Una advertencia no neutraliza ninguno de estos errores.
- Mantiene alias exactos genéricos históricos para productos ordinarios del componente,
  sin interpretar que prometen globales o frecuencias adicionales. Los controles
  inferenciales previos conservan sus restricciones; este catálogo no es un intérprete
  universal de promesas en prosa.
- Permite integrales descriptivas con componentes de alcances distintos, incluso de
  la misma familia. No permite usar componentes duplicados como solución ni modifica
  métodos, cálculos, fuentes o resultados del motor.
- No añade campos ni cambia Plan v1. Los planes históricos siguen legibles. Un plan
  con texto no verificable puede requerir una propuesta nueva antes de acciones nuevas;
  no se recorta `expected_outputs` ni se cambia el plan aceptado automáticamente.

| Punto de control | Comportamiento corregido |
| --- | --- |
| Generación | `validate_plan` compartido rechaza antes de persistir; usa la única corrección semántica existente y sus límites |
| Aceptación nueva | HTTP 422 con diagnóstico; no llama a `decide_proposal` ni cambia estado |
| Decisión ya aceptada | Replay idempotente, sin reescritura ni nueva transición; no acredita cobertura |
| Preparación histórica | Relectura de originales y validación; devuelve `UNSUPPORTED`, sin especificación ejecutable |
| Ejecución | `validate_spec` verifica productos tanto en API como en el hijo Python; una incompatibilidad no calcula ni termina como `completed` |
| Resultados ya guardados | Se leen/reproducen sin reescribirlos ni recalcularlos |

Las instrucciones productivas se agregan a ambos proveedores mediante
`PRODUCT_INSTRUCTIONS`. El `SYSTEM` histórico exportado, esquemas y evidencias Terra
mantienen sus hashes. La validación histórica M ahora detecta productos descriptivos
sin alcance verificable; no se altera el archivo para mantener su aprobación anterior.

## 3. Reproducción descriptiva

Datos sintéticos: cuatro medidas, dos grupos A/B. El mismo plan exige resumen global,
resumen por grupo y frecuencias del agrupador con un único componente agrupado.
Se ejecutan rutas reales de FastAPI, SQL local y motor Python, no un doble de cálculo.

| Versión/caso | Aceptación | Conversación | Preparación | Motor |
| --- | --- | --- | --- | --- |
| Backend real auditado `f6df957` | 200 | `ready` | `READY` | `completed`; solo dos filas agrupadas, sin resumen global ni tabla de frecuencias |
| Backend corregido, propuesta pendiente | 422 | Conserva `goal` | No se habilita | Bloqueado también al entrar directamente al motor |
| Backend corregido, propuesta histórica ya aceptada | 200 replay | No cambia la decisión histórica | `UNSUPPORTED` | Bloqueado |
| Integral corregida con tres componentes separados | Validación válida | Sin aceptación automática | `READY` | `completed`, con global, dos grupos y frecuencias A/B comprobadas |

También se comprueban descriptivo global, agrupado soportado y frecuencias categóricas
válidos; integral con un componente faltante; texto desconocido; corrección semántica
Gemini y OpenAI; aceptación sin cambios ante fallo y conservación de originales.

## 4. Solución B, persistencia y recuperación

Se conserva 007 intacta y se añade **008**, transaccional y con prerrequisitos de esquema.
No modifica datos existentes ni cambia RLS:

- `begin_chat_turn` conserva Gemini legacy con modelo desconocido (`null`) y replay
  completado. Rechaza por excepción solicitudes OpenAI o vinculadas a un modelo que
  ese backend no puede acreditar. Un turno Gemini nuevo con modelo conocido también
  requiere un backend que lo comunique; no se borra el modelo para desbloquearlo.
- `begin_provider_chat_turn` adquiere directamente el turno, sin delegar en el legacy.
  Conserva los bloqueos de conversación/cálculo y compara UUID, payload, proveedor y modelo.
- `finish_chat_turn` conserva la transacción de 005 y exige procedencia coincidente
  para respuestas de solicitudes vinculadas, diferenciando mensajes deterministas.
- Un trigger impide reescribir proveedor/modelo conocidos, incluidos modelos históricos
  de solicitudes completadas. Los modelos desconocidos no se inventan retroactivamente.
- `provider_rollback_safety()` y el backend bloquean Terra si falta 008. Con solo 007,
  aun con bandera activada y credencial sintética, el backend corregido devuelve 503
  antes de registrar una solicitud nueva o llamar al modelo.

## 5. Reproducción de rollback con código real

No se recibió un archivo del auditor. Se reproduce la secuencia completa descrita,
con `git archive` de los backends reales `f6df957` y
`74b957700dd1eca34e59a2c488bc44e85f26ec4d`, sin cambiar de rama ni modificar ese código.
El backend auditado inicia un turno Terra simulado que falla; se restaura el backend
anterior y se reintenta **el mismo UUID y payload** con la conversación aún en OpenAI.

| Esquema/caso | Resultado observado |
| --- | --- |
| 007 sola + backend anterior | HTTP 200, una llamada Gemini simulada; solicitud pasa a completed conservando atribución OpenAI/Terra: defecto reproducido |
| 007 + 008 + backend anterior | HTTP 409, cero llamadas Gemini; selección y solicitud fallida OpenAI/Terra intactas |
| Reintento posterior con backend compatible y Terra | HTTP 200, una llamada Terra simulada y metadata OpenAI/modelo correcto |
| Replay completado desde el backend anterior | HTTP 200 replay, cero llamadas a modelos y sin duplicación |
| Gemini legacy sin modelo registrado | Funciona con 007 y 008; replay no llama al modelo ni inventa modelo histórico |
| Gemini con modelo registrado, otro modelo o legacy | Bloqueado; con modelo correcto puede adquirirse de nuevo |

La prueba también verifica finalización con procedencia incorrecta, selección antes y
después de fallos, inmutabilidad del vínculo, solicitudes HTTP concurrentes, un único
mensaje por UUID y RLS entre dos usuarios. Las solicitudes concurrentes se serializan
en una instancia PGlite; no se presenta esto como prueba de carga distribuida.

Auth/REST/Storage están emulados en loopback, con JWT y claves sintéticos. Las funciones,
transacciones y políticas RLS se ejecutan en PostgreSQL real compilado a WASM. No equivale
a Supabase remoto ni a una integración real con modelos.

## 6. Resultados de validación

| Comprobación | Resultado final |
| --- | --- |
| Backend, 21 módulos en procesos aislados | 478 pruebas aprobadas en las validaciones finales, sin omisiones locales ni fallos pendientes |
| Pruebas nuevas de capacidades | 13 aprobadas |
| Reproducciones históricas y protección SQL | 10 aprobadas; incluye ambas reproducciones con backends reales |
| SQL existente (`npm test`, PostgreSQL WASM) | 5 aprobadas |
| Frontend sin cambios | 68 pruebas y 2 controles de configuración aprobados |
| TypeScript, lint, formato y build frontend | Aprobados |
| Ruff/formato Python del script de calidad | Aprobados; 50 archivos |
| Lint adicional de módulos heredados modificados | Aprobado |
| Sintaxis Python y dependencias (`pip check`) | Aprobadas |
| Diff, secretos, evidencia y alcance | Aprobados; sin credenciales locales ni cambios frontend; 007, evidencia Terra y cálculos originales intactos |
| CI remota de estas correcciones | No ejecutada: no se autorizó push |

La primera pasada encontró una regresión de replay de propuestas ya aceptadas. Se
corrigió el código para conservar ese contrato; la prueba existente no se eliminó ni
se relajó. Solo se actualizaron expectativas históricas que afirmaban que un aviso
reparaba el plan o que una validación metodológica acreditaba todos sus productos.
Ahora comprueban el bloqueo y la conservación de bytes/hashes, con nuevas pruebas de
cobertura para impedir que esas expectativas oculten el defecto auditado.

El host Windows presentó un fallo nativo COM/WMI (`0x8007000e`) durante la obtención de
metadatos de plataforma. Las validaciones finales usaron el fallback WinAPI de Python
en los procesos de prueba, sin modificar rutas, cálculos ni aserciones. El arnés limita
tiempo y termina árboles de procesos. No se omiten escenarios por ese incidente.
Continúan avisos existentes de Starlette/TestClient y del chunk Vite superior a 500 kB;
no impidieron la compilación ni se cambiaron dependencias para ocultarlos.

## 7. Archivos modificados

| Área | Archivos |
| --- | --- |
| Capacidades e integración | `backend/app/services/plan_capabilities.py`, `gemini.py`, `openai_provider.py`, `methodology.py`, `planning_errors.py` |
| Controles de API/ejecución | `backend/app/api/chat.py`, `backend/app/services/providers.py`, `backend/app/services/statistics/automatic.py`, `preparation.py` |
| Pruebas nuevas | `backend/tests/test_plan_capabilities.py`, `test_provider_rollback.py`, `backend/tests/helpers/run_historical_backend.py`, `run_historical_statistics.py` |
| Pruebas existentes | `backend/tests/test_chat_api.py`, `test_provider_selection.py`, `test_terra_diagnostic.py` |
| PostgreSQL local y migración | `supabase/tests/helpers/postgrest-bridge.mjs`, `supabase/migrations/202611170008_provider_rollback_guard.sql`, `supabase/checks/provider_rollback.sql` |
| Verificación | `backend/scripts/check_analysis_quality.py`, `.github/workflows/ci.yml` |
| Documentación | `docs/PR07_CORRECTION_PLAN.md`, `PR07_CORRECTION_REPORT.md`, `PR07_SAFE_ROLLOUT.md`, `MULTIPROVIDER_BACKEND.md`, `SETUP.md`, `ARCHITECTURE.md` |

El workflow solo prepara historial Git y Node/PGlite para reproducir el backend real
en la futura CI; no incorpora despliegues. No se modificaron frontend, requisitos,
cálculos de `engine.py`/`procedures.py`, 007, informes `docs/TERRA*` ni el diagnóstico aislado.

## 8. Migraciones, riesgos y verificaciones externas

El usuario ejecutó una consulta de solo lectura en su Supabase y compartió una captura:
007 falta en ese entorno. No se confirmó el estado de todos los demás, por lo que se
conservó la migración original. No se accedió a Supabase, Vercel o Render mediante cuentas
vinculadas. No se aplicaron migraciones ni se asumió que una configuración externa cambiara.

La [secuencia manual](PR07_SAFE_ROLLOUT.md) indica plataforma, ubicación, configuración y
verificación: confirmar entorno y prerrequisitos; impedir previews Git no autorizadas;
mantener Terra deshabilitado; instalar 007/008 pendientes antes del código; verificar RPC,
permisos y RLS; probar Auth/CRUD/turno determinista/perfilado con dos cuentas; conservar
un artefacto de recuperación que incluya ambas correcciones. No basta `/health`.

Recuperar `74b9577` demuestra la barrera B de 008, pero no es una recuperación funcional
completa de A. No revertir el esquema ni usar un backend sin ambas correcciones como
reserva aprobada. Terra sigue deshabilitado y no está declarado preparado para producción.

Pendientes: autorización expresa para publicar; confirmación del control de previews;
CI del commit actualizado; instalación y pruebas reales por el propietario en cada entorno;
revisión independiente del diff. El catálogo conservador puede bloquear planes históricos
de redacción ambigua hasta aclarar su alcance. Los límites de solicitudes siguen siendo
por proceso. RLS aísla usuarios; no autentica JSON que el propio dueño manipule directamente.

## 9. Commits y recomendación

Commits funcionales locales preparados, en español y con la identidad Git existente:

- `73987a6` — `fix(planes): bloquear productos descriptivos sin cobertura verificable`.
- `ec38402` — `fix(proveedores): impedir cambios de destinatario al recuperar el backend`.

El commit final de documentación incorpora este informe y la secuencia manual; su
identificador se informa al cerrar la entrega y figura en `git log`.

**APTO para actualizar el PR #7 tras tu revisión y autorización expresa.** La recomendación
se basa en la reproducción de los defectos con código histórico real, el bloqueo posterior,
la cobertura de productos y las regresiones locales; no en la CI anterior del SHA auditado.
No equivale a aprobación de merge ni producción. No autoriza push, despliegue, migraciones
ni habilitación de Terra. No se publicó la rama ni se actualizó o fusionó el PR.
