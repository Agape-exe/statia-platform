# Configuración local

Sesión 09: [estabilización documental y rediseño](SESSION9_REPORT.md). Sin nuevas
dependencias, migraciones ni variables. Reiniciar API y Vite si no están en modo
recarga. El consentimiento aparece al asociar instrumentos y se modifica junto al
compositor; no se activa automáticamente. Se solicita de nuevo al añadir instrumentos,
cambiar proveedor o recargar/salir del asistente. La elección solo afecta a turnos futuros.

Para inspeccionar el diseño sin sesión remota, abrir con Vite activo
`http://localhost:5173/visual/index.html?screen=dashboard`. La misma entrada admite
`screen=asistente`, `contexto`, `datos`, `resultados`, `login` o `registro`. Usa componentes
reales con fixtures sintéticas, bloquea llamadas de red y no forma parte de `dist`.
No valida proveedores, RLS o persistencia remotos. No usarla para datos reales.

**Migración 009:** el usuario confirma que ya se aplicó manualmente en el Supabase
de validación. No se vuelve a ejecutar durante esta sesión; se conserva el archivo.
Antes de futuros despliegues debe conciliarse con el historial de migraciones y
verificarse el entorno de destino. Esto actualiza el requisito pendiente descrito
históricamente en la Sesión 08; no es una comprobación remota realizada aquí.

Sesión 6B: ver [Welch, vista de registros y validación final](SESSION6B_REPORT.md).
Sin variables nuevas, migraciones ni cambios de configuración remota.

Sesión 6: ver [correcciones, pruebas y arranque local](SESSION6_REPORT.md). No requiere
variables nuevas ni migraciones. Los comandos permiten sobrescribir VITE_API_URL solo
en el proceso, sin editar secretos. No ejecutar diagnósticos con `--live` para esta validación.

Sesión 5B: el [selector multiproveedor frontend](MULTIPROVIDER_FRONTEND.md) consulta
la disponibilidad al backend y confirma el destinatario antes del cambio. No requiere
nuevas variables frontend ni migraciones. Gemini conserva la creación rápida; Terra
solo se selecciona si el catálogo lo habilita y configura. No colocar claves ni
habilitación OpenAI/Terra en `VITE_*`; el control de producción las rechaza.

Corrección focalizada P1 del PR #7: [productos inferenciales y conservación del alcance](PR07_P1_REPORT.md).
No requiere nuevas migraciones ni habilita proveedores.

Sesión 5A: consultar [backend multiproveedor](MULTIPROVIDER_BACKEND.md) para la migración
aditiva 007 y su corrección obligatoria 008, configuración experimental OpenAI y contrato del futuro selector. Gemini
conserva el valor predeterminado; Terra requiere habilitación explícita y la protección 008. Ver [instalación y recuperación manual](PR07_SAFE_ROLLOUT.md).

Sesión 04: aplicar únicamente la migración aditiva 006 si aún no está instalada para habilitar [Contexto de tesis](THESIS_CONTEXT.md). La preparación y publicación manual de backend/frontend, variables de producción y Auth se explican en [DEPLOYMENT](DEPLOYMENT.md). Conservar el acceso local; no repetir 001–005 ya aplicadas.

Actualización integral: aplicar `202611160005_chat_timeline.sql` después de 001–004 y reiniciar API/Vite. No modificar ni repetir migraciones ya aplicadas. El recorrido parcial, continuación y validaciones pendientes se explica en [INTEGRAL_EXECUTION](INTEGRAL_EXECUTION.md).

## 1. Supabase

En el proyecto existente abre **SQL Editor**, crea una consulta, pega el contenido completo de `supabase/migrations/202611150001_projects.sql` y ejecútalo una vez. Se usa una transacción para evitar una instalación parcial. No ejecutar de nuevo una migración ya aplicada: creará conflicto porque los objetos ya existen.

