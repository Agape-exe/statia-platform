# Cierre de validación aislada de GPT-6.1 Terra

Fecha de cierre: 17 de noviembre de 2026. Rama: `test/preparar-terra-mi`. Base comprobada: `origin/develop`, commit `8274c1241a30e4aa9777c6f7ad8039a4c430dbe4` (PR #5 incorporado). Sin divergencias al preparar el cierre.

La fase aislada queda cerrada como evidencia de **planificación experimental**, con límites metodológicos y operativos documentados. Terra no está integrado en FastAPI ni validado en producción; Gemini continúa como proveedor productivo y Python mantiene la ejecución estadística determinista autorizada.

## Resultados reales e interpretación

| Caso | Evidencia | Resultado y alcance |
| --- | --- | --- |
| A | Resultado histórico confirmado por el usuario | JSON mínimo aprobado; no se repitió durante M/I ni en este cierre. No demuestra planificación estadística por sí solo. |
| D | Resultado histórico confirmado por el usuario | Una propuesta descriptiva aprobó Pydantic y metodología. No se repitió durante M/I ni en este cierre. |
| M | Generación real y auditoría sanitizada persistidas | Cuatro propuestas; Pydantic, validadores nativos y cobertura aprobados. El diagnóstico inicial falló en una condición adicional de independencia; se conserva ese fallo. |
| M, reevaluación | Validaciones exclusivamente locales sobre la evidencia real guardada | Las cuatro propuestas y la prosa persistidas aprueban los criterios corregidos. No se reconstruyó una respuesta original ausente. El resultado es `passed_for_persisted_evidence`. |
| I | Una generación real; AssistantReply original completo en almacenamiento privado | Una propuesta integral con descripción y Pearson. JSON, contrato, metodología nativa y criterios adicionales aprobados. La revisión manual detectó una diferencia entre salidas prometidas y capacidad de ejecución. |

### Latencias y consumo observados

Tarifas de M/I confirmadas por el usuario el 16 de noviembre: entrada US$1,00/millón, entrada cacheada US$0,05/millón y salida US$5,00/millón incluyendo razonamiento. Son tarifas históricas configuradas, no una promesa de precios futuros. D conserva el importe histórico reportado.

| Caso real | HTTP / estado | Duración | Entrada | Salida total | Razonamiento incluido | Caché de entrada | Costo estimado |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A | 200 / completed | 4,13 s | No conservado aquí | No conservado aquí | No conservado aquí | No conservado aquí | No conservado aquí |
| D | 200 / completed | 14,50 s | 5 924 | 916 | No conservado aquí | No conservado aquí | US$0,01050 |
| M | 200 / completed | 36,011 s | 6 019 | 3 003 | 267 | 0 | US$0,021034 |
| I | 200 / completed | 20,708 s | 6 013 | 1 609 | 124 | 0 | US$0,014058 |

El razonamiento ya forma parte de la salida total y no se factura dos veces en la estimación. En M e I hubo una sola solicitud por caso, sin reintentos. **Este cierre no realizó solicitudes reales a OpenAI o Gemini ni consumió créditos adicionales.** Las llamadas Git/GitHub y la CI no son llamadas a los proveedores de modelos.

## Hallazgos metodológicos y operativos

### Independencia en M

El diagnóstico adicional exigía una advertencia de independencia en `requirements` de todos los planes. La propuesta descriptiva sin inferencia la trataba en `limitations`; la regla rechazó un plan que ya había aprobado los validadores nativos.

La corrección quedó limitada al diagnóstico: descripción de registros sin inferencia no exige independencia; los procedimientos inferenciales deben reconocer restricciones pendientes en su plan; los integrales se evalúan por componentes y por alcance de las advertencias. Una advertencia no confirma el diseño ni autoriza calcular. Se conservan sin cambios los contratos, validadores productivos, comprobaciones de referencias, cobertura, catálogo y afirmaciones numéricas.

### Salidas descriptivas prometidas en I

El plan real pide a un solo componente descriptivo resúmenes globales, resúmenes por `grupo` y frecuencias de `grupo`. En `backend/app/services/statistics/procedures.py`, `describe()` recorre los niveles cuando hay `role=group` y omite la variable de agrupación al generar frecuencias. El despacho de `engine.py` no crea componentes descriptivos adicionales para completar esas promesas.

Por tanto, el contrato y las familias/métodos son válidos, pero **el plan original de I no está listo para ejecutarse sin revisar su alcance**. La observación se determinó leyendo código, sin calcular ni modificar el motor. El PR no corrige el plan recibido ni cambia la evidencia para ocultar esa diferencia. Una futura sesión debe decidir cómo comprobar las salidas prometidas frente a las capacidades efectivas del motor.

## Evidencia incluida y excluida

Se incluyen el diagnóstico M/I, sus pruebas, el control de calidad Python que incorpora esas pruebas, este cierre y los informes sanitizados:

- [Preparación histórica](TERRA_MI_PREPARATION.md).
- [Ejecución M](TERRA_M_LIVE_RESULT_2026-11-16.md) y su [registro JSON sintético](TERRA_M_LIVE_RESULT_2026-11-16.json).
- [Reevaluación M](TERRA_M_INDEPENDENCE_REVIEW_2026-11-16.md) y su [registro JSON](TERRA_M_INDEPENDENCE_REVIEW_2026-11-16.json).
- [Ejecución I y observación operativa](TERRA_I_LIVE_RESULT_2026-11-16.md) y su [resumen sanitizado](TERRA_I_LIVE_RESULT_2026-11-16.json).

Los documentos históricos son snapshots de sus etapas: pueden mencionar que entonces no había commits, que la preparación aún no autorizaba llamadas o el nombre previo de la rama. No describen el estado final. La rama actual cumple la convención `test/`; no se crearon ramas nuevas en el cierre.

Se excluyen:

- `backend/test_terra_statia_env.py`: script histórico A/D conservado localmente e intacto, con SHA-256 `95d8581522b1635c2f208fc6303ac808fd1e5279a8de09d6dee94298447a5c26`. Tiene comportamiento antiguo de llamadas reales predeterminadas, por lo que no se publica como entrada segura del diagnóstico. `.gitignore` excluye exactamente este archivo. La prueba de su hash/conversor se omite explícitamente en checkouts donde no existe.
- Respuesta completa y evidencia privada I: permanecen fuera del checkout, en `%LOCALAPPDATA%\Statia\terra-evidence\I-20261117T010527Z-cb4b81191b80\`, con ACL restringida al usuario y SYSTEM. No se copian al repositorio. El resumen compartible solo contiene métricas, componentes, límites y huellas.
- `.env`, claves, credenciales, archivos de usuarios, encabezados de autorización, cuerpos HTTP crudos y contenido de razonamiento.

M no conserva todos los campos originales de `AssistantReply`; la reevaluación documenta cada campo ausente y los valores predeterminados usados únicamente para la vista local de los planes. I sí conserva el texto JSON original completo y permite replay local íntegro. El original I tiene SHA-256 `2c509cd6ac8353e0c909719a301c302e2cfeb4c2f841e243eee9cb2173e375bc`.

Los informes históricos mantienen exactamente sus bytes y hashes. `.gitattributes` evita que la conversión de finales de línea entre Windows y Linux cambie esa evidencia. Ninguno de esos archivos se editó durante el cierre.

## Pruebas locales y reproducibilidad

Las pruebas automatizadas utilizan datasets sintéticos, respuestas simuladas y `httpx.MockTransport`. Los tests que recorren la ruta `--live` sustituyen el transporte y el almacenamiento por entornos temporales controlados; no consumen créditos. La regresión M lee directamente las propuestas reales sanitizadas guardadas.

El diagnóstico es seco por defecto. Solo `--live` permite una solicitud real y exige caso individual y tarifas con su referencia; no hay consultas `/models`, herramientas, correcciones, redirecciones ni reintentos automáticos. Esta bandera técnica no constituye por sí sola autorización del usuario: toda llamada real futura requiere una nueva autorización explícita. Los comandos pagados de los documentos históricos son referencias, no instrucciones para repetirlos durante revisión o CI.

Comandos locales desde `backend`:

```powershell
& .\.venv\Scripts\python.exe scripts/diagnose_terra.py
& .\.venv\Scripts\python.exe -m pytest tests/test_terra_diagnostic.py -q
& .\.venv\Scripts\python.exe scripts/check_analysis_quality.py
& .\.venv\Scripts\python.exe -m pip check
```

En Linux/CI se ejecutan todos los módulos `tests/test_*.py` en procesos separados, como ya establece el workflow existente, para no acumular memoria entre pruebas del motor. En Windows las pruebas ACL específicas se ejecutan; en Linux se omite únicamente ese caso de plataforma, y el script A/D ausente conserva su omisión explícita. No se presentan esas omisiones como integraciones reales aprobadas.

Controles ejecutados el 17 de noviembre de 2026:

- Backend completo: **402 pruebas aprobadas**, 17 módulos en procesos aislados, cero fallos y cero omisiones locales; duración total 755,05 s. Incluye las **99 pruebas específicas** del diagnóstico Terra. Las omisiones previstas de plataforma y del archivo A/D excluido solo corresponden a otros entornos como CI Linux.
- `scripts/check_analysis_quality.py`: lint y formato aprobados, 40 archivos. Sintaxis Python y `pip check` aprobados.
- Modo seco M/I: ambos devuelven `dry_run`, `requests_attempted=0`, sin llamadas ni evidencia privada cargada y sin validaciones de respuestas simuladas presentadas como éxito real.
- Frontend: **68 pruebas aprobadas**, **2 comprobaciones de configuración aprobadas**, TypeScript, lint, formato y build aprobados. La advertencia existente de Vite por un chunk superior a 500 kB no bloqueó el build; no se desplegó.
- SQL local: **4 pruebas aprobadas** mediante el entorno de prueba del repositorio, sin contactar Supabase remoto.
- Diff y espacios finales aprobados. Los siete documentos históricos coinciden byte por byte con sus blobs preparados para Git. Escaneo de los 13 archivos del PR sin coincidencias con credenciales locales y con JSON válido; no se incluyeron `.env`, respuesta privada completa, credenciales o el script A/D.
- La respuesta privada I conserva su SHA-256 original. Los hashes de los informes históricos y el script A/D también permanecen intactos.

La CI remota se evaluará en el PR. Estos resultados locales no se presentan como CI Linux ejecutada ni como aprobación de un servicio productivo.

## Riesgos pendientes y siguiente sesión

- No hay integración multiproveedor, pruebas productivas, benchmark representativo ni garantía de precisión general. Una generación por escenario no demuestra consistencia entre respuestas.
- La diferencia de salidas descriptivas de I sigue pendiente; independencia, diseño, tipos y ausencias deben revisarse antes de cualquier ejecución estadística.
- La detección por patrones de cifras, supuestos y contenido sensible es conservadora y parcial; no sustituye revisión humana ni acredita ausencia universal de información personal.
- Un timeout puede tener consumo remoto incierto. Se registra sin reintentar; uso ausente queda desconocido.
- No se probaron fallos reales de cuota, disponibilidad o red en esta fase. Los fallos automatizados corresponden a simulaciones.

El PR puede integrarse como **pruebas y documentación**, sujeto a revisión y CI aprobada. No habilita Terra ni modifica Gemini. La integración multiproveedor pertenece a una sesión posterior, en una nueva rama `feat/` desde `develop` actualizado. No se fusiona automáticamente ni se despliega durante este cierre.
