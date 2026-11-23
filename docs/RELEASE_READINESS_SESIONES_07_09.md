# Integración de sesiones 07, 08 y 09

Fecha: 23 de noviembre de 2026, America/Lima.
Repositorio: `Agape-exe/statia-platform`. Base: `develop` (`44227f6` al auditar).
Rama: `fix/estabilizacion-instrumentos-ux-sesion9`. Sin ramas nuevas, rebase,
force push, merge, despliegue ni cambios de servicios remotos.

## Alcance y procedencia

La auditoría comenzó con árbol limpio en `fa5b87f`. Después de `git fetch origin`,
`origin/develop` es ancestro de HEAD: 0 commits exclusivos en destino y 32 en
la rama, antes de este cierre documental. Se comprobó con `merge-base --is-ancestor`
que `feat/excel-multihoja` (`4fa072a`) y `fix/cierre-validacion-tesis` (`71c03d8`)
están incluidos completos. No había PR abiertos al comenzar. No hay conflictos
locales con esa base; GitHub deberá confirmar su estado para el HEAD publicado.

| Bloque | Cambios incluidos |
| --- | --- |
| 07 | Perfiles XLSX por hoja, comprensión global acotada y navegación por hojas; alias descriptivos verificados. |
| 08 | Extracción DOCX segura, recuperación PDF/DOCX, separación de conversación y planes, Contexto con cambios/revisión, presentación académica y migración 009. |
| 09 | Identidad índigo/lavanda global, chat y tarjetas, consentimiento contextual, recuperación por códigos y temas bilingües, títulos, intención, alcance y productos, validación parcial, aceptación/ejecución separadas y reintentos. |

El diff acumulado previo al cierre abarca 85 archivos: backend, frontend,
pruebas, documentación, una migración y configuración de Git. No cambia archivos
de `backend/app/services/statistics`. La capa de publicación de resultados
sí limita artefactos nuevos al alcance solicitado; no reescribe históricos.
No modifica workflows, autenticación remota ni políticas RLS de producción.
Las variables API aditivas y Plan v1 conservan lectura de planes antiguos.

Inventario exacto de commits de las sesiones, de más antiguo a más reciente
(los commits del cierre se agregan después, visibles en el PR):

- `7d29c61` fix(planes): reconocer productos descriptivos sin ampliar el alcance
- `6e0297d` feat(datos): comprender libros Excel y navegar hojas sin alterar planes
- `4fa072a` docs(sesion07): documentar validaciones y límites de Excel multihoja
- `b2da72a` docs(sesion08): registrar plan correctivo y continuidad local
- `6ee83a5` fix(instrumentos): admitir DOCX y recuperar texto documental con límites
- `e1d6661` fix(asistente): separar consultas de planes y validar equivalencias seguras
- `ea92e01` fix(contexto): distinguir revisiones confirmadas de cambios pendientes
- `74eb1c2` fix(interfaz): aclarar consentimiento documental y lectura académica de resultados
- `14cf271` test(auditoria): conservar el contrato histórico de Terra ante metadatos nuevos
- `71c03d8` docs(sesion08): documentar validaciones, límites y requisito de esquema
- `5eb2616` docs(sesion09): registrar plan de estabilización y alcance
- `f0be1dc` fix(instrumentos): recuperar referencias equivalentes y diferenciar diagnósticos
- `c2a7ac0` feat(interfaz): renovar identidad y aclarar el flujo documental
- `309acc7` docs(sesion09): documentar validaciones y límites de la entrega
- `6679d0f` fix(instrumentos): recuperar códigos de ítems con punto
- `913568c` fix(asistente): aclarar títulos y etiquetas de archivos
- `de16399` docs(sesion09): registrar la reproducción con el PDF público
- `205f36c` fix(instrumentos): recuperar evidencia temática bilingüe
- `b2f011a` test(datos): verificar columnas omitidas del resumen de Excel
- `6ac3b06` docs(sesion09): registrar el diagnóstico y la validación de T2
- `35b5e36` fix(instrumentos): evitar códigos falsos en consultas numeradas
- `bc3fae5` docs(sesion09): documentar el diagnóstico de la consulta numerada
- `cc6a09e` fix(asistente): validar y persistir las propuestas solicitadas
- `95744a1` fix(chat): distinguir la orientación de las propuestas revisables
- `cf90031` fix(asistente): conservar explicaciones en turnos sin petición explícita
- `fbfe927` docs(sesion09): registrar la validación del flujo de planificación
- `639a40b` fix(asistente): separar la conversación del alcance de cada propuesta
- `6ae5a58` fix(asistente): informar incompatibilidades sin reabrir decisiones resueltas
- `de0f169` docs(sesion09): registrar la validación de intención y alcance
- `45c4ddd` fix(planificacion): conservar exclusiones y validar el contrato de frecuencias
- `2a061b7` test(planificacion): actualizar la regresión de versión del alcance
- `fa5b87f` docs(sesion09): documentar el bloqueo de frecuencias y su revalidación


