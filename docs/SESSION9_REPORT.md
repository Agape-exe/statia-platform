# Sesión 09 — Estabilización documental y rediseño UX/UI

Fecha: 21 de noviembre de 2026. Repositorio `Agape-exe/statia-platform`.
Base: `fix/cierre-validacion-tesis`, `71c03d8`, limpia al inicio y con los commits
de las sesiones 07 y 08 incluidos. Rama de entrega:
`fix/estabilizacion-instrumentos-ux-sesion9`. Se utilizó la base solicitada
expresamente, sin actualizar ni desarrollar sobre `develop` o `main`.

**Estado: APTO para validación manual controlada.** Los servicios externos y el
instrumento original del incidente siguen pendientes de validación real. No se
hicieron push, PR, merge, despliegues, cambios remotos ni llamadas reales a proveedores.

## 1. Causas raíz identificadas

- El recuperador exigía encontrar los códigos de la consulta dentro de tokens
  léxicos exactos. Las variantes de presentación con espacios, guiones o guiones
  bajos podían descartar texto que sí se había extraído correctamente. Los casos
  sintéticos iniciales reprodujeron siete fallos de diez comprobaciones nuevas:
  seis de recuperación por variantes de códigos y uno de diagnóstico sin texto.
- La tokenización incluía guiones dentro de las palabras y no normalizaba formas
  equivalentes de códigos. También faltaba normalización de compatibilidad Unicode.
- La selección podía consumir todos los cupos con coincidencias antes de incluir
  las alternativas contiguas. En Word, una tabla puede producir varios fragmentos,
  uno por párrafo/celda; recuperar la pregunta no garantizaba recuperar sus opciones.
- Una búsqueda sin coincidencias y una extracción vacía recibían el mismo mensaje,
  que sugería OCR sin haber demostrado que esa fuera la causa. El retorno estático
  ocurría **antes de invocar al proveedor**; no era un fallo atribuible a Gemini.
- El enrutamiento reconocía únicamente códigos compactos, y el estado de carga de
  instrumentos podía interceptar una consulta por código antes de clasificarla.
- Las consultas documentales/metodológicas se excluían correctamente de la finalidad
  estadística, pero con ello también perdían su título sugerido. Un chat dedicado
  exclusivamente al documento podía seguir como «Nueva conversación».
- El consentimiento estaba alejado del adjunto. El frontend lo transmitía como
  bandera de cada turno; la revisión no encontró evidencia de que el backend
  ignorara una bandera verdadera. Había, en cambio, una experiencia poco visible
  y un mensaje de cambio de proveedor que sugería conservar autorizaciones que
  realmente debían renovarse.

**Límite del diagnóstico:** no se proporcionó el PDF original `SLQ_J.pdf` ni trazas
del turno fallido en este checkout. No se afirma haber reproducido exactamente ese
archivo o identificado su maquetación concreta. Se reprodujeron y corrigieron
causas generales verificables del mismo falso negativo. No se presupone que el
original necesite OCR, ni se lo descargó de una fuente ajena para sustituirlo.

## 2. Corrección de recuperación PDF/DOCX

La extracción real existente conserva texto, fragmentos, ubicaciones y advertencias;
no se reemplazó pypdf ni el lector DOCX seguro. Las regresiones usan PDF y paquetes
DOCX reales generados en memoria, con estructuras educativas, comunitarias,
administrativas y de evaluación, sin documentos de usuarios.

- Búsqueda por palabras, frases tokenizadas, encabezados y códigos.
- Normalización Unicode de compatibilidad, mayúsculas y acentos para búsqueda.
- Equivalencias acotadas de separadores entre prefijos alfabéticos y números,
  incluidos saltos de línea. Se conservan ceros y sufijos: no se aproxima un código
  ausente a otro parecido ni se confunde `R12` con `R120` o `R12A`.
- Prioridad por códigos solicitados y por documentos, seguida de vecindad para
  alternativas, continuaciones y celdas. Los límites globales siguen vigentes.
- Las evidencias compartidas conservan su texto original. El validador admite la
  referencia canónica solo si existe esa evidencia y mantiene la comprobación de
  citas literales y la prohibición de afirmar una lectura completa.
- Ubicaciones DOCX comprensibles: cuerpo, encabezado, pie o notas y párrafo. Las
  rutas XML originales siguen intactas en la metadata histórica; no se presentan
  como fuente habitual del mensaje.
