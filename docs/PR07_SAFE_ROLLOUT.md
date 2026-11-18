# Instalación y recuperación manual de la corrección del PR #7

Estas son instrucciones para el propietario de los entornos reales, para una sesión
posterior autorizada. **No ejecutar migraciones ni despliegues durante esta corrección.**
No se accedió a las cuentas vinculadas de Supabase, Vercel o Render. La captura enviada
por el usuario muestra 007 ausente únicamente en el entorno consultado: columnas 007
vacías, RPC multiproveedor ausentes y tabla de historial de migraciones inexistente.
No se extrapola ese resultado a otros proyectos o entornos.

007 permanece byte por byte igual al SHA auditado. Se añade
`202611170008_provider_rollback_guard.sql`, con prerrequisito explícito de 007 y una
transacción. Si un entorno ya tiene 007, no repetirla ni reescribirla: aplicar solo 008.
Si no tiene 007, aplicar 007 y después 008 mientras Terra sigue deshabilitado. El
historial vacío no basta para decidir si una migración manual se aplicó; revisar también
columnas, funciones y permisos del esquema real.

## Secuencia de instalación

1. **Vercel y GitHub, antes de autorizar cualquier push.** En la cuenta que realmente
   administra Statia, abrir el proyecto en Vercel → Settings → Git y revisar la integración
   del repositorio. El usuario debe impedir y confirmar los despliegues automáticos
   de la rama de trabajo antes de autorizar publicación. Si el control por rama no está
   disponible, puede desconectar temporalmente el repositorio desde esa pantalla,
   evaluando que también suspende otros despliegues Git automáticos. No se ha cambiado
   esa configuración y no se asume que esté resuelto. No usar la cuenta vinculada a
   las herramientas como prueba de identidad del entorno real.
2. **Render real de Statia.** Abrir el servicio backend → Environment. Mantener
   `OPENAI_TERRA_ENABLED=false`, sin cambiar las claves. En Settings → Build & Deploy,
   el administrador debe asegurar que una publicación no active un despliegue automático
   no autorizado. Conservar el artefacto y configuración recuperables. No habilitar Terra
   en producción durante esta instalación ni como parte de las pruebas de este documento.
3. **Supabase real → SQL Editor → New query.** Comprobar el proyecto y el estado por
   objetos. Verificar también los prerrequisitos 001–006 (incluidos `analysis_runs`,
   `analysis_proposals.source_message_id` y `research_contexts`); si falta alguno, detener
   la instalación y revisar su historial antes de continuar. Tras autorización de instalación, ejecutar únicamente las migraciones pendientes
   007/008 en ese orden. 001–006 no se repiten. La 008 no transforma registros: conserva
   proveedor/modelo, mensajes, planes y resultados. Falla si faltan los prerrequisitos
   de 007; no instalar el backend dependiente antes de terminar ambas.
4. En **SQL Editor**, ejecutar el archivo de solo lectura
   `supabase/checks/provider_rollback.sql`. Debe devolver versión 1, las cinco funciones
   invoker con `search_path` vacío, ejecución `authenticated=true`/`anon=false` y RLS
   habilitado. Conservar las huellas para contrastar la versión instalada. Esto verifica
   esquema/permisos; no constituye una prueba de RLS con usuarios reales.
5. **Despliegue manual futuro en Render.** Solo con autorización separada, instalar el
   backend corregido sobre ese esquema y con Terra deshabilitado. El código también
   bloquea operaciones Terra si el RPC de protección de 008 falta o no devuelve 1;
   el fallo es 503 `openai_rollback_guard`, sin registrar una solicitud nueva ni llamar
   a otro modelo. Mantener un worker según la arquitectura vigente.
6. Ejecutar las pruebas funcionales de abajo antes de considerar instalado el backend.
   Conservar una versión de recuperación que incluya **ambas** correcciones, con Terra
   deshabilitado. La existencia del código local y de pruebas simuladas no significa
   que esa versión ya esté desplegada ni que Terra esté autorizado o listo para producción.