## Validación manual comunicada por el usuario

Estas son validaciones reales realizadas por el usuario, no llamadas realizadas
durante la auditoría ni resultados de los dobles de prueba:

- Student Depression: recorrido descriptivo general satisfactorio; tipos
  provisionales y texto de alternativas quedaron como observaciones.
- Tesis NHANES Dermatology, Contexto revisión 1 y Gemini real: carga,
  comprensión, reconocimiento de Contexto, consulta documental, conversación,
  propuesta de frecuencias de `sun_reaction`, tarjeta, aceptación, ejecución
  separada, tabla contrastada con referencia y persistencia al recargar.
  3419 registros, 3418 respuestas físicamente presentes y un ausente.
- Recuperación de preguntas reales en instrumentos PDF y DOCX con Gemini.

Las pruebas automatizadas locales usan proveedores/Auth/Storage simulados;
el perfilado, rutas, validadores y motor se ejecutan realmente. PGlite ejecuta
PostgreSQL/RLS local con Auth/Storage emulados. No certifica Supabase remoto.

## Defectos y límites aceptados para revisión

| Observación | Estado y efecto |
| --- | --- |
| Clasificación de variables | Pendiente metodológica: tipos preliminares requieren confirmación; no deben tratarse como escala validada. |
| Textos estadísticos genéricos | Pendiente: algunas frecuencias muestran explicaciones de medias, DE, varianza, IC o grupos no aplicables. Afecta la interpretación presentada; revisar antes de compartir informes. |
| Nombre del procedimiento | Pendiente: ciertos resultados muestran «Estadística descriptiva» en lugar de frecuencias categóricas. |
| Propuestas mencionadas y no disponibles | Corregido en regresiones: una tarjeta con prosa que ofrece tres y respuestas parciales con dos planes descartados. La respuesta nueva enumera solo planes validados; no se afirma ausencia universal de todas las variantes lingüísticas. |
| Raisin_Dataset.xlsx / Class | Defecto conocido pendiente: rechazo de referencias o productos al planificar frecuencias. No investigado ni corregido en este cierre por decisión expresa del usuario. |

No se declara cobertura exhaustiva de datasets, escalas, idiomas ni procedimientos.
PDF sin texto necesita una solución externa de OCR; DOC antiguo requiere conversión.
La recuperación temática tiene vocabulario acotado; la evidencia sigue siendo
literal y autorizada. No se unen hojas ni se limpian datos automáticamente.

## Migraciones y conciliación de Supabase

Única migración nueva frente a `origin/develop`:
`supabase/migrations/202611200009_instrument_docx.sql`.
07 y 09 no agregan migraciones; 001–008 ya pertenecen a la base.

La revisión SQL y PGlite comprueban que 009:

- Amplía CHECK de tipos a CSV/XLSX/JSON/PDF/DOCX y exige rol instrumento
  exactamente para PDF/DOCX. DOC y formatos activos quedan fuera.