- Diagnósticos distintos para ausencia de instrumentos, falta de autorización,
  extracción vacía y búsqueda sin coincidencias. No encontrar una coincidencia
  no demuestra que el contenido no exista en el original.

## 3. Comportamiento del consentimiento

Al asociar instrumentos sin una decisión vigente aparece una confirmación contextual
con el título solicitado, explicación del uso de fragmentos, proveedor y documentos
afectados. Las acciones son «Permitir consultar fragmentos» y «Continuar sin compartir».
Cerrar el diálogo sin una elección previa equivale a continuar sin compartir.

La elección no se activa automáticamente. Se mantiene en memoria por proyecto,
conversación y proveedor mientras permanezca montado el asistente. No se vuelve a
preguntar en cada mensaje. Añadir un instrumento, cambiar de proveedor, recargar o
salir y volver al asistente requiere una nueva elección. No se añadió persistencia
permanente ni una tabla de permisos.

Una franja junto al compositor muestra «Lectura autorizada» o «Contenido no
compartido» y permite cambiar la elección. Las tarjetas muestran el estado de
extracción informado por el servidor; una autorización no implica que el proveedor
haya leído todo el archivo. La siguiente solicitud lleva la bandera correcta.
Las cargas mixtas no generan comprensión automática antes de resolver la elección.
Autorizar no reenvía ni reintenta mensajes anteriores.

Los reintentos conservan su UUID y payload. Mientras haya uno pendiente se bloquean
los cambios de las opciones de compartición; «Escribir otra solicitud» permite
descartarlo y cambiar opciones para una solicitud nueva. Los mensajes ya compartidos
siguen formando parte del historial, como informa la interfaz.

## 4. Arquitectura y seguridad documental

Flujo: original privado → extracción acotada → fragmentos persistidos con ubicación
→ índice léxico temporal por consulta → selección acotada → contexto del proveedor
autorizado → validación de evidencias → respuesta con fuentes.

No se añadió un índice remoto, embeddings, OCR, infraestructura ni llamadas de red
para recuperar documentos. Se conservan los límites existentes: 80 páginas PDF,
240 000 caracteres y 600 fragmentos de extracción; por turno, diez fragmentos y
12 000 caracteres entre todos los instrumentos. También se conservan los controles
de tamaño, ZIP/XML, recursos externos, objetos activos, cifrado, proceso hijo,
tiempo y memoria. DOC antiguo sigue requiriendo conversión segura.

Los originales y la metadata histórica no se reescriben. El fallback autorizado de
instrumentos antiguos sigue siendo temporal. Storage continúa privado; Auth, JWT
del usuario, clave publicable, RLS y aislamiento no se modificaron. No se ejecutan
macros, código ni instrucciones incrustadas; no se descargan recursos externos.

## 5. Nueva identidad visual

La identidad cambia globalmente de verde a índigo, lavanda y gris perla mediante
tokens CSS. Abarca login, registro, dashboard, proyectos, navegación, formularios,
diálogos, Contexto, Datos, chat, propuestas y Resultados. Se conserva el icono de
marca existente, con nueva aplicación de color. No hay biblioteca visual nueva.

Las superficies son claras, las sombras discretas y los paneles más compactos.
El verde queda para estados de éxito/confirmación; rojo y ámbar conservan sus usos
semánticos. Las notas informativas usan índigo suave y texto explícito.

## 6. Paleta y tokens definitivos

| Token | Valor | Uso |
| --- | --- | --- |
| `--primary` | `#4F46E5` | Acciones y marca |
| `--primary-strong` | `#3730A3` | Hover y texto de énfasis |
| `--lavender` | `#8B5CF6` | Acentos y foco |
| `--lavender-strong` | `#6D28D9` | Marca y acentos legibles |
| `--lavender-soft` | `#DDD6FE` | Contraste en acceso oscuro |
| `--surface-lavender` | `#F5F3FF` | Franja de autorización |
| `--surface-soft` | `#EEF2FF` | Mensajes del usuario y selección |
| `--canvas` | `#F8FAFC` | Fondo |
| `--surface` | `#FFFFFF` | Tarjetas |
| `--ink` | `#1E293B` | Texto principal |
| `--muted` | `#5F6E85` | Texto secundario accesible |
| `--border` | `#E2E8F0` | Bordes |
| `--border-strong` | `#C7D2FE` | Selección y controles |
| `--success` | `#166534` | Éxito |
| `--danger` | `#B91C1C` | Error/peligro |
| `--warning` | `#92400E` | Advertencia |
| `--auth-bg` | `#242052` | Superficie oscura de acceso |