## Pruebas funcionales superiores a /health

Usar un entorno de validación, proyectos dedicados y datos sintéticos. El propietario
ejecuta estas acciones manualmente, sin compartir tokens o claves en el informe:

- Con JWT de la cuenta A y clave publicable, consultar `POST /rest/v1/rpc/provider_rollback_safety`
  en Supabase con cuerpo `{}`. Debe devolver `1`. Con clave publicable y rol anónimo
  debe denegar ejecución. No usar `service_role` ni considerar SQL Editor como cuenta A.
- Con el JWT de A, en FastAPI crear una conversación con `POST /projects/{proyecto_A}/conversations`
  y `{}`; verificar `assistant_provider=gemini`. Enviar `instrument_no` mediante `/turns`
  con un UUID nuevo, repetir exactamente el mismo UUID/payload y comprobar replay sin
  mensajes duplicados. Este recorrido es determinista y no consume modelos.
- Adjuntar un CSV sintético a esa conversación mediante el endpoint de archivos y consultar
  su perfil. No enviar `files_ready` ni otra acción generativa: eso requeriría autorización
  separada para una llamada real. Verificar originales privados y perfilado sin modificar datos.
- Consultar `GET /projects/{proyecto_A}/assistant-providers` autenticado. Gemini debe seguir
  predeterminado y OpenAI debe figurar deshabilitado. Intentar seleccionar OpenAI debe
  devolver 503, sin cambiar la selección y sin llamadas a modelos.
- Con cuenta B, intentar leer la conversación/solicitudes del proyecto A y llamar a sus RPC.
  Debe denegar acceso o devolver cero filas según la operación. Comprobar también desde
  REST con el JWT de B; no desactivar RLS para facilitar la prueba.
- Verificar que propuestas históricas incompatibles se leen sin reescritura pero se bloquean
  en una aceptación nueva, preparación o ejecución. Repetir una decisión ya aceptada es
  un replay que no cambia estado ni acredita capacidades; preparar/ejecutar siguen bloqueados.
  No usar datos reales para crear ejecuciones
  de prueba; las reproducciones completas con proveedores simulados están en las pruebas locales.

No se han ejecutado estos pasos externos. El usuario debe confirmar por entorno los
resultados de instalación, RPC, RLS, Auth/REST/Storage y pruebas funcionales.

## Recuperación

La protección SQL 008 es compatible con el backend anterior **para conversaciones Gemini
sin modelo vinculado**. Una solicitud completada se reproduce sin llamar a modelos,
aunque la selección haya cambiado. Un turno fallido con proveedor/modelo conocido no
puede ser adquirido por el backend anterior: devuelve conflicto SQL/HTTP 409. Esta
limitación es deliberada: esa versión no comunica qué modelo Gemini usaría.

Ante un fallo, mantener/desactivar Terra, conservar 007/008 y recuperar el artefacto
corregido de reserva. **No revertir el esquema ni sustituir los RPC por versiones 004/007.**
No modificar `chat_requests.provider/model` para desbloquear un UUID. Para cambiar de
destinatario se necesita una decisión explícita y otro UUID; nunca reintentar automáticamente
en Gemini una solicitud OpenAI fallida.

La reproducción con `74b9577` acredita la barrera de proveedor, no convierte ese backend
antiguo en una recuperación completa: carece del nuevo control de productos descriptivos.
Por ello, una recuperación funcional aprobada debe incluir las correcciones A y B.
Si esa versión no está disponible, mantener el asistente fuera de servicio y Terra
deshabilitado; no resolver la incidencia quitando las validaciones.

La comprobación de versión 008 supone conservar el esquema instalado. No protege frente
a que un administrador reemplace deliberadamente funciones después de la verificación.
Tampoco RLS acredita contenido que el propio propietario altere directamente en tablas.
