# Despliegue manual — Render, Vercel y Supabase

Preparado el 16 de noviembre de 2026. El usuario realiza los despliegues y cambios remotos. No se crearon servicios ni se cambiaron planes o configuraciones de cuenta desde esta sesión. No hay una URL pública validada todavía. Usar el proyecto Supabase existente.

## 1. Antes de publicar

1. Revisar el PR de Sesión 04 hacia `develop`. Para demostrar antes de fusionar, seleccionar explícitamente `feat/sesion4-contexto-despliegue` en ambos servicios. Tras la fusión revisada, cambiar su rama a `develop`; no depender de `main`, que puede contener otra versión.
2. No subir `.env`, `.env.local`, credenciales, datasets de usuarios ni carpetas `.vercel`. Mantener las claves en los paneles de cada proveedor.
3. No crear otro Supabase. Comprobar el identificador del proyecto de las variables locales antes de configurar producción. Una clave publicable es válida en navegador; Gemini y claves secretas nunca deben llevar prefijo `VITE_`.

## 2. Supabase existente: comprobar antes de aplicar

En SQL Editor (solo inspección), comprobar tablas, políticas y buckets con las consultas de `supabase/checks/deployment.sql`. No acredita RLS entre usuarios porque SQL Editor usa permisos privilegiados.

Revisar **Database → Migrations** o el historial de la CLI si se usó ese mecanismo. Si las migraciones se ejecutaron manualmente y no hay historial, contrastar sus objetos y funciones con los archivos versionados. Una tabla existente por sí sola no acredita que se aplicó una migración completa. Comparar `pg_get_functiondef` con las definiciones de 003 y 005. No volver a ejecutar una migración ya instalada ni usar `db reset`.

Orden obligatorio de archivos en `supabase/migrations`:

| Número | Archivo | Comprobación principal |
| --- | --- | --- |
| 001 | `202611150001_projects.sql` | projects, RLS CRUD, tipo/propietario inmutables |
| 002 | `202611150002_chat.sql` | conversaciones, archivos, propuestas, turnos, project-files privado |
| 003 | `202611150003_chat_titles.sql` | decide_proposal y títulos manuales |
| 004 | `202611150004_analysis_results.sql` | runs, artifacts, RPC y analysis-results privado |
| 005 | `202611160005_chat_timeline.sql` | source_message_id y finish_chat_turn actualizado |

Aplicar **solo los archivos ausentes**, completos y en orden, en SQL Editor. Si se administra con CLI, verificar vinculación e historial antes de `supabase db push`; reconciliar migraciones manuales con el historial antes de usarlo. No ejecutar ambos caminos sin reconciliación. Las migraciones nuevas de Contexto se documentan en `THESIS_CONTEXT.md`.

Auth: mantener email/contraseña y la confirmación de correo que corresponda. No desactivar RLS ni hacer públicos los buckets para resolver errores. Las políticas existentes filtran por propietario; el backend debe usar clave publicable y el JWT del usuario, nunca `service_role`.

## 3. Backend en Render

Crear manualmente **New → Web Service** y conectar `Agape-exe/statia-platform`. Elegir la rama revisada.

| Ajuste | Valor |
| --- | --- |
| Runtime | Python |
| Root Directory | `backend` |
| Python | `3.12` desde `.python-version` (no sobrescribir con otro PYTHON_VERSION) |
| Build | `pip install -r requirements.txt` |
| Start | `sh start.sh` |
| Health Check Path | `/health` |
| Instancias / workers | 1 / 1 |
| Plan inicial | Free; no seleccionar uno de pago sin autorización |
| Auto deploy | Off inicialmente; actualización manual tras comprobaciones |
| Discos | Ninguno |

El script usa `exec`, escucha `0.0.0.0:$PORT` y limita BLAS a un hilo. Si se elige raíz del repositorio en lugar de backend: build `pip install -r backend/requirements.txt`, start `sh backend/start.sh`; la `.python-version` de raíz conserva Python 3.12. No instalar `requirements-dev.txt` en producción.

Alternativa reproducible: revisar `render.yaml` en la rama elegida y crear un Blueprint manualmente. No aplicar el manifiesto a un servicio previo de otro nombre ni mantener dos mecanismos de configuración simultáneamente. El archivo selecciona Free y no incorpora secretos. CLI opcional: `render blueprints validate render.yaml` antes de aplicarlo. El manifiesto pasó el esquema oficial draft2020; esta validación local no sustituye la validación del proveedor.

Variables del servicio (tomar nombres de `backend/.env.example`):