Radios reutilizables de 8/12/16 px, escala de espacio 4/8/12/16/24/32 px y dos
sombras compartidas. La tipografía conserva Segoe UI/system-ui, sin descargas de
fuentes. El gris secundario propuesto se ajustó: `#64748B` sobre `#EEF2FF` daba
4,26:1; `#5F6E85` da 4,63:1. Principal sobre blanco: 6,29:1. Estas comprobaciones
puntuales no constituyen una certificación completa WCAG.

## 7. Mejoras del chat

- Tres zonas en escritorio; historial temporal/plegable en tablet y móvil.
- Encabezado compacto, proveedor visible y acciones con etiquetas accesibles.
- Mensajes con ancho ajustado al contenido, identidad del autor y tratamiento
  diferente de eventos del sistema, advertencias y errores.
- «Información del sistema» sustituye la etiqueta técnica de acción determinista.
  Un mensaje histórico sin proveedor acreditado se presenta como Statia; nunca se
  atribuye al proveedor seleccionado actualmente. El modelo acreditado permanece
  en metadata y en la información emergente de procedencia.
- Compositor accesible, textarea ajustable, adjunto visible, estado de procesamiento,
  Enter/Shift+Enter/IME e idempotencia conservados.
- Distinción visible de formatos de instrumentos y datasets. Archivos asociados
  abiertos inicialmente, con tarjetas compactas y detalles/descarga expandibles.
- Títulos derivados de nuevas consultas documentales cuando el nombre sigue siendo
  provisional. No hay renombrado masivo ni modificación de títulos manuales.

## 8. Propuestas, resultados y gráficos

Las propuestas mantienen objetivo, procedimiento y justificación visibles; dataset,
variables, supuestos, limitaciones y productos quedan en secciones revisables. La
aceptación/rechazo conserva sus servicios y validaciones. Los planes aceptados se
pueden desplegar, sin ejecutar automáticamente.

Resultados usa nombres legibles de métodos, tablas con desplazamiento propio,
advertencias abiertas cuando existen y metadatos técnicos plegables. Se evita repetir
el resultado seleccionado en el listado y se conservan los anuncios accesibles de
estado. Las rutas de imágenes se sustituyen por títulos del procedimiento y número
de gráfico; siguen disponibles en la trazabilidad técnica.

«Ampliar gráfico» abre el mismo blob privado original, con desplazamiento por teclado
y tamaño nativo. No descarga otra copia, no llama a ejecución ni recalcula. La prueba
de regresión verifica una consulta al artefacto, ausencia de ejecución e inmutabilidad
del resultado. Los PNG históricos mantienen sus colores, ejes, categorías y orden;
una imagen rasterizada con etiquetas largas no puede remaquetarse solo con CSS.

No se alteraron los cálculos, denominadores, valores presentes, ausencias físicas ni
categorías sustantivas/no sustantivas. La clasificación semántica optativa de Sesión 08
continúa sin aplicar reglas universales a textos como Unknown o None.

## 9. Navegación, responsive y revisión visual

Se reutilizaron Vite en `localhost:5173` y API en `127.0.0.1:8001`, que ya estaban
activos; no se interrumpieron ni duplicaron. `/health` respondió 200.

Se inspeccionó la aplicación mediante navegador local, con los componentes reales
y servicios sintéticos aislados de `frontend/visual/index.html`. La entrada bloquea
fetch de servicios; solo permite explícitamente leer el PNG sintético local para
presentarlo como artefacto. No usa una sesión real ni datos de investigadores y no
se incluye en el build público. Su banner identifica siempre la simulación.

| Tamaño | Revisión realizada |
| --- | --- |
| 1440 × 900 | Acceso, dashboard, formulario de proyecto, chat de tres zonas y consentimiento |
| 1280 × 800 | Chat, mensajes, propuesta/plan aceptado, Contexto y Resultados |
| 820 × 1180 | Contexto, Datos y chat con historial oculto, compositor y navegación |
| 390 × 844 | Dashboard, registro, chat, consentimiento, plan aceptado, Contexto, tablas y gráfico ampliado |

Iteraciones verificadas: reducción del encabezado móvil, eliminación de títulos
repetidos, texto secundario con mayor contraste, navegación móvil compacta también
fuera del chat y tarjeta de revisión confirmada de Contexto con ayuda secundaria
plegable. Sus controles de edición, revisión, importación y conflictos se preservan.

