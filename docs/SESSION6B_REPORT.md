# Sesión 6B — corrección final y validación local

**APTO para segunda validación manual local.** Rama existente
`fix/correcciones-validacion-sesion6`, continuada desde `63af6ac` sin rehacer Sesión 6.
No hubo push, PR, merge, despliegue, migraciones, cambios de entorno ni llamadas
reales a Gemini/Terra. Los recorridos aprobados manualmente se conservaron.

## Causas raíz y resultado

| Incidencia | Causa y corrección |
| --- | --- |
| S6-01/02 Welch | La solicitud literal producía `global + global_test`: el texto «p global» impedía clasificar las medias como agrupadas. Ahora separa alcance del resumen y alcance del contraste. |
| Cobertura de Welch | El motor ya devuelve N, media y DE por grupo, pero la cobertura de `Resúmenes por grupo` solo acreditaba componentes descriptivos. Ahora acredita la comparación registrada, para su resultado y agrupador exactos. No acredita globales, frecuencias ni columnas de otro componente. |
| Productos/contrato | Se reconocen N/media/DE agrupadas, F, p global y grados de libertad. ANOVA Welch sigue como una propuesta `group_comparison`, `comparison=null`; no se amplía el contrato de dos grupos ni se añade un cálculo. El método Welch solicitado queda vinculado al alcance y no puede sustituirse por ANOVA clásico. |
| Corrección fallida | Tras las dos respuestas permitidas, una solicitud clara ya no vuelve a «¿global o por grupo?». Informa que falló la generación, conserva productos/exclusiones y no guarda un plan incompleto. El diagnóstico es texto funcional, no una ejecución ni un éxito estadístico. |
| Caché de alcance | Una conversación de Sesión 6 puede conservar el `global` mal detectado. Se reconstruye el alcance derivado solo si toda su evidencia de usuario sigue disponible en el historial completo. Solicitudes globales auténticas y contextos truncados no se recortan. |
| S6-03 Datos | «Ver datos» abre registros originales, separado del perfil. Endpoint autenticado, paginación de 50 filas en UI (máximo 100 por petición), desplazamiento horizontal/vertical, CSV/XLSX/JSON tabular. PDF mantiene metadatos. |
| S6-04 Resultados | Un solo «Cerrar detalle», sin enlace redundante al módulo ni otro cierre en la tarjeta/fila activa. Se conserva ZIP, consulta desde otros módulos, parámetros adicionales e historial del navegador. |
| S6-05 Asimetría | Instrucciones prudentes y control finito de afirmaciones observadas: media superior a mediana no confirma asimetría ni intensidad. Se rechaza la afirmación excesiva y se usa la corrección semántica existente. Sin nuevas medidas. |
| S6-06 Procedencia | La sustitución indiscriminada de UUID por «archivo del proyecto» también afectaba IDs de ejecución. Ahora se preservan los IDs de ejecución verificados y se rechazan IDs inventados/marcadores antes de sustituir texto. El marcador legado se omite solo en presentación; no se modifica su mensaje almacenado. |
| S6-07 Contexto | Se distingue objetivo considerado en la conversación de Contexto confirmado. Se corrige el patrón ambiguo «He registrado tu objetivo…» cuando Contexto está vacío. No se añade escritura desde chat ni se exigen hipótesis para descripción. |
| Etiqueta menor | Los gráficos nuevos usan «Diagrama de caja de puntaje»; no «Comparación» para un único conjunto. No se eliminan advertencias metodológicas necesarias ni se alteran gráficos históricos. |

La respuesta JSON original del primer 502 real no fue proporcionada; no se atribuye
al modelo un contenido que no se observó. Sí se reprodujeron la causa determinista
del alcance y la secuencia 502 → corrección de productos fallida → reintento válido
mediante respuestas simuladas válidas e inválidas para ambos proveedores.

## Pruebas

- **Pytest completo: 562 aprobadas, 25 módulos, cero fallos**, una pasada con
  aislamiento por módulo como CI. Incluye descriptiva, Pearson, integral, T8/T10,
  PDF+CSV, proveedores/historial, RLS simulado y motor/proceso estadístico real.
- Welch literal con Gemini y Terra simulados: una propuesta válida, aceptación,
  preparación y ejecución real. N=15 por A/B/C; medias y DE por grupo, F/p contrastados
  con SciPy; gl del numerador y las referencias numéricas existentes; sin post hoc.
  No se sustituyó por ANOVA clásico ni se inventaron resultados.
- 18 regresiones nuevas backend: corrección válida/fallida, secuencia del fallo
  observado, recuperación del alcance anterior, conservación de solicitudes
  auténticas, registros/paginación/auth, XLSX/JSON, interpretación y T10.
- Vitest completo: **114 de 115 aprobadas en la pasada inicial**. La única prueba
  nueva fallida no esperaba a que cargara la tarjeta; se corrigió esa espera.
  Después, **5/5 en el módulo afectado**. También se aprobaron 27 pruebas dirigidas
  de Datos, Resultados y Markdown. No se repitió toda la suite.
- SQL/PGlite: **5/5 suites aprobadas**, sin Supabase remoto.
- TypeScript, oxlint, Prettier y build: **aprobados** con el código final frontend.
  Calidad Python del repositorio: **59 archivos correctos**; `pip check` aprobado.
- Vista real en navegador aislado con servicios interceptados: 1366×768, 1440×900 y
  390×844; páginas 1–50, 51–100 y 101–123; tablas desplazables, cierre único y ZIP visible;
  cero errores de consola. También se conservaron chat/Markdown/Contexto/diálogo.