Alternativa con la CLI oficial de Supabase instalada: desde la raíz ejecutar `supabase login`, `supabase init`, `supabase link --project-ref <referencia-del-proyecto>` y `supabase db push`. Revisar el proyecto vinculado antes de aplicar. No mezclar ambos procedimientos sin sincronizar el historial de migraciones.

Para Sesión 02, con proyectos ya instalados, ejecutar **solo** `supabase/migrations/202611150002_chat.sql` una vez en el mismo proyecto. Crea seis tablas de chat, RPC, índices, RLS y bucket privado `project-files`. No elimina ni reconstruye proyectos. Comprobar que el bucket sea privado y tenga políticas SELECT/INSERT/DELETE. No se requiere una clave administrativa en la aplicación.

Comprueba en Table Editor la tabla pública `projects` y en sus políticas RLS las cuatro operaciones. No deshabilites RLS para solucionar errores.

En **Authentication**, habilita email/contraseña. Configura **URL Configuration**:

- Site URL: `http://localhost:5173`.
- Redirect URLs: `http://localhost:5173/dashboard`.
- Decide si exigirás confirmación de correo. Si está activa, el registro informa que debes abrir el enlace recibido; no presupone sesión.
- Ajusta la política de contraseña y su longitud mínima; el cliente usa por defecto 8. Las reglas adicionales y los límites de envío los aplica Supabase. Un correo ya registrado puede recibir una respuesta deliberadamente ambigua del proveedor.

## 2. Variables

Copiar `frontend/.env.example` a **`frontend/.env.local`**. Colocar ahí la URL y la clave **publicable** del proyecto (Settings / API Keys). Nunca usar una clave secreta o `service_role`.

```dotenv
VITE_SUPABASE_URL=<URL de tu proyecto>
VITE_SUPABASE_PUBLISHABLE_KEY=<clave publicable>
VITE_API_URL=http://localhost:8000
VITE_AUTH_MIN_PASSWORD_LENGTH=8
```

La clave publicable está diseñada para el navegador; el acceso a los datos depende de Auth y RLS. Mantener igualmente las variables locales fuera de Git. El mínimo debe coincidir con el configurado en Supabase. Reiniciar Vite al cambiar variables.

Copiar `backend/.env.example` a **`backend/.env`**. `ALLOWED_ORIGINS` acepta orígenes separados por comas, sin barras finales. Completar `SUPABASE_URL` y `SUPABASE_PUBLISHABLE_KEY` con el mismo proyecto del frontend (clave publicable, nunca `service_role`).

Un administrador elegible conforme a las condiciones de Google debe configurar `GEMINI_API_KEY` solo en backend. `GEMINI_MODEL=gemini-3.5-flash-lite` es el valor predeterminado, configurable sin modificar código. No se eluden requisitos de edad, cuotas ni permisos. No colocar claves privadas en variables `VITE_`, capturas ni commits.

La API inicia y `/health` responde aunque falten claves. Sin Supabase, las rutas privadas devuelven 503; sin Gemini, la interpretación informa que falta habilitar el proveedor y conserva el mensaje para reintentar sin duplicarlo. No hay fallback simulado. El cliente intenta renovar una vez la sesión; si falla, permite volver a ingresar.

Límites configurables en `.env.example`: 10 MB por archivo, 20 000 filas, 120 columnas, 30 MB expandidos, 12 archivos por conversación, 45 000 caracteres de contexto y 35 s por llamada Gemini. Se limitan además celdas (2000 caracteres), hojas (30) y páginas PDF (80). Al aumentar `MAX_FILE_BYTES`, ajustar también `storage.buckets.file_size_limit` y el proxy/hosting. Empezar con un worker Uvicorn en Render para conservar un perfilado simultáneo por proceso. No hay OCR.

Storage no tiene cascada SQL: tras eliminar un proyecto o ante una compensación fallida, revisar y eliminar **solo** objetos huérfanos de ese proyecto desde Dashboard o Storage API. No borrar filas de `storage.objects` directamente. El backend advierte si no logra compensar. Eliminar un chat conserva archivos para otras conversaciones.