La revisión encontró que una tabla de 600 px ampliaba toda la página móvil hasta
655 px. Se corrigió el mínimo intrínseco del grid de Resultados. Comprobación final:
viewport 390 px, página 375 px (descontando scrollbar), tabla visible 300 px y contenido
600 px con scroll interno. En chat móvil: página 390 px y borde inferior del compositor
837,2 px dentro de 844 px. En tablet: página 820 px y compositor dentro de 1180 px.

Capturas sintéticas locales, excluidas de Git en `.local/session9/`: `chat-desktop.jpg`,
`chat-laptop.jpg`, `chat-tablet.jpg`, `chat-mobile.jpg`, `plan-aceptado.jpg`,
`datos-tablet.jpg`, `contexto-mobile.jpg`, `resultados-mobile.jpg`, `login-desktop.jpg`.
La figura sintética versionada se generó con el módulo Charts existente, sin cambiarlo.
Se comprobó igualdad binaria entre workspace e índice Git; `.gitattributes` evita
que normalizar saltos de línea corrompa su firma PNG en otros checkouts.

No se probó un teléfono físico, teclado virtual real, lector de pantalla, Safari o
Firefox. La revisión responsive fue en viewports de un navegador de escritorio.

## 10. Archivos modificados

```text
.gitattributes
.gitignore
backend/app/services/conversation.py
backend/app/services/instrument_context.py
backend/tests/test_instruments.py
backend/tests/test_thesis_stability.py
docs/ARCHITECTURE.md
docs/SESSION9_PLAN.md
docs/SESSION9_REPORT.md
docs/SETUP.md
frontend/src/components/AnalysisResultCard.tsx
frontend/src/components/AnalysisResults.tsx
frontend/src/components/AssistantProviderSelector.tsx
frontend/src/components/ChatComposer.tsx
frontend/src/components/ComponentStates.tsx
frontend/src/components/DatasetCard.tsx
frontend/src/components/InstrumentAccess.tsx
frontend/src/components/ProposalCard.tsx
frontend/src/components/StatisticalChat.tsx
frontend/src/components/ThesisContext.tsx
frontend/src/index.css
frontend/src/lib/analysis-methods.ts
frontend/src/lib/assistant-provider.ts
frontend/src/lib/instrument.ts
frontend/src/pages/AuthPage.tsx
frontend/src/pages/Workspace.tsx
frontend/src/test/analysis.test.tsx
frontend/src/test/chat.test.tsx
frontend/src/test/fixtures/frequencies.synthetic.png
frontend/src/test/providers.test.tsx
frontend/src/test/visual-preview.tsx
frontend/visual/index.html
```

## 11. Commits locales

- `5eb2616` — `docs(sesion09): registrar plan de estabilización y alcance`.
- `f0be1dc` — `fix(instrumentos): recuperar referencias equivalentes y diferenciar diagnósticos`.
- `c2a7ac0` — `feat(interfaz): renovar identidad y aclarar el flujo documental`.
- `docs(sesion09): documentar validaciones y límites de la entrega` — commit final
  de este informe; su hash se consulta con `git log -1 --oneline`.

Identidad Git existente, sin coautores artificiales. Todos son locales. Árbol Git
limpio verificado después del commit de cierre; evidencia de pruebas y capturas
permanece ignorada, sin incorporarse al historial.

## 12. Pruebas aprobadas

| Comprobación | Resultado |
| --- | --- |
| Backend general en 29 procesos aislados | 647 aprobadas, 1 omitida, 0 fallidas |
| Regresión documental/API final | 67 aprobadas: 34 instrumentos, 21 tesis y 12 chat |
| Backend consolidado final | **650 aprobadas, 1 omitida**, sin fallos pendientes |
| Frontend general, 12 archivos | **130 aprobadas** |
| Revalidación posterior de acceso/proveedores | 48 aprobadas |
| Revalidación del último ajuste visual de Contexto | 9 aprobadas |
| PostgreSQL/PGlite local | **6 suites aprobadas**: proyectos, chat, proveedores, resultados, Contexto y DOCX |
| Configuración de producción frontend | 2 aprobadas |
| TypeScript estricto, oxlint, Prettier y build | Aprobados al cierre; incluye la entrada sintética y su HTML en las comprobaciones aplicables |
| Calidad Python | Lint y formato aprobados, 70 archivos; lint adicional de conversación aprobado |
| `pip check` | Sin dependencias rotas |
| Diff/secretos | Sin errores de whitespace ni patrones de claves/JWT/llaves privadas en líneas añadidas |
| Inmutabilidad de alcance | Sin diff en motor estadístico, migraciones, lockfiles, requisitos o entornos |
| Aislamiento de revisión visual | Sin entrada, textos de simulación ni fixtures sintéticas en `dist` |

