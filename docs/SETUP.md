# Configuración local

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

Un administrador elegible conforme a las condiciones de Google debe configurar `GEMINI_API_KEY` solo en backend. `GEMINI_MODEL=gemini-3.8-flash` es el valor predeterminado, configurable sin modificar código. No se eluden requisitos de edad, cuotas ni permisos. No colocar claves privadas en variables `VITE_`, capturas ni commits.

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

### Comprobar perfilado y continuidad corregidos

No se requiere otra migración. Reiniciar API/Vite y crear conversaciones nuevas para validar. Volver a cargar el CSV original para obtener `profile_version=2`; los perfiles previos y las propuestas aceptadas no se recalculan ni sobrescriben. Después se puede reutilizar ese archivo sin duplicarlo físicamente.

`MISSING_VALUE_MARKERS` configura candidatos separados por comas. `MISSING_VALUE_OVERRIDES` es JSON por columna, vacío por defecto. Solo después de confirmar el significado, por ejemplo en Palmer Penguins, se puede usar `MISSING_VALUE_OVERRIDES={"sex":["NA"]}` y volver a perfilar. No aplicar ese ejemplo universalmente a otros datasets. Sin override se muestran 8 ausencias numéricas y 11 posibles ausencias ambiguas de sexo; con esa decisión coincide con las 19 de referencia.

Recorrido: comprobar las cuatro medidas cuantitativas y `year` temporal; pedir recomendaciones sin objetivo conocido; revisar varias alternativas e integral; solicitar Welch entre sexos de «una misma especie», elegir Adelie o todas y revisar alcance, efecto y multiplicidad antes de aceptar. Abrir otro chat, reutilizar y responder No: debe preguntar finalidad sin repetir presentación ni mostrar IDs. Recargar para comprobar persistencia y estados de las demás propuestas. El modelo de la prueba real fue `gemini-3.5-flash-lite`; `GEMINI_MODEL` sigue configurable.

### Diagnóstico general

- Pantalla «Conecta tu espacio»: revisar nombres y ubicación de `frontend/.env.local`, URL y clave; reiniciar Vite.
- Registro sin acceso inmediato: revisar correo, spam, requisitos de confirmación y Redirect URLs. Supabase limita envíos; esperar o configurar SMTP propio si hace falta.
- Correo/contraseña incorrectos: confirmar correo, revisar proyecto configurado y credenciales; no desactivar seguridad.
- Tabla inexistente/permisos: aplicar las migraciones en el mismo proyecto de la URL; verificar sesión y políticas RLS.
- Error CORS de FastAPI: ejecutar desde `backend` y configurar el origen exacto. El CRUD de proyectos no pasa por FastAPI.
- Puerto 5173 ocupado: liberar el puerto o actualizar Site URL, Redirect URLs y CORS al puerto elegido.
- Proyectos funcionan pero el asistente falla: comprobar FastAPI, `VITE_API_URL`, Supabase en backend y migración de chat. Ante modelo no disponible o sin permisos, revisar `GEMINI_MODEL`, clave y cuota con el administrador.
- Los mensajes de error y `X-Statia-Error` distinguen esquema, modelo, cuota, permisos/clave del proveedor, timeout y conectividad; `X-Gemini-Status` conserva el código HTTP original. Un 503 del proveedor indica indisponibilidad y un 504 tiempo de espera; cambiar el timeout no corrige un 400 de esquema. No modificar `extra="forbid"` ni las validaciones estadísticas para evitar errores: el contrato de transporte está separado en `gemini_schema.py`. `GEMINI_MODEL` y los límites de espera siguen siendo configurables, sin ajustes específicos de Flash-Lite.
- Error 404 al recargar una ruta en un hosting: configurar fallback SPA al publicar; producción se prepara en una sesión posterior.
