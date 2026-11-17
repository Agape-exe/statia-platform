# Terra — Única ejecución real del escenario I

Fecha local: 16 de noviembre de 2026, America/Lima. El nombre del directorio privado utiliza UTC y por eso contiene `20261117`. Rama verificada antes y después: `test/preparar-terra-mi`.

## 1. Estado y alcance

**I superó los validadores de planificación y el diagnóstico corregido.** HTTP 200, generación `completed`, código de salida 0. Se realizó exactamente una solicitud real a `gpt-6.1-terra`, con razonamiento `medium`, sin reintentos, correcciones automáticas ni consultas de autenticación. No se ejecutaron A, D o M contra proveedores en esta intervención.

La revisión manual encontró una observación sobre las salidas descriptivas prometidas frente al comportamiento actual del motor. El éxito del diagnóstico no equivale a que el plan esté preparado para ejecución sin revisión de ese alcance. No se ejecutaron cálculos estadísticos del plan.

## 2. Métricas reales

| Métrica | Resultado |
| --- | --- |
| Modelo | gpt-6.1-terra |
| HTTP | 200 |
| Estado | completed |
| Duración medida por el diagnóstico | 20,708 s |
| Tokens de entrada | 6 013 |
| Tokens de salida totales | 1 609 |
| Razonamiento, incluido en la salida | 124 |
| Salida visible derivada | 1 485 |
| Entrada cacheada | 0 |
| Límite configurado de salida total | 8 000 |
| Costo estimado | US$0,014058 |
| Propuestas | 1 |
| Componentes | 2 |

El límite de 8 000 es el ya preparado y justificado en `TERRA_MI_PREPARATION.md`: I produce un único integral, frente a las hasta cuatro propuestas de M. La solicitud autorizaba conservar un límite distinto previamente justificado; no se cambió a 12 000. No hubo agotamiento del presupuesto de tokens ni respuesta incompleta.

Tarifas confirmadas por el usuario: entrada US$1,00/millón, caché US$0,05/millón y salida US$5,00/millón incluyendo razonamiento. Costo: `(6013 × 1 + 0 × 0,05 + 1609 × 5) / 1 000 000 = US$0,014058`. No se suman de nuevo los 124 tokens de razonamiento.

## 3. Validación estructural y de solicitud

| Comprobación | Resultado |
| --- | --- |
| JSON íntegro | Aprobado |
| AssistantReply / Pydantic | Aprobado |
| validate_reply, con planes y cobertura activados | Aprobado |
| Una única propuesta integral | Aprobado |
| Al menos dos familias y métodos distintos | descriptive y correlation; descriptive y pearson |
| Referencias exactas de archivo, hoja y columnas | Aprobado |
| Cobertura de variables raíz por los componentes | Aprobada |
| Dependencias y ausencia de integrales anidados | Aprobado |
| Catálogo, tipos e identificadores | Aprobado |
| Independencia y restricciones inferenciales pendientes | Aprobado |
| Afirmaciones numéricas inventadas | Ninguna detectada; revisión manual sin resultados numéricos en la propuesta |
| Cumplimiento del escenario I | Aprobado |

`recommendations_requested=false`: no se fuerza una cuota de múltiples propuestas en I. El modelo no incluyó una comparación entre grupos; era opcional y bastaban dos procedimientos compatibles.

La respuesta conserva `suggested_stage=proposal`, `confirmation_required=true`, `clarification_required=false`, `methodology_confirmed=false`, `joins=[]` y `comparison=null`. La independencia no se presenta como confirmada. `registro_id` no se selecciona como medida.

Después de recibirla se repitieron únicamente validaciones locales sobre el `AssistantReply` completo guardado. El replay completo aprobó sin reconstruir campos omitidos. La huella del payload coincide con la preparada: `cdc736000ff4ab14ab613f9e8284138d9499db00a3bcf943749bb8b070baca1b`.

## 4. Propuesta integral recibida

Título: **Descripción y correlación exploratoria**.

Objetivo original: «Describir `medida_a` y `medida_b` en conjunto y según `grupo`, y explorar la relación entre ambas medidas».

Variables raíz: `medida_a` y `medida_b` con rol `outcome`; `grupo` con rol `group`. Las referencias pertenecen al dataset sintético `terra_sintetico.csv`, hoja `tabla`, ID `00000000-0000-0000-0000-000000000002`.