| Variable | Configuración |
| --- | --- |
| SUPABASE_URL | URL HTTPS del proyecto existente |
| SUPABASE_PUBLISHABLE_KEY | Clave publicable del mismo proyecto |
| GEMINI_API_KEY | Clave privada, solo en Render |
| GEMINI_MODEL | `gemini-3.5-flash-lite` o modelo autorizado disponible |
| ALLOWED_ORIGINS | Origen HTTPS exacto de Vercel y `http://localhost:5173`, separados por coma, sin barra final |
| GEMINI_TIMEOUT_SECONDS / GEMINI_CONTEXT_CHARS | 35 / 45000 inicialmente |
| MAX_FILE_BYTES / MAX_ROWS / MAX_COLUMNS | 10485760 / 20000 / 120 |
| MAX_EXPANDED_BYTES / MAX_CONVERSATION_FILES | 31457280 / 12 |
| MISSING_VALUE_MARKERS / MISSING_VALUE_OVERRIDES | Valores de ejemplo; overrides `{}` salvo decisiones justificadas |

Antes de conocer la URL de Vercel puede mantenerse solo el origen local. Actualizar después con el origen real y redeployar. No permitir `*`, `*.vercel.app`, rutas, credenciales o barras finales. Añadir previews uno por uno si se usarán.

Desplegar, esperar estado **Live** y copiar la URL real que asigne Render. Abrir `https://<host-real>/health`: debe responder `{"status":"ok","service":"statia-platform-api"}`. Este endpoint no prueba Supabase ni Gemini; las rutas privadas sin sesión deben devolver 401. No continuar a una demostración si el deploy falló.

### Capacidad y límites