- API/Vite finales responden localmente; la nueva ruta sin JWT responde **401**.
  La prueba HTTP con autorización simulada cubre propietario/proyecto incorrectos
  con 404 y límites inválidos con 422. Los originales permanecen intactos.

Los tests usan proveedores y Auth/Storage simulados; no se presentan como una
integración nueva con Gemini o Supabase reales. El motor y sus referencias sí se
calculan localmente. Las advertencias existentes de Starlette/httpx y del chunk
base Vite de unos 501 kB no impiden las comprobaciones.

## Vista de registros y límites

`GET /projects/{project_id}/files/{file_id}/rows?offset=0&limit=50` utiliza el JWT del
usuario, clave publicable y controles de propietario/proyecto; Storage mantiene
RLS. Contrato `FileRows`; respuesta `Cache-Control: no-store`. No utiliza IA.

El navegador no descarga el original ni carga todas las páginas al abrir Datos.
Cada petición explícita relee el objeto privado acotado en el servidor para
consultar registros y contar filas; solo devuelve la página. No se promete un
índice de acceso aleatorio ni rendimiento independiente del tamaño del archivo.
Se reutilizan límites existentes y el semáforo de lectura.

CSV conserva cadenas, espacios, ceros iniciales, vacíos y marcadores como `NA`.
JSON conserva números sin pérdida de precisión y ausencias; XLSX respeta la hoja
seleccionada y muestra fórmulas sin ejecutarlas, con fechas ISO. No se escriben
archivos ni se cambian perfiles, deduplicación, instrumentos o datos históricos.

## Pendientes y riesgos acotados

- Repetir la solicitud literal con Gemini real durante la segunda validación manual.
  No se promete que toda respuesta futura de un modelo sea válida; siguen activos
  los validadores y el máximo de una corrección semántica.
- Verificar «Ver datos» con la cuenta/proyecto sintético de Supabase real. La nueva
  ruta fue probada con Auth/Storage simulados y comparte las protecciones existentes;
  no se accedió a proyectos remotos para esta sesión.
- Si un alcance antiguo tiene historial truncado o evidencia ausente, se conserva
  de forma prudente. No se borra para desbloquear un plan; puede ser necesario
  confirmar el alcance completo o usar una conversación nueva con los mismos archivos.
- Los controles de prosa son finitos, dirigidos a los defectos observados; no son
  una revisión científica universal de cualquier frase.
- JSON debe ser tabular y los archivos deben respetar los límites existentes.
  Por simplicidad, el servidor vuelve a leer el original en cada página.

Las cifras 66.651111 y 11.11057 del CSV manual se consideran evidencia aprobada
por el responsable. No se modificó el motor para ajustarlas ni se sustituyó ese
archivo por la fixture sintética del repositorio.

**Nuevas dependencias: ninguna. Nuevas variables: ninguna. Migraciones: ninguna.**
Sin cambios en `.env`, cuotas de proveedores, configuración Supabase o despliegues.

## Commits nuevos

- `9e4fef0` — alcance/método de Welch, corrección y procedencia/interpretación.
- `322637c` — vista de registros paginada y autenticada.
- `68c7fca` — cierre único de Resultados, caja y regresiones.
- `docs(validacion): registrar evidencia y límites de la sesión 6B` — este informe.

## Validación manual local

Se conservan los servidores de esta rama en frontend **localhost:5173** y backend
**127.0.0.1:8001**, con recarga automática del backend. El Vite verificado usa la API
local 8001. Hay otros procesos locales existentes que no se detuvieron; 8000 estaba
ocupado. No duplicar servidores si los actuales siguen activos.

Si se necesita reiniciarlos, desde la raíz en terminales separadas:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

```powershell
Set-Location frontend
$env:VITE_API_URL = 'http://localhost:8001'
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Abrir `http://localhost:5173`, API `http://localhost:8001/docs`.
CORS fue comprobado para `http://localhost:5173`; usar ese origen, no 127.0.0.1.
La variable anterior solo afecta al proceso, no modifica `.env`. Los servidores
normales mantienen las credenciales existentes: una interacción manual con IA
puede hacer llamadas reales; esta sesión solo hizo pruebas simuladas.

Recorrido sugerido: repetir Welch literal en el chat afectado, comprobar la única
propuesta y sus productos, aceptar y ejecutar; después Datos → Ver datos → avanzar
páginas, y Resultados → abrir → ZIP → único cierre → Atrás. Conservar T8/T10 y los
resultados aprobados. **APTO para esta validación; no autoriza merge ni despliegue.**

## Archivos modificados

- `backend/app/api/chat.py`
- `backend/app/models/chat.py`
- `backend/app/services/conversation.py`
- `backend/app/services/conversation_text.py`
- `backend/app/services/data_preview.py`
- `backend/app/services/gemini.py`
- `backend/app/services/interpretation_guards.py`
- `backend/app/services/plan_capabilities.py`
- `backend/app/services/requested_scope.py`
- `backend/app/services/statistics/catalog.py`
- `backend/app/services/statistics/charts.py`
- `backend/scripts/check_analysis_quality.py`
- `backend/tests/test_session6b.py`
- `docs/ARCHITECTURE.md`
- `docs/SESSION6B_PLAN.md`
- `docs/SESSION6B_REPORT.md`
- `docs/SETUP.md`
- `frontend/src/components/AnalysisResultCard.tsx`
- `frontend/src/components/AnalysisResults.tsx`
- `frontend/src/components/DatasetRows.tsx`
- `frontend/src/components/ProjectData.tsx`
- `frontend/src/components/StatisticalChat.tsx`
- `frontend/src/index.css`
- `frontend/src/lib/chat-text.ts`
- `frontend/src/services/chat.ts`
- `frontend/src/test/session6b.test.tsx`
- `frontend/src/types/chat.ts`