El contrato `AnalysisComponent` no tiene campos propios de justificación, requisitos o limitaciones. Esos campos están en el `Plan` original. A continuación se explica qué partes de ese texto compartido corresponden a cada componente; no se atribuyen campos nuevos al JSON del modelo.

### Componente 1: descripción

- Procedimiento: `descriptive`; método reconocido del catálogo: `descriptive`.
- Método original: estadística descriptiva de `medida_a` y `medida_b`, globalmente y por `grupo`, y frecuencias de `grupo`.
- Variables: `medida_a`, `medida_b`, `grupo`.
- Justificación, según el plan: conocer las distribuciones por grupo.
- Requisitos explícitos del plan: revisar significado y unidades de ambas medidas, categorías de `grupo` y valores ausentes.
- Limitaciones pertinentes del plan: datos sintéticos y diseño no informado. Describir los registros no confirma independencia ni habilita generalización.
- Independencia: no se exige confirmarla para resúmenes observados sin inferencia. No se solicitan intervalos descriptivos en este componente.
- Observación operativa: el alcance global, agrupado y de frecuencias de la agrupación requiere revisión antes de ejecutar; véase la sección 6.

### Componente 2: correlación

- Procedimiento: `correlation`; método reconocido del catálogo: `pearson`.
- Método original: correlación de Pearson entre `medida_a` y `medida_b`.
- Variables: `medida_a`, `medida_b`. No incorpora `grupo` a esta correlación global.
- Justificación, según el plan: explorar asociación lineal entre las medidas cuantitativas.
- Requisitos explícitos: revisar observaciones válidas en ambas medidas, forma de la relación y atípicos; verificar independencia con el diseño —muestreo, repeticiones, pareamiento y conglomerados— y los supuestos distributivos pertinentes para inferir.
- Limitaciones explícitas: independencia sin confirmar, sensibilidad a atípicos y relaciones no lineales, ausencia de causalidad; una correlación global no establece la relación dentro de cada grupo.
- Supuestos pendientes: independencia, adecuación de la relación lineal y condiciones distribucionales para cualquier resultado inferencial posterior.

Los métodos pertenecen a las familias correctas del catálogo y las variables son compatibles con sus procedimientos. El transporte no expone `depends_on`; los valores internos por defecto son `[]` para ambos componentes, con orden resoluble `[0,1]`. El original permanece sin esos campos añadidos.

## 5. Calidad metodológica y supuestos

La propuesta distingue descripción de inferencia, mantiene la independencia pendiente, no inventa diseño, no trata el identificador como resultado y no interpreta asociación como causalidad. El método correlacional y la descripción aportan dos objetivos distintos. También advierte sobre la diferencia entre asociación global y dentro de los grupos.

Los supuestos todavía no fueron comprobados empíricamente. Pertenecen a una revisión y ejecución posteriores con decisiones explícitas del usuario. La aceptación de un plan, la validación del JSON y esta prueba del proveedor no autorizan un cálculo ni convierten advertencias en evidencia del diseño.

## 6. Problemas y límites encontrados

No hubo error HTTP, generación incompleta, error de contrato ni rechazo metodológico de los validadores. El diagnóstico registró `success`.

**Observación manual de compatibilidad operativa:** el componente descriptivo promete simultáneamente resúmenes globales, resúmenes por `grupo` y frecuencias de `grupo`. En la implementación actual de `statistics/procedures.py`, `describe()` selecciona los niveles cuando existe una variable con `role=group` y omite esa misma columna al generar las tablas de frecuencias. Con este componente se obtendrían resúmenes por grupo; no se añaden automáticamente el resumen global ni las frecuencias de la variable de agrupación. `engine.py` despacha el componente sin crear otros descriptivos adicionales.

Esta diferencia se identificó por lectura del código, sin ejecutar el motor. Las familias y tipos del plan son válidos, pero esas salidas prometidas necesitan aclaración o una propuesta revisada antes de ejecutar. No se corrigió el plan recibido, no se cambió el motor y no se hizo una llamada adicional. La observación no queda oculta bajo el éxito de Pydantic o del diagnóstico.

