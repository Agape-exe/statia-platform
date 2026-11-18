# Sesión 6: corrección consolidada y validación local

Fecha: 18 de noviembre de 2026. Rama: `fix/correcciones-validacion-sesion6`.
Base: `origin/develop` actualizado, `1ac0983b768953b7b5b1bc477a6b59b031c6d216`.

**APTO para validación manual local.** No equivale a aprobación de producción ni
a autorización de merge. No hubo push, PR, merge, despliegue, migración remota,
cambio de proyectos reales ni llamadas reales a Gemini/Terra.

## Causas raíz y correcciones

- **Alcance:** el reconocedor consumía etiquetas literales y trataba el resto de la
  prosa como incertidumbre. Ahora reconoce descriptiva, medidas, Pearson y ANOVA;
  separa negaciones y conserva productos/exclusiones. Una aclaración inequívoca
  («quiero solo descriptiva global…») puede resolver una ambigüedad sin una frase
  del catálogo. No se acreditan productos que el componente no pueda ejecutar.
- **Validación metodológica:** un `output_scope` del proveedor saltaba directamente
  a preguntar al usuario. Ahora recibe la única corrección semántica autorizada.
  Tesis rechazaba también preguntas opcionales junto a propuestas aun con
  `clarification_required=false`; se conserva el bloqueo de preguntas esenciales.
  No se desactivaron validadores. Errores genuinos siguen impidiendo persistir planes.
- **Welch:** `comparison` es deliberadamente un contrato de dos grupos. Las
  instrucciones ahora explicitan `comparison=null` para ANOVA global y sus
  productos reales. Se conserva la exclusión de post hoc en el plan y se impide
  activarlos desde opciones avanzadas. No se ampliaron métodos ni cambiaron fórmulas.
- **Tipos ambiguos:** el perfil prudente se conserva. El investigador puede escribir
  ``Confirmo que `horas_estudio` es cuantitativa discreta`` (o `continua`). El servidor
  guarda una decisión por archivo/hoja/columna en el plan, la revalida al aceptar y
  al releer originales, y exige conservarla al ejecutar. No modifica perfiles,
  originales, unidades ni planes históricos. Si la columna está en varios archivos,
  pide desambiguar; una alternativa segura es reutilizar solo el archivo pertinente
  en otro chat. Identificadores y fechas no pueden convertirse por esta vía.
- **Datos:** módulo funcional con catálogo de todo el proyecto, rol/formato/tamaño,
  metadatos, perfil bajo demanda, texto PDF y descarga privada. Deduplicación visual
  por ID; archivos distintos del mismo nombre permanecen separados.
- **Interfaz:** Markdown/GFM con react-markdown y remark-gfm, sin HTML ejecutable,
  enlaces permitidos, código y tablas desplazables. Estados según la etapa, la
  preparación y la aceptación vigente; el resultado histórico conserva su estado.
  Botones de detalle abren/ocultan y respetan URL. La comprensión repetida se nombra
  explícitamente. Éxito JSON junto al importador, borrador separado de guardado y
  conflicto HTTP 409 referido a la versión guardada del Contexto.
- **Supuestos:** la procedencia distingue declaración del investigador, verificación
  automática y pendientes. Los resultados nuevos tienen origen opcional; no se
  reetiquetan resultados antiguos. Un integral exclusivamente descriptivo no recibe
  un ajuste de multiplicidad inferencial. Los mixtos conservan el comportamiento validado.
- **Cuota:** cada solicitud HTTP emitida consume la reserva, incluidas correcciones
  semánticas y reintentos ya existentes del SDK. Los rechazos locales no consumen
  otra reserva. Gemini y Terra tienen ventanas distintas, compartidas por proveedor
  dentro del proceso y reiniciadas al reiniciar ese proceso. Un turno ya completado
  se reproduce sin otra generación; reintentar uno fallido puede emitir solicitudes
  nuevas y no elude la ventana por minuto. Solo esta ventana proporciona
  `Retry-After` calculado y texto de espera al frontend. Se mantiene el código
  público de error; el máximo por turno no inventa un tiempo de espera. Sin nuevas
  cuotas, esperas bloqueantes ni reintentos pagados automáticos.

## Evidencia local y límites

| Comprobación | Resultado |
| --- | --- |
| Backend completo, una ejecución | 543 casos: 539 aprobados y 4 fallos iniciales |
| Corrección de esos fallos y módulos afectados | 233/233 aprobados; seis módulos, sin repetir toda la suite |
| Aserciones finales Welch/T10/aclaración | 4/4 aprobadas |
| Último ajuste de contexto, tipos y PDF | 5/5 aprobadas |
| Vitest completo | 109/109 aprobadas |
| Vitest tras último ajuste de estado/CSS | 30/30 aprobadas, incluye un caso nuevo |
| SQL/PGlite | 5/5 suites aprobadas, sin Supabase remoto |
| TypeScript, oxlint, Prettier, build | Aprobados después del último cambio frontend |
| Calidad Python del repositorio y pip check | Aprobados; 56 archivos con formato correcto |
| Diff y patrones de secretos | Sin errores de whitespace ni credenciales detectadas |
| Fórmulas numéricas y generador de gráficos | Sin cambios |
| FastAPI y Vite | Iniciados localmente; health y HTML responden 200 |
| Escritorio 1366×768 / 1440×900 y móvil 390×844 | Chat, Markdown, carga, Datos, Contexto, diálogo y Resultados comprobados; cero errores de consola |