## 3. Arrancar

Desde `frontend`: `npm ci` y `npm run dev`. Desde `backend`: crear `.venv` con Python 3.12, instalar `requirements-dev.txt` y ejecutar `./.venv/Scripts/python -m uvicorn app.main:app --reload`. Ver comandos completos en README. Mantener ambas terminales abiertas. Comprobar `/health` con navegador o `Invoke-RestMethod http://localhost:8000/health`.

## 4. Recorrido de Auth y proyectos

1. Abrir `/login`, pasar a `/registro`, crear una cuenta propia y confirmar correo si corresponde. Ingresar y recargar: debe conservarse la sesión.
2. Crear un proyecto de tesis con descripción; comprobar dashboard y cuatro módulos. Crear un proyecto general: no debe tener Contexto. Abrir manualmente `/proyectos/<id-general>/contexto`: debe redirigir al asistente.
3. Editar nombre/descripción y comprobar persistencia tras recargar. El tipo permanece fijo. Cancelar una eliminación y comprobar que no cambia nada; luego confirmar y comprobar que desaparece.
4. Cerrar sesión, intentar una ruta privada y comprobar redirección a login. Abrir `/login` autenticado debe llevar al dashboard.
5. Usar dos cuentas en perfiles separados; cada cuenta debe ver únicamente sus proyectos. Con el JWT de B y la clave publicable, consultar el ID de A por REST debe devolver cero filas; PATCH/DELETE del ID de A no deben afectar filas. INSERT con propietario A usando JWT B debe fallar. Con el JWT A intentar cambiar `user_id` o `project_type`: debe fallar. No probar como propietario de base de datos en SQL Editor: ese contexto omite RLS.
6. Validar escritorio y móvil, errores de conexión y reintento. No guardar JWT, contraseñas o datos reales en capturas, pruebas o commits.

## 5. Validación externa de Sesión 02 pendiente

Requiere migración remota, sesiones de usuario y credenciales Gemini autorizadas; no equivale a los dobles locales:

1. Con dos cuentas, crear proyectos y chats. Confirmar que B no puede leer, escribir, renombrar, borrar ni asociar recursos de A por REST/API o descargar sus objetos. Asociar archivos entre proyectos del mismo usuario también debe fallar.
2. General: crear chat → sin instrumento → CSV sintético → comprobar perfil y respuesta real Gemini → indicar que no conoce los datos → aceptar plan → recargar y comprobar persistencia y descarga.
3. Tesis: PDF → continuar → CSV/XLSX/JSON sintético → elegir hoja → aclarar diseño, escala y pareamiento → revisar variables y aceptar. Para interpretar PDF, revisar y habilitar el envío de extractos.
4. Otro chat → reutilizar archivos → comprobar relaciones nuevas y el mismo objeto físico. Pedir finalidad no relacionada y confirmar otro chat: debe conservarse el anterior.
5. Probar cuota/error transitorio, clave ausente, formato inválido, archivo grande, PDF escaneado y sesión vencida. Reintentar sin mensajes duplicados ni respuestas simuladas. Los planes no deben mostrar resultados inferenciales.

## Problemas frecuentes

### Instrumentos Word/PDF y tesis — Sesión 08

La versión local admite instrumentos PDF y DOCX en General y Tesis. DOC antiguo,
DOCM, archivos cifrados y objetos activos no son formatos admitidos: convertir
una copia a DOCX sin contraseña/objetos o PDF. El original aceptado permanece
privado, descargable y reutilizable dentro del mismo proyecto.

Reinstalar `backend/requirements-dev.txt` para incorporar `defusedxml` (Python
puro; sin OCR ni conversores del sistema). No hay variables nuevas.