El consolidado backend sustituye únicamente las 31 pruebas iniciales de instrumentos
por su revisión final de 34 tras añadir Unicode/tablas y códigos partidos en línea.
La última regresión de 67 también revalida el enrutamiento, títulos y diagnósticos.
No se presenta como una segunda pasada general completa. Las pruebas estadísticas
existentes ejecutaron el motor Python real con datos sintéticos: descriptivos,
correlaciones, Welch e integrales; los proveedores/Auth/Storage de los recorridos
HTTP son simulados. PGlite emula Auth/Storage localmente; no valida Supabase remoto.

Cobertura nueva: códigos equivalentes en ambos formatos, acentos/palabras, búsqueda
sin coincidencias, ausencia de texto, identificadores cercanos no equivalentes,
Unicode de ancho completo, salto de línea y tabla Word con seis opciones separadas.
Se conserva la cobertura de multipágina, preguntas tardías, múltiples instrumentos,
archivos dañados/cifrados, ZIP/XML inseguros y contenido malicioso como dato.

La primera prueba frontend posterior al cambio del selector requería el nombre
técnico del modelo dentro de la opción. Se actualizó al diseño compacto conservando
la prueba de procedencia acreditada. Los errores intermedios de tipado/formato y
la aserción que confundía recurso técnico oculto con recurso eliminado se corrigieron;
no se dejaron comprobaciones fallidas ni se ocultó trazabilidad para pasar pruebas.

## 13. Pruebas omitidas

Una omisión heredada: `test_legacy_a_d_bytes_and_converter_unchanged_without_import_or_execution`
de `test_terra_diagnostic.py`, por ausencia del archivo local no versionado
`backend/test_terra_statia_env.py`. No se inventó ni regeneró esa evidencia.

Por restricción expresa no se ejecutaron proveedores reales, Supabase remoto,
migraciones remotas, despliegues o pruebas en Render/Vercel. Tampoco se usaron
instrumentos o datasets reales de investigadores. No se ejecutó producción con
credenciales de despliegue ni se intentó autenticar una cuenta desde el navegador.

## 14. Regresiones y validaciones pendientes

Sin regresiones conocidas de alta gravedad al cierre. Quedan la validación del PDF
original, otros documentos reales con maquetación compleja, respuestas reales de
ambos proveedores, aislamiento con dos cuentas reales y dispositivos/navegadores
adicionales. El desbordamiento visual detectado se corrigió y volvió a inspeccionarse.

## 15. Dependencias nuevas

Ninguna. Manifiestos y lockfiles sin cambios. Se reutilizan bibliotecas existentes,
incluidos pypdf, defusedxml, React, iconos y Matplotlib para la fixture sintética.

## 16. Migraciones nuevas

Ninguna. No se modificó ni ejecutó la migración 009. Según el usuario, ya fue aplicada
manualmente al Supabase de validación. Antes de futuros despliegues se debe conciliar
ese hecho con el historial de migraciones y comprobar el destino. No se presenta
esa confirmación del usuario como una inspección remota de esta sesión.

## 17. Variables de entorno nuevas

Ninguna. No se leyeron valores secretos para mostrarlos ni se modificaron credenciales
o archivos de entorno. No hay claves administrativas nuevas ni uso de `service_role`.

## 18. Riesgos y limitaciones conocidos

- La búsqueda es léxica y acotada: no traduce conceptos entre idiomas, no resuelve
  sinónimos arbitrarios ni interpreta texto de imágenes. Una referencia fuera de
  los límites de extracción o compartición puede no recuperarse.
- La normalización de separadores permite buscar variantes de presentación; la
  identidad semántica de ítems con convenciones ambiguas debe contrastarse con sus
  fragmentos y el original. No se infieren correspondencias con columnas del dataset.
- La extracción PDF puede perder orden de tablas/columnas. Word conserva ubicaciones
  por parte/párrafo, no páginas estables ni numeración automática fiable.
- El consentimiento no es permanente: volver a montar el asistente requiere elegir
  de nuevo. Una revocación limita turnos futuros, no retira información ya compartida.