La evaluación es una sola generación sintética; no demuestra calidad universal, reproducibilidad entre generaciones ni resiliencia real ante cuotas o indisponibilidad. Los controles de prosa son conservadores, no una verificación semántica exhaustiva.

## 7. Evidencia completa y protección

Ubicación privada local, fuera del checkout y fuera de Git:

`%LOCALAPPDATA%\Statia\terra-evidence\I-20261117T010527Z-cb4b81191b80\`

- `assistant_reply.json`: los 5 777 bytes UTF-8 del texto JSON original completo, guardados antes de validarlo. Conserva sus 14 campos raíz y todos los campos recibidos, incluidos anulables. No se normalizó mediante Pydantic, no se completaron campos ni se reconstruyó el original.
- `metrics_and_validations.json`: métricas reales y resultados de validación, separados del original.
- `criteria.json`: límites y criterios de aprobación/rechazo configurados antes de la llamada.
- `attempt.json`: selección del caso y máximo de una solicitud.
- `offline_validation_report.json`: replay local, componentes y observación manual de alcance.

SHA-256 del original: `2c509cd6ac8353e0c909719a301c302e2cfeb4c2f841e243eee9cb2173e375bc`. Se comprobó de nuevo tras el replay y la generación del informe; el original permanece intacto.

La carpeta tiene herencia desactivada y dos identidades autorizadas: usuario actual y SYSTEM. Se comprobaron las ACL de la carpeta y de sus archivos. Al estar fuera del repositorio, la evidencia completa queda excluida de este Git sin depender de un patrón de `.gitignore`.

No se guardaron claves, cabeceras, cuerpo HTTP crudo ni contenido de razonamiento. La única entrada enviada fue el contexto sintético preparado. La captura comprueba posibles claves, JWT y direcciones de correo antes de guardar; si aparecen, falla sin modificar ni persistir esa respuesta. El informe compartible no contiene la respuesta completa ni información personal.

El resumen sanitizado está en [TERRA_I_LIVE_RESULT_2026-11-16.json](TERRA_I_LIVE_RESULT_2026-11-16.json).

## 8. Preparación y verificaciones anteriores a la llamada

Se modificaron exclusivamente el diagnóstico y sus pruebas para capturar el original, conservar validaciones separadas y fallar antes de red si no puede prepararse la evidencia. No cambió el payload, el esquema, el esfuerzo o el presupuesto preparado de I. Se exige además diversidad de métodos estadísticos, no solo etiquetas distintas de familia.

La versión final pasó **99 pruebas específicas y 241 pruebas relevantes** con respuestas y proveedores simulados, antes de la llamada real. Ruff, formato, compilación Python y `check_analysis_quality.py` aprobaron. Una advertencia existente de deprecación de Starlette/TestClient no impidió las pruebas.

Se verificó también la protección real y escritura de una carpeta de prueba sintética, sin solicitudes al proveedor. Esa prueba detectó que quitar solo la herencia no eliminaba entradas explícitas. La solución final restablece la DACL del directorio nuevo y vacío, aplica las dos identidades y verifica el resultado. Los intentos de prueba de permisos no hicieron llamadas ni consumieron créditos. La prueba restringida de pytest se interrumpió por problemas de acceso a temporales; las verificaciones finales fuera del sandbox aprobaron.

Los informes M y su reevaluación, el script A/D y el documento de preparación permanecen intactos. No se modificaron Gemini, FastAPI, contratos productivos, motor, Supabase ni frontend. Sin commits, PR, merges, pushes o despliegues.

## 9. Viabilidad de integración

La evidencia A/D histórica, M y esta prueba I justifican considerar a Terra como proveedor **opcional experimental de planificación** en una sesión de integración autorizada. I demuestra compatibilidad real con el transporte, el contrato y los validadores de Statia, con respuesta completa conservada y costo medido.

Todavía no justifica habilitarlo en producción ni ejecutar automáticamente sus planes. Antes de una integración debe resolverse cómo se verifican las salidas prometidas frente a las capacidades del motor, incluida la observación descriptiva encontrada. Gemini continúa como proveedor productivo y el motor Python conserva la ejecución determinista autorizada.

**Detenido tras la única llamada autorizada de I.** No se han realizado otras solicitudes ni cálculos estadísticos del plan.