- Conserva PDF y añade MIME
  `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
  a la lista existente del bucket `project-files`.
- No altera políticas RLS, propietarios, objetos ni límites del bucket.
  El bucket debe existir privado según 002, con MIME actuales no nulos.
  Un entorno divergente requiere diagnóstico, no volver a aplicar 002.
- Mantiene el orden 001–009, transacción completa y nombres de restricciones
  esperados. El archivo no es un script para ejecutarlo repetidamente.

El usuario confirma que 009 se aplicó manualmente en su proyecto de pruebas.
**El registro en `supabase_migrations.schema_migrations` no está verificado.**
No hay CLI Supabase instalada/vinculada localmente para ese proyecto; tampoco
se ejecutó SQL remoto, conforme a la restricción de este cierre.

Procedimiento posterior, por el usuario o en una sesión expresamente autorizada:

1. Identificar el proyecto exacto de pruebas y el futuro destino; no deducirlos
   por el nombre de una variable. Guardar evidencia/esquema e historial antes
   de modificar nada, sin versionar credenciales ni copias privadas.
2. En una CLI compatible, consultar `supabase migration list --help` y la
   lista del proyecto remoto vinculado. La documentación actual utiliza
   `supabase migration list --remote`; versiones anteriores usan `--linked`.
   No vincular automáticamente otro proyecto ni ejecutar `db push`.
3. Inspeccionar solamente el entorno: CHECK de `public.project_files`,
   `pg_policies`, `pg_tables.rowsecurity`, MIME, `public=false` y tamaño de
   `storage.buckets` para `project-files`. Contrastar con archivos 001–009
   y `supabase/checks/deployment.sql`. La inspección privilegiada no prueba
   aislamiento; repetir después con dos sesiones de usuario autorizadas.
4. Si 009 figura aplicada y el esquema coincide, no ejecutar nada. Si el
   esquema coincide completamente pero falta su versión en el historial,
   preparar **solo** la reparación de historial para `202611200009`.
5. **Requiere aprobación expresa antes de ejecutarse:**
   `supabase migration repair --status applied 202611200009 --remote`
   (o `--linked` si corresponde a la versión revisada). Marca el historial;
   no ejecuta el SQL de la migración. No marcar otras versiones sin comprobarlas.
6. Si hay aplicación parcial o divergencias, detenerse y diseñar una reparación
   revisable. Si falta tanto esquema como historial en otro entorno, aplicar
   la migración pendiente una sola vez, con aprobación. No hacer reset ni
   reejecutar las migraciones previas. Volver a listar historial y comparar.
7. Solo después de resolver discrepancias, revisar un `db push --dry-run`
   para el destino y aprobar por separado cualquier escritura real.

Referencia oficial consultada: [migraciones e historial de Supabase](https://supabase.com/docs/guides/deployment/database-migrations).
No se realizaron los pasos remotos de ese procedimiento en esta entrega.

## Dependencias, entorno y despliegue posterior

Nuevo paquete Python acumulado: `defusedxml>=0.7.1,<1` para XML de DOCX seguro.
No hay dependencias npm nuevas; `package.json` y lockfile permanecen iguales
a develop y se verifican con `npm ci`. No hay variables nuevas de aplicación
en 07–09. `STATIA_TEST_INPUT_DIR` pertenece al arnés de pruebas opcional.

Render existente: Python 3.12, raíz `backend`, instalación
`pip install -r requirements.txt`, arranque `sh start.sh`, un worker,
BLAS de un hilo y `/health`. La cabecera `X-Statia-Planning-Version: 6`
permite verificar el contrato nuevo, no acredita Auth/proveedores.
`render.yaml` es una plantilla histórica para creación manual y aún apunta
a `feat/sesion4-contexto-despliegue`: no sincronizarla sobre el servicio
existente. Elegir el SHA aprobado en el servicio durante el despliegue manual.

Vercel existente: raíz `frontend`, Node 24, `npm ci`,
`npm run build:production`, salida `dist`, rewrites de SPA existentes.
El build local sin credenciales usa `npm run build`. El guard de producción
debe rechazar URLs locales/vacías y claves privadas. Su funcionamiento se
comprueba con pruebas; no se introducen valores falsos para aprobarlo.
No se ejecuta un build de producción con secretos ni se validan paneles remotos.

Revisar en los servicios existentes, sin publicar valores: SUPABASE_URL y
publicable del mismo proyecto, GEMINI_API_KEY solo backend, modelo autorizado,
ALLOWED_ORIGINS exactos y variables VITE públicas de origen HTTPS. Terra
continúa experimental bajo habilitación explícita. Conservar límites de
bytes/filas/columnas/ZIP/tiempos y semáforo compartido. Un plan de hosting
no queda certificado por pruebas Windows: falta observar memoria, duración,
arranque en frío y concurrencia en Render. CI Ubuntu mide RSS del motor.

## Integración, producción y rollback

El PR es único hacia develop desde la rama actual. La publicación autorizada
no autoriza merge ni despliegue. No se cambian integraciones GitHub/Vercel/Render;
si existen previews automáticos externos, no acreditan producción ni se
promueven desde esta sesión. El YAML versionado tiene autodespliegue apagado;
la configuración real de los servicios no se ha comprobado.

Antes de merge: revisar diff, CI del HEAD y ausencia de conflictos; aceptar
expresamente el alcance de Raisin y los defectos de presentación. Asegurar
que el entorno donde se probará develop tiene 009 completa y conciliada.
Después el usuario podrá fusionar hacia develop; no se fusiona automáticamente.

Merge a develop: **NO APTO para fusión inmediata**, pendiente de esa revisión
y de verificar el historial de 009 cuando corresponda al entorno destino.
La rama sí está preparada para publicar un PR revisable con esos pendientes.

Producción: **NO APTO para desplegar todavía**. Pendientes conciliación,
revisión del PR, configuración efectiva de servicios, aceptación explícita
del defecto Raisin y textos de interpretación, y plan de despliegue aprobado.
No hay promoción automática a main.

Tras autorizar producción: registrar SHA/esquema de origen y destino, conservar
backup, verificar historial; desplegar backend compatible primero y frontend
después. Comprobar health/versión, Auth, CORS de origen permitido y rechazo
ajeno, descargas privadas y aislamiento con dos usuarios. Repetir general,
tesis, PDF/DOCX, multihoja, propuesta/aceptación/ejecución y persistencia.
Contrastar frecuencias/ausencias con la referencia; controlar memoria/tiempo.

Rollback: detener nuevas ejecuciones, conservar originales y resultados,
republicar los SHA anteriores compatibles de backend y frontend. No borrar
DOCX existentes ni deshacer 009: volver a CHECK solo PDF puede fallar y
romper referencias legítimas. El código anterior puede no leer DOCX; elegir
un SHA compatible o mantener la carga documental suspendida con decisión
operativa revisada. Un revert de código no restaura datos ni historial SQL;
cualquier reparación de esquema se diseña y aprueba aparte. No usar reset
destructivo ni force push para volver atrás.

## Resultado automatizado y publicación

Comprobaciones ya observadas en este cierre:

- `npm ci` frontend: instalación limpia aprobada tras liberar el módulo
  nativo que mantenía abierto Vite; cero vulnerabilidades informadas por npm.
  Vite se restauró en 5173 apuntando a la misma API 8001, sin editar `.env`.
- 133 pruebas frontend y dos del guard de producción aprobadas; TypeScript,
  lint, formato y build aprobados. Persiste el aviso de un chunk de 500,98 kB.
- `npm ci` y seis pruebas PGlite aprobadas, incluidas restricciones, PDF/DOCX,
  bucket privado, RLS, turnos, Contexto, resultados y proveedores.
- Calidad Python y `pip check` aprobados. Sin paquetes rotos.
- Medición multihoja local Windows: 4 hojas, 400 000 celdas, original
  1 737 696 bytes, RSS inicial 84,10 MiB y pico 107,73 MiB, 5,08 s;
  pasó el umbral del arnés. No mide Render ni garantiza máximos generales.
- Revisión de rutas añadidas y patrones de secretos en los 32 commits:
  sin hallazgos. Esta comprobación no sustituye una revisión de secretos
  exhaustiva; los originales reales y logs permanecen fuera de Git.

Backend completo ejecutado módulo a módulo en procesos aislados como CI:
31 módulos, **705 pruebas aprobadas y una omitida**, sin fallos. La omisión
es la evidencia histórica A/D `backend/test_terra_statia_env.py` no disponible;
no se oculta ni se sustituye por una validación real. Incluye planificación,
recuperación, consentimiento, Auth, persistencia, rutas y motor.
No se hicieron llamadas reales a proveedores.
No se ejecutó `build:production` con configuración remota: el build local y
las pruebas del guard no acreditan valores efectivos de Vercel/Render.

El enlace del PR,
SHA remoto y CI se registran en el propio PR y en la entrega final para
evitar un commit autorreferente que vuelva a invalidar sus verificaciones.