- Los gráficos históricos son imágenes inmutables; la ampliación facilita leerlos,
  pero no corrige su maquetación ni cambia categorías. No se regeneraron resultados.
- Persisten avisos existentes de Starlette/TestClient y del chunk base Vite de
  aproximadamente 500,98 kB. No se alteró el empaquetado para silenciar el aviso.
- Las capturas prueban presentación local con simulaciones identificadas; no son
  evidencia de Gemini, Terra, Auth o Storage reales ni una auditoría WCAG completa.

## 19. Comandos locales

Reutilizar servidores si ya están activos. Desde la raíz, en terminales separadas:

```powershell
Set-Location backend
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8001
```

```powershell
Set-Location frontend
npm run dev
```

Comprobaciones desde `backend`:

```powershell
.\.venv\Scripts\python -m pytest tests/test_instruments.py tests/test_thesis_stability.py tests/test_chat_api.py -q
.\.venv\Scripts\python scripts/check_analysis_quality.py
.\.venv\Scripts\python -m pip check
```

Desde `frontend`: `npm test`, `npm run typecheck`, `npm run lint`,
`npm run format:check`, `npm run build`, `npm run test:deployment` y
`npx prettier --check visual/index.html`. Desde `supabase`: `npm test` solo ejecuta
las suites locales PGlite. No ejecutar scripts diagnósticos con `--live`.

Vista sintética local: `http://localhost:5173/visual/index.html?screen=dashboard`;
también admite `asistente`, `contexto`, `datos`, `resultados`, `login`, `registro`.
No usar esa entrada para datos reales ni confundirla con la aplicación autenticada.

## 20. Plan de validación manual con instrumentos reales

1. En el entorno autorizado, confirmar que 009 y el historial de migraciones están
   conciliados. No volver a ejecutarla automáticamente. Verificar bucket privado.
2. Abrir un proyecto de tesis con Contexto confirmado y otro General. Confirmar
   revisión, edición, deshacer, revisión antes de guardar e importación JSON. En
   dos pestañas provocar un conflicto y verificar que se conserva el borrador.
3. Asociar el PDF original del incidente y consultar sus códigos/preguntas sin
   autorizar. Verificar ausencia de contenido enviado y diagnóstico de permiso.
   Autorizar, enviar una consulta nueva y contrastar preguntas, alternativas y
   páginas con el original. No considerar aprobada esa comprobación todavía.
4. Repetir con DOCX de otra disciplina, párrafos y tablas, y PDF largo/multipágina.
   Consultar encabezados, frases y referencias con separadores; probar también
   un código inexistente, documento sin texto y extracción parcial. Distinguir
   los tres diagnósticos y comprobar que no se inventan opciones ni citas.
5. Descargar originales y contrastar sus hashes. Probar carga mixta de instrumento
   y CSV/XLSX/JSON; confirmar roles, elección de permiso, perfil y advertencias.
   En Excel recorrer hojas sin cambiar la hoja congelada del plan.
6. Cambiar proveedor y volver a autorizar; revocar y enviar otra consulta. Conservar
   mensajes, revisar metadatos y comprobar el UUID/payload en reintentos. No debe
   aparecer un mensaje duplicado ni reenviarse una consulta al pulsar autorizar.
7. Con autorización específica futura, validar Gemini y Terra reales por separado:
   confirmar que reciben fragmentos verificables, sus fuentes y el Contexto vigente.
   Registrar los fallos reales sin sustituirlos por respuestas simuladas.
8. Revisar/aceptar un descriptivo, una correlación y ANOVA de Welch sin cambiar la
   semántica del plan. Ejecutar solo tras confirmar decisiones; cotejar tablas,
   supuestos, denominadores, PNG y ZIP. Abrir resultados previos sin recalcularlos.
9. Con dos usuarios reales, verificar RLS y acceso a proyectos, conversaciones,
   perfiles, originales y artefactos. No usar credenciales administrativas.
10. Repetir el recorrido autenticado en escritorio, tablet y teléfono, con teclado,
    mensajes largos, tablas anchas, ampliación de gráficos y teclado virtual. Revisar
    lector de pantalla y navegadores adicionales antes de certificar accesibilidad.

## 21. Estado final

**APTO para validación manual controlada**, con las limitaciones externas descritas.
Recuperación generalizable, consentimiento contextual, identidad global y revisión
visual local implementados; motor estadístico, resultados históricos, originales,
seguridad y lógica multihoja conservados. No equivale a aprobación con archivos reales
o proveedores reales y no autoriza merge, push ni despliegue.