El plan Free documenta 512 MB y 0,1 CPU; se suspende por inactividad y su primer acceso puede tardar. Es una opción de demostración, sin promesa de disponibilidad de producción. Revisar sus cuotas vigentes de horas, compilación y transferencia. Referencias: [planes](https://render.com/docs/compute-plans), [Free](https://render.com/docs/free), [Python](https://render.com/docs/python-version).

Medición local reproducible: desde backend, `.venv/Scripts/python scripts/measure_analysis_memory.py` en Windows; `python scripts/measure_analysis_memory.py` en Linux. Usa 20 000 filas, 400 000 celdas sintéticas y gráficos; no credenciales. Resultado de esta sesión: Windows/Python 3.12.10, 2 629 782 bytes de original, API inicial 89,3 MiB, hijo 212,0 MiB, combinado 314,5 MiB, 7,41 s, estado completed. No es un máximo para todos los métodos ni una medición Render. La CPU gratuita puede exceder el tiempo aunque quepa en memoria.

La misma medición se completó en Linux local (WSL Ubuntu, Python 3.12.3, instalación de producción limpia): API inicial 102,9 MiB, hijo 236,6 MiB, combinado 357,2 MiB, 6,27 s, estado completed; sin conflictos de dependencias. CI la repite en Ubuntu/Python 3.12. Falta la demostración y medición real en Render. Mantener un worker: API e hijo comparten exclusión con perfilado. Barreras actuales: 320 MiB del hijo, 450 MiB combinados, sondeo 100 ms, 45 s cálculo, 150 s operación, lease 180 s; un hilo BLAS. No hay cola durable ni continuidad tras reinicio. El perfilado sucede en un hilo de la API y conserva límites de bytes/filas/expansión, pero no dispone de la barrera RSS del subprocess. Los picos entre sondeos y exportación requieren vigilar métricas del hosting.

No hay dependencia de disco persistente: originales y resultados privados van a Storage; el cálculo usa memoria. Cachés de fuentes/Matplotlib son temporales y pueden regenerarse. Recursos exportados: hasta 24 MB conjuntos, incluidos ZIP; no incluyen originales. No añadir un disco para solventar memoria.

Si la demostración pequeña supera memoria/tiempo, registrar el fallo y reducir filas/componentes con revisión del usuario. Alternativa: solicitar autorización para un plan con más CPU/RAM, medir de nuevo y mantener los límites. No contratar ni cambiar planes automáticamente.

## 4. Frontend en Vercel

Importar manualmente el mismo repositorio. Root Directory **frontend**, framework **Vite**, install `npm ci`, build `npm run build:production`, output `dist`, Node **24.x**. Seleccionar la rama revisada; si Vercel toma otra por defecto, cambiar Production Branch antes de publicar esa versión. `frontend/vercel.json` resuelve recargas de React Router mediante `/index.html`.

En Environment Variables, configurar para Production y para los previews que se vayan a validar:

| Variable | Valor que debe aportar el usuario |
| --- | --- |
| VITE_SUPABASE_URL | URL HTTPS del Supabase existente |
| VITE_SUPABASE_PUBLISHABLE_KEY | Publicable o anon; jamás secreta/service_role |
| VITE_API_URL | URL HTTPS real del backend Render, sin barra final |
| VITE_AUTH_MIN_PASSWORD_LENGTH | 8 o el mínimo real de Supabase |

`build:production` rechaza URLs ausentes/no HTTPS, hosts locales, claves administrativas y variables privadas reconocibles. No imprime valores. Los valores `VITE_` se incorporan al JavaScript público; revisar todos los nombres y contenidos, incluso si pasan la validación. `npm run build` conserva el build local con configuración de desarrollo; para publicar usar siempre `build:production`.

Desplegar y esperar **Ready**. Copiar el dominio estable real. Probar `/login`, `/dashboard` y `/proyectos/<id-propio>/asistente` por navegación y recarga directa. No pegar IDs ajenos ni usar rutas inventadas como evidencia. Confirmar HTTPS y que Network llama a Render, no a localhost. Ver [Vite en Vercel](https://vercel.com/docs/frameworks/frontend/vite).

## 5. Conectar los orígenes reales

1. En Render, añadir el dominio estable Vercel exacto a `ALLOWED_ORIGINS`, conservar localhost y redeployar. Verificar preflight con Authorization/Content-Type y rechazo de un origen ajeno. CORS no sustituye Auth ni RLS.
2. En Supabase → Authentication → URL Configuration, establecer Site URL al origen HTTPS estable de Vercel. Añadir Redirect URLs exactas `https://<dominio-real>/dashboard` y `http://localhost:5173/dashboard`. Conservar otros redirects locales usados deliberadamente. No usar comodines de previews sin necesidad.
3. Registrar/confirmar correo con una cuenta propia; probar login, refresh, logout y redirección. Si falta SMTP/cuota/permisos de proveedor, documentar el error real. No poner contraseñas/JWT en documentación o capturas.

## 6. Demostración real pendiente

Usar cuentas de prueba propias y los datos públicos cuya procedencia está en `backend/tests/fixtures/README.md`. No probar con archivos personales.

- **General:** crear proyecto, chat sin instrumento, cargar Palmer Penguins, comprobar perfil (344 filas; revisar `NA` ambiguo de sex), pedir una propuesta descriptiva a Gemini real, aceptar, preparar, revisar decisiones y confirmar. Ver tablas/gráficos, recargar y descargar CSV/PNG/JSON/Markdown/ZIP; comprobar manifiesto y ausencia de originales. Preguntar por resultados guardados sin ejecutar otra vez.
- **Tesis:** crear proyecto, revisar/importar y confirmar Contexto según `THESIS_CONTEXT.md`, adjuntar datos, consultar al asistente, aceptar/preparar/confirmar, revisar resultados. Cambiar Contexto y confirmar que una consulta posterior lo incorpora sin cambiar recursos históricos.
- **Aislamiento:** dos cuentas en perfiles separados; B no puede listar/editar/eliminar proyectos, Contexto, chats, runs o archivos de A; probar REST con JWT de B y clave publicable y las rutas de descarga. A tampoco puede asociar archivos de otro proyecto propio. SQL Editor no prueba esto.
- **Errores:** Gemini ausente/cuota, API dormida, red interrumpida, sesión vencida, doble clic/reintento y archivo incompatible; no duplicar mensajes/runs ni simular respuestas.
- **Pantallas:** escritorio 1440×900 y móvil 390×844; revisar navegación, importación, scroll y controles de confirmación, sin registrar datos sensibles.

## 7. Actualización y redeploy

Revisar pruebas del PR, fusionar manualmente cuando corresponda, aplicar solo migraciones aditivas pendientes en Supabase y registrar el historial. Actualizar rama de ambos servicios a la rama integrada. Desplegar backend primero; verificar health/Auth y luego frontend. Cambiar variables VITE requiere rebuild. Variables Render guardadas sin deploy no están activas.

Registrar SHA de ambos builds y repetir demostración. Si hay regresión, redeployar un SHA previo compatible con el esquema; un rollback de código no revierte migraciones ni datos. No borrar resultados/originales como parte del redeploy. Con auto deploy Off, cada actualización exige un deploy manual deliberado.

## Estado y pendientes

Pruebas locales y resultados de CI se registran en `SESSION04_VALIDATION.md`. Pendiente del usuario: aplicar/verificar migraciones reales, configurar variables y Auth, crear y desplegar los dos servicios, registrar URLs/SHA, comprobar TLS/CORS y ambos recorridos con dos usuarios, medir en Render y revisar métricas. La preparación local no acredita esos pasos.