**Requisito de esquema para DOCX:** la migración local
`supabase/migrations/202611200009_instrument_docx.sql` amplía exclusivamente los
CHECK de tipo/rol y el MIME del bucket privado existente. El usuario confirma que
ya se aplicó manualmente en su entorno de validación. No volver a ejecutarla;
conciliar el historial de migraciones antes de futuros despliegues y revisar otros
destinos en una fase autorizada. La Sesión 08 la preparó localmente y la Sesión 09
no ejecuta operaciones remotas. No volver a ejecutar migraciones anteriores.
PDF y los archivos históricos conservan sus referencias.

Al asociar instrumentos, elegir «Permitir consultar fragmentos» solo después de
revisar el contenido y el proveedor indicado. «Continuar sin compartir» conserva
el archivo privado sin enviarlo. La franja junto al compositor permite cambiar la
elección; las opciones de privacidad siguen disponibles. La autorización
está vinculada al proyecto, conversación y proveedor; cambiar de proveedor
requiere autorizar otra vez. No se comparten originales. Desactivar la opción
evita nueva recuperación documental, pero los mensajes anteriores siguen en el
historial compartido. Una consulta sin autorización informa el límite sin llamar
al proveedor. Especificar el código o términos buscados ayuda a recuperar texto
alejado del comienzo; el asistente indica documento y ubicación de los fragmentos.

Límites documentales: hasta 10 MB comprimidos y el máximo de archivo configurado;
30 MB expandidos por defecto, 500 entradas DOCX, expansión máxima 200:1 por entrada,
8 MiB por parte XML interpretada, 80 páginas PDF, 240 000 caracteres recuperados
(incluye solapamientos), 600 fragmentos. Un proceso de extracción por semáforo,
20 segundos, RSS observada del hijo hasta 192 MiB y API+hijo hasta 450 MiB.
La monitorización cada 100 ms no garantiza que no haya picos entre mediciones;
la instancia Render real sigue pendiente de medir. Mantener un worker.

PDF escaneado puede carecer de texto; no hay OCR. PDF multicolumna/tablas puede
perder orden. Word recupera párrafos, tablas, encabezados/pies, notas y comentarios;
no reproduce páginas, numeración automática ni imágenes y avisa de lectura parcial.
La vista previa local sigue limitada a 16 000 caracteres; la búsqueda usa todos los
fragmentos conservados. Por turno se recuperan hasta diez fragmentos y 12 000
caracteres en total. No encontrar un código no prueba que no exista fuera de lo
recuperable. Instrumentos históricos se amplían temporalmente desde el original
solo cuando se autoriza compartir, sin reescribir su metadata histórica.

Contexto muestra revisión confirmada y borrador modificado; revisar/guardar se
habilita con cambios reales. Un 409 conserva el borrador y exige revisar la versión
guardada; el chat no escribe Contexto. Resultados añade una vista local optativa
para declarar categorías de no información; no modifica resultados ni descargas.

Comprobaciones, causas y pendientes: [informe de Sesión 08](SESSION8_REPORT.md).

### Excel multihoja — Sesión 07

Reiniciar backend y frontend; no requiere migraciones, dependencias ni variables
nuevas. El asistente recibe la estructura global del libro antes de seleccionar
una hoja para planes. En Datos, abrir «Ver datos» o «Consultar metadatos y perfil»
para cargar el selector «Hoja visible». Cambiarlo solo actualiza la vista; la
hoja del asistente conserva su protección histórica. Los perfiles de archivos
antiguos se amplían temporalmente al consultar, sin reescribirlos.

Validaciones locales, límites y comprobaciones externas pendientes:
[informe de Sesión 07](SESSION7_REPORT.md). Medición sintética de memoria:
desde backend ejecutar `./.venv/Scripts/python scripts/measure_workbook_memory.py`.

### Comprobar perfilado y continuidad corregidos

No se requiere otra migración. Reiniciar API/Vite y crear conversaciones nuevas para validar. Volver a cargar el CSV original para obtener `profile_version=2`; los perfiles previos y las propuestas aceptadas no se recalculan ni sobrescriben. Después se puede reutilizar ese archivo sin duplicarlo físicamente.

