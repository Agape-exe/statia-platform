# Configuración local

## 1. Supabase

En el proyecto existente abre **SQL Editor**, crea una consulta, pega el contenido completo de `supabase/migrations/202611150001_projects.sql` y ejecútalo una vez. Se usa una transacción para evitar una instalación parcial. No ejecutar de nuevo una migración ya aplicada: creará conflicto porque los objetos ya existen.

Alternativa con la CLI oficial de Supabase instalada: desde la raíz ejecutar `supabase login`, `supabase init`, `supabase link --project-ref <referencia-del-proyecto>` y `supabase db push`. Revisar el proyecto vinculado antes de aplicar. No mezclar ambos procedimientos sin sincronizar el historial de migraciones.

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

Copiar `backend/.env.example` a **`backend/.env`**. `ALLOWED_ORIGINS` acepta orígenes separados por comas, sin barras finales. No necesita credenciales Supabase ni Gemini.

## 3. Arrancar

Desde `frontend`: `npm ci` y `npm run dev`. Desde `backend`: crear `.venv` con Python 3.12, instalar `requirements-dev.txt` y ejecutar `./.venv/Scripts/python -m uvicorn app.main:app --reload`. Ver comandos completos en README. Mantener ambas terminales abiertas. Comprobar `/health` con navegador o `Invoke-RestMethod http://localhost:8000/health`.

## 4. Recorrido real pendiente

1. Abrir `/login`, pasar a `/registro`, crear una cuenta propia y confirmar correo si corresponde. Ingresar y recargar: debe conservarse la sesión.
2. Crear un proyecto de tesis con descripción; comprobar dashboard y cuatro módulos. Crear un proyecto general: no debe tener Contexto. Abrir manualmente `/proyectos/<id-general>/contexto`: debe redirigir al asistente.
3. Editar nombre/descripción y comprobar persistencia tras recargar. El tipo permanece fijo. Cancelar una eliminación y comprobar que no cambia nada; luego confirmar y comprobar que desaparece.
4. Cerrar sesión, intentar una ruta privada y comprobar redirección a login. Abrir `/login` autenticado debe llevar al dashboard.
5. Usar dos cuentas en perfiles separados; cada cuenta debe ver únicamente sus proyectos. Con el JWT de B y la clave publicable, consultar el ID de A por REST debe devolver cero filas; PATCH/DELETE del ID de A no deben afectar filas. INSERT con propietario A usando JWT B debe fallar. Con el JWT A intentar cambiar `user_id` o `project_type`: debe fallar. No probar como propietario de base de datos en SQL Editor: ese contexto omite RLS.
6. Validar escritorio y móvil, errores de conexión y reintento. No guardar JWT, contraseñas o datos reales en capturas, pruebas o commits.

## Problemas frecuentes

- Pantalla «Conecta tu espacio»: revisar nombres y ubicación de `frontend/.env.local`, URL y clave; reiniciar Vite.
- Registro sin acceso inmediato: revisar correo, spam, requisitos de confirmación y Redirect URLs. Supabase limita envíos; esperar o configurar SMTP propio si hace falta.
- Correo/contraseña incorrectos: confirmar correo, revisar proyecto configurado y credenciales; no desactivar seguridad.
- Tabla inexistente/permisos: aplicar migración en el mismo proyecto de la URL; verificar sesión y políticas RLS.
- Error CORS de FastAPI: ejecutar desde `backend` y configurar el origen exacto. El CRUD de proyectos no pasa por FastAPI.
- Puerto 5173 ocupado: liberar el puerto o actualizar Site URL, Redirect URLs y CORS al puerto elegido.
- Error 404 al recargar una ruta en un hosting: configurar fallback SPA al publicar; producción se prepara en una sesión posterior.