Los cuatro fallos iniciales fueron: compatibilidad del código de cuota; una clave
vacía innecesaria en estado conversacional; conservación de Holm en integrales
mixtos; y una auditoría histórica que comparaba su payload con el prompt actual.
Se corrigieron y se verificaron en los módulos afectados. La auditoría usa el
prompt histórico congelado: no se reescribieron evidencia, hashes ni planes reales.

La revisión visual ejecutó la interfaz real en Edge/Playwright con sesión, Auth y
respuestas HTTP sintéticas interceptadas. No equivale a una sesión Supabase real.
Las capturas y el resultado JSON quedan en la carpeta local de visualizaciones de
esta conversación. El perfil de Datos en móvil tiene desplazamiento horizontal
interno, sin ensanchar la página. Las pruebas HTTP de backend usan Auth/Storage
simulados y el motor Python/proceso real.

El build avisa de un chunk base de unos 501 kB. No bloquea la compilación; no se
hizo una reorganización de bundles antes de la presentación. Pytest informa la
advertencia de deprecación existente de Starlette/httpx.

## Casos obligatorios

- **A–E, Gemini y Terra simulados:** solicitudes naturales de descriptiva global,
  Pearson, ANOVA Welch, integral descriptiva+Pearson y descriptiva de tesis producen
  planes aceptables sin «Confirmo alcance». Se prueba aceptación, preparación,
  decisiones explícitas, ejecución, recursos persistidos e interpretación posterior.
- **Welch:** 45 registros sintéticos, A/B/C con 15 por grupo, sin post hoc. Se
  verifican N, medias y DE por grupo, F y p contra SciPy (`equal_var=False`) y gl
  del numerador. La suite numérica conserva además la referencia racional de gl
  de Welch. No se tocaron las fórmulas.
- **T8:** Contexto vigente revisión 2 y objetivo exclusivamente descriptivo;
  propuesta, aceptación, ejecución sin intervalos/pruebas e interpretación del
  resultado guardado, sin modificar cifras ni Contexto. Se comprueba que el
  proveedor recibe resultados guardados y el Contexto vigente.
- **T10:** Contexto ausente válido; se puede iniciar, pedir objetivo general y
  conservar información conversacional sin crear hipótesis, diseño ni documento
  Contexto. Se invita a revisarlo y confirmarlo en su módulo. No se añadió guardado
  desde chat.
- **PDF:** instrumento sintético de una página con texto, rol `instrument`,
  continuación a CSV, ambos asociados y reutilizables. Los extractos se comparten
  solo con decisión explícita. Rechazos de DOCX, PDF inválido, cifrado y PDF usado
  como dataset. PDF sin texto conservado, con aviso y sin OCR. Instrumento renderizado
  y revisado visualmente. No se añadió Word ni se ampliaron límites.

El archivo `statia_sesion6_datos_sinteticos.csv` del encargo no estaba adjunto ni en
el repositorio. **Pendiente** contrastar sus valores exactos: media 66.651111,
DE 11.11057, r≈0.13097 y p≈0.39114. La fixture nueva `regresion_sesion6.csv` es
independiente y no se presenta como ese original. Las referencias existentes de
Pearson, descriptiva y Welch siguen verificadas mediante la suite numérica.

## Datos y deduplicación

Las cargas nuevas guardan `metadata.content_sha256`. Dentro del mismo proyecto,
rol y formato, igual contenido reutiliza ID/objeto y solo añade el vínculo que
falte. Mismo nombre con bytes diferentes crea otro archivo. Un lock serializa
cargas dentro de un proceso. No hay garantía atómica entre procesos sin una
restricción de base de datos; **no se propone migración para esta sesión**.

Históricos sin hash se conservan íntegros y no se compactan. XLSX ya perfilados
pueden crear otra referencia para permitir elegir otra hoja sin cambiar el perfil
congelado. No se deduplica por nombre ni entre proyectos. La API conserva JWT,
clave publicable y RLS; pruebas SQL/PGlite cubren aislamiento e integridad.

## Arranque Windows/PowerShell

No hay variables nuevas, migraciones ni cambios de secretos. Se comprobó que
frontend y backend usan el mismo Supabase y clave publicable, y que CORS admite
`http://localhost:5173`. La variable frontend guardada apuntaba a otra API; se
sobrescribe únicamente para el proceso local.

El puerto 8000 estaba ocupado por otro servicio que se conservó. Para esta rama
se dejó FastAPI en **8001** y Vite en **5173**. En terminales separadas, desde la raíz:

```powershell
Set-Location backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8001
```

```powershell
Set-Location frontend
$env:VITE_API_URL = 'http://localhost:8001'
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

Abrir `http://localhost:5173`; API `http://localhost:8001/docs` y
`http://localhost:8001/health`. Si 8000 queda libre, cambiar ambos puertos API a
8000. No duplicar servidores mientras los dejados en ejecución sigan activos.
Si faltan dependencias en otro checkout: `npm ci` en frontend y Supabase;
`.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt` en backend
(Python 3.12). Mantener los `.env` existentes sin imprimirlos ni versionarlos.

Los servidores normales usan las credenciales existentes. Una interacción manual
con IA puede realizar llamadas reales; para comprobar sin consumo usar las
pruebas simuladas. No se ejecutaron diagnósticos `--live` en esta sesión.

Para repetir el backend completo, preferir el aislamiento por módulo que ya usa CI:

```powershell
Set-Location backend
Get-ChildItem tests/test_*.py | ForEach-Object {
  & .\.venv\Scripts\python.exe -m pytest -q $_.FullName
  if ($LASTEXITCODE -ne 0) { throw "Falló $($_.Name)" }
}
```

## Pendientes y riesgos

- Validación manual con cuentas/proyectos sintéticos en Supabase real, incluyendo
  Storage y RLS remoto. PGlite y dobles no sustituyen esa integración.
- Repetir A–E/T8 con proveedores reales solo en otra sesión autorizada. Los tests
  de Gemini/Terra validan contrato/transporte y flujo; no certifican la respuesta
  futura de un modelo remoto. Persisten los validadores y el fallo explícito.
- Contrastar el CSV original mencionado y sus cifras conocidas cuando esté disponible.
- Deduplicación concurrente entre procesos y compactación de históricos siguen
  fuera de alcance; se mantienen las alternativas seguras descritas.
- El reconocimiento es finito: productos desconocidos, restricciones contradictorias
  o métodos no ejecutables siguen necesitando aclaración. No se reduce el alcance
  automáticamente para aparentar una propuesta válida.

## Commits locales

- `4a900ab` — planificación y metodología.
- `03d78c4` — cargas y deduplicación.
- `bc6ee82` — instrumentos y regresiones sintéticas.
- `89f3d86` — interfaz, Datos, Markdown, Contexto y supuestos.
- `ba18fa5` — conservación de fixtures y presupuesto de contexto de decisiones.
- `docs(validacion): documentar correcciones y evidencia local de sesión 6` — commit
  de este informe; obtener su hash con `git log -1 --oneline`.

Se conservaron los metadatos Git configurados, sin coautores añadidos.

## Archivos modificados

- `.gitattributes`
- `backend/app/api/chat.py`
- `backend/app/api/research_context.py`
- `backend/app/main.py`
- `backend/app/models/analysis.py`
- `backend/app/models/chat.py`
- `backend/app/services/conversation.py`
- `backend/app/services/gemini.py`
- `backend/app/services/plan_capabilities.py`
- `backend/app/services/provider_runtime.py`
- `backend/app/services/requested_scope.py`
- `backend/app/services/statistics/automatic.py`
- `backend/app/services/statistics/preparation.py`
- `backend/app/services/statistics/procedures.py`
- `backend/app/services/variable_types.py`
- `backend/scripts/check_analysis_quality.py`
- `backend/tests/fixtures/README.md`
- `backend/tests/fixtures/instrumento_sesion6.pdf`
- `backend/tests/fixtures/regresion_sesion6.csv`
- `backend/tests/fixtures/session5_system.txt`
- `backend/tests/test_chat_api.py`
- `backend/tests/test_requested_scope.py`
- `backend/tests/test_session6.py`
- `backend/tests/test_terra_diagnostic.py`
- `docs/ARCHITECTURE.md`
- `docs/SESSION6_PLAN.md`
- `docs/SESSION6_REPORT.md`
- `docs/SETUP.md`
- `frontend/package-lock.json`
- `frontend/package.json`
- `frontend/src/components/AnalysisResultCard.tsx`
- `frontend/src/components/AnalysisResults.tsx`
- `frontend/src/components/ChatMarkdown.tsx`
- `frontend/src/components/DatasetCard.tsx`
- `frontend/src/components/ExecutionPreparationCard.tsx`
- `frontend/src/components/ProjectData.tsx`
- `frontend/src/components/ProposalCard.tsx`
- `frontend/src/components/StatisticalChat.tsx`
- `frontend/src/components/ThesisContext.tsx`
- `frontend/src/index.css`
- `frontend/src/pages/Workspace.tsx`
- `frontend/src/services/chat.ts`
- `frontend/src/test/chat.test.tsx`
- `frontend/src/test/research-context.test.tsx`
- `frontend/src/test/session6.test.tsx`
- `frontend/src/types/analysis.ts`
- `frontend/src/types/chat.ts`