`MISSING_VALUE_MARKERS` configura candidatos separados por comas. `MISSING_VALUE_OVERRIDES` es JSON por columna, vacío por defecto. Solo después de confirmar el significado, por ejemplo en Palmer Penguins, se puede usar `MISSING_VALUE_OVERRIDES={"sex":["NA"]}` y volver a perfilar. No aplicar ese ejemplo universalmente a otros datasets. Sin override se muestran 8 ausencias numéricas y 11 posibles ausencias ambiguas de sexo; con esa decisión coincide con las 19 de referencia.

Recorrido: comprobar las cuatro medidas cuantitativas y `year` temporal; pedir recomendaciones sin objetivo conocido; revisar varias alternativas e integral; solicitar Welch entre sexos de «una misma especie», elegir Adelie o todas y revisar alcance, efecto y multiplicidad antes de aceptar. Abrir otro chat, reutilizar y responder No: debe preguntar finalidad sin repetir presentación ni mostrar IDs. Recargar para comprobar persistencia y estados de las demás propuestas. El modelo de la prueba real fue `gemini-3.5-flash-lite`; `GEMINI_MODEL` sigue configurable.

### Actualizar el asistente final de Sesión 02

Aplicar `202611150003_chat_titles.sql` después de las dos migraciones existentes y reiniciar frontend/backend. Reemplaza únicamente `decide_proposal`, con la misma firma, permisos invoker y RLS: al aceptar actualiza un título provisional en la misma transacción. No crea tablas, no modifica planes aceptados ni retitula conversaciones en lote; los títulos manuales prevalecen.

El historial se puede plegar; en móvil/tablet abre un diálogo temporal. Enter envía, Shift + Enter inserta una línea y la composición IME no envía. Probar conversaciones nuevas: solicitar exploración sin `suggested_title`, elegir un plan integral y comprobar título/estado tras recargar. Revisar que independencia figure pendiente sin evidencia de diseño y que g con SD combinada use ν_H=n1+n2−2, separado de los gl de Welch. La aceptación no calcula; para ello usar «Ejecutar análisis» y confirmar las decisiones finales.

### Diagnóstico general

Para la última validación de Excel y planes descriptivos, consultar
[hotfix final local](HOTFIX_FINAL_REPORT.md), con pruebas, límites y comandos de localhost.

- Pantalla «Conecta tu espacio»: revisar nombres y ubicación de `frontend/.env.local`, URL y clave; reiniciar Vite.
- Registro sin acceso inmediato: revisar correo, spam, requisitos de confirmación y Redirect URLs. Supabase limita envíos; esperar o configurar SMTP propio si hace falta.
- Correo/contraseña incorrectos: confirmar correo, revisar proyecto configurado y credenciales; no desactivar seguridad.
- Tabla inexistente/permisos: aplicar las migraciones en el mismo proyecto de la URL; verificar sesión y políticas RLS.
- Error CORS de FastAPI: ejecutar desde `backend` y configurar el origen exacto. El CRUD de proyectos no pasa por FastAPI.
- Puerto 5173 ocupado: liberar el puerto o actualizar Site URL, Redirect URLs y CORS al puerto elegido.
- Proyectos funcionan pero el asistente falla: comprobar FastAPI, `VITE_API_URL`, Supabase en backend y migración de chat. Ante modelo no disponible o sin permisos, revisar `GEMINI_MODEL`, clave y cuota con el administrador.
- Los mensajes de error y `X-Statia-Error` distinguen esquema, modelo, cuota, permisos/clave del proveedor, timeout y conectividad; `X-Gemini-Status` conserva el código HTTP original. Un 503 del proveedor indica indisponibilidad y un 504 tiempo de espera; cambiar el timeout no corrige un 400 de esquema. No modificar `extra="forbid"` ni las validaciones estadísticas para evitar errores: el contrato de transporte está separado en `gemini_schema.py`. `GEMINI_MODEL` y los límites de espera siguen siendo configurables, sin ajustes específicos de Flash-Lite.
- Para investigar 503, desde `backend` ejecutar `./.venv/Scripts/python scripts/diagnose_gemini.py` (seco, sin solicitudes). Añadir `--live --cases A B C D E F` para seis solicitudes sintéticas reales, una por caso y sin reintentos; el código de salida 1 indica al menos un fallo. La salida JSONL solo contiene métricas, categorías y tokens disponibles. `--system-version session3 --cases D --live` compara las instrucciones históricas; requiere historial Git. No usar un éxito A/B como prueba de que funcionan las propuestas. Ver [informe y recorrido antes de Render](GEMINI_503_AUDIT.md). El timeout configurable es por intento; existe además un presupuesto de 65 s por generación completa, incluida la espera con jitter, para respetar el límite del turno.
- Error 404 al recargar una ruta en un hosting: configurar fallback SPA al publicar; producción se prepara en una sesión posterior.

### Validar alternativas con datos heterogéneos

Esta corrección no necesita otra migración ni volver a perfilar archivos. Reiniciar la API. Primero pedir solo descripción; después pedir varias alternativas e integral. Revisar variables/objetivos y el aviso si solo algunas alternativas pudieron validarse. Aceptar una válida, recargar y comprobar su plan/estado; un fallo conserva la solicitud para reintentar sin duplicar mensajes. Los logs `Planning validation` distinguen categorías por intento/propuesta sin incluir sus contenidos. Para un 502, revisar `X-Statia-Validation` desde una llamada HTTP o los logs del backend. No implica que haya fallado la lectura descriptiva del dataset.


## Sesión 03: instalación y comprobación de resultados

1. Aplicar en el mismo proyecto, después de 001/002/003, **solo** `supabase/migrations/202611150004_analysis_results.sql`. No repetir las migraciones anteriores ni una 004 ya aplicada. Mantener `analysis-results` privado. La migración aditiva crea tablas, índices, RLS, RPC y actualiza bienvenida/serialización de turnos; no borra planes ni originales.
2. En backend, reinstalar `./.venv/Scripts/python -m pip install -r requirements-dev.txt` (Python 3.12). Reiniciar API y frontend. Configurar Supabase con clave publicable y conservar GEMINI_MODEL configurable. No se necesita Gemini para calcular/consultar/descargar.
3. Producción prevista en Render de 512 MB: **un worker**, por ejemplo `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1` en su shell Linux. No usar varios workers para sortear el bloqueo. Hay un cálculo síncrono por proceso, 45 s para el hijo, 150 s para la operación y concesión de 180 s; no continúa como trabajo durable al cerrar/reiniciar el servidor. RSS: 320 MiB hijo y 450 MiB combinado API+hijo, monitorizado cada 100 ms; son barreras observadas, no una garantía del sistema operativo contra picos instantáneos. No se probó una instancia Render real.
4. Desde backend: `./.venv/Scripts/python scripts/check_analysis_quality.py`, `./.venv/Scripts/python -m pytest -q` y `./.venv/Scripts/python -m pip check`. Lint/formato Python se aplica a los módulos nuevos de análisis y sus pruebas; no adopta configuraciones globales del equipo. Opcional: `./.venv/Scripts/python scripts/measure_analysis_memory.py` mide RSS con datos sintéticos. Frontend: `npm test`, `npm run typecheck`, `npm run lint`, `npm run format:check`, `npm run build`. En supabase: `npm ci` y `npm test`. GitHub Actions ejecuta estos bloques en PR hacia develop/main, sin secretos ni servicios remotos.

### Recorrido manual con servicios reales (pendiente)

- Cuenta A autenticada → proyecto → conversación con dataset original → propuesta aceptada. Pulsar «Ejecutar análisis»: debe preparar sin calcular, mostrar una aclaración imprescindible o «Análisis preparado». Responder en el mismo chat, recargar y comprobar decisiones conservadas. Revisar resumen/filtros/grupos y confirmar el cálculo desde el resumen. No es necesario abrir «Opciones avanzadas» cuando no hay bloqueos. La aceptación sola no debe calcular.
- Penguins: descriptivo de medidas y frecuencias; correlación morfológica; Welch de masa por sexo dentro de Adelie. Declarar explícitamente `NA` como ausencia de `sex` y medidas solo en esta ejecución. Comprobar 152 filas tras filtro y 146 casos completos (73/73); diferencia female−male ≈ −674.657534 g. No transformar el archivo original.
- Titanic: descriptivo de edad/sexo (714 edades válidas, 177 ausentes), Pearson age/fare (714 parejas) y ANOVA de Welch de fare por pclass declarada categórica (216/184/491). Confirmar pertinencia metodológica antes de inferir; estos números son casos de validación, no reglas del motor.
- Verificar tablas, exclusiones, IC, efectos y supuestos pendientes. Recargar; abrir Resultados y comprobar conversación, fecha, método, estado y cantidad de recursos. Descargar CSV, PNG, JSON, Markdown y ZIP. Abrir el ZIP, verificar manifiesto/hashes, ausencia de originales y coincidencia con pantalla. Un resultado parcial debe señalar cada componente o pareja no calculable.
- Probar doble clic/reintento con mismo UUID; no debe duplicar ejecución ni evento. Interrumpir una solicitud, consultar estado después de 180 s y reintentar; cambiar decisiones crea otra ejecución. Probar fallo de Storage, originales inaccesibles, columnas/hoja alteradas, constantes, grupo vacío y plan no aceptado.
- Preguntar por p y g de Hedges; revisar que use el resultado real, conserve la conversación y no invente medidas. Con Gemini deshabilitado, la interpretación determinista y las descargas deben seguir disponibles. Pedir otra estadística requiere nueva propuesta/confirmación; otra finalidad conserva el mecanismo de nuevo chat.
- Cuenta B: pegar URLs de ejecución, artefacto y Storage de A, y probar REST SELECT/INSERT/UPDATE/DELETE; ningún recurso de A debe ser accesible. Repetir con otra conversación/proyecto de A para verificar FK compuestas. Estas comprobaciones remotas no se sustituyen por mocks ni por PGlite.

La corrección de preparación conversacional no agrega migraciones: reutiliza JSONB y RPC existentes de 002–004. Para validar, reiniciar API/Vite. La 004 sigue siendo necesaria para resultados si aún no está instalada; no repetirla si ya se aplicó. «No lo sé» retira esa pregunta activa y muestra **Preparación detenida por incertidumbre**, incluso al recargar un estado guardado por la versión anterior. Repetir el texto conserva la incertidumbre. **Revisar respuesta y cambiarla** reabre solo esa aclaración; **Solicitar propuesta descriptiva alternativa** usa la misma conversación y conserva los filtros, pero exige aceptar el nuevo plan. **Dejar pendiente y volver al chat** conserva las decisiones. Generar la alternativa requiere Gemini: probar el error sin proveedor y el reintento con el mismo UUID, sin duplicados. Preparar/ejecutar una propuesta suficientemente definida no requiere Gemini. Las respuestas simples se validan por opciones y expresiones inequívocas; el texto complejo no se convierte automáticamente en una confirmación. Revisar también cambios avanzados, rechazo de método incompatible, doble clic y preparación idéntica desde otra pestaña/dispositivo.

Los objetos de `analysis-results` deben mantenerse privados. Al borrar proyectos/conversaciones o después de un fallo incierto puede haber objetos huérfanos; eliminarlos mediante mantenimiento autorizado, comprobando primero que no estén referenciados por analysis_artifacts. No reutilizar rutas de originales ni hacerlos públicos. Los límites del motor y métodos no disponibles se detallan en [STATISTICAL_ENGINE.md](STATISTICAL_ENGINE.md).
