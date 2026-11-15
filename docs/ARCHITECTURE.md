# Arquitectura

El navegador usa Supabase Auth y PostgREST mediante Supabase JS. Los tokens son gestionados y renovados por el SDK, que recupera la sesión local y comunica cambios al `AuthProvider`. Los guards esperan la inicialización antes de redirigir. Las rutas autenticadas se remontan cuando cambia el usuario para no conservar datos de otra cuenta.

`pages` presenta formularios, dashboard y módulos; `components` contiene controles reutilizables y guards; `layouts` contiene el encabezado; `hooks` expone sesión; `services/projects.ts` concentra consultas y mutaciones; `lib` configura Supabase, traducción de errores y validaciones; `types` describe el modelo. No hay fallback de proyectos simulados. Sin configuración se muestra una pantalla de instrucciones.

`projects.user_id` referencia `auth.users`; RLS evalúa `auth.uid()` en SELECT/INSERT/UPDATE/DELETE. Los filtros del cliente mejoran la claridad de las consultas, pero RLS constituye la barrera de seguridad. Un trigger sin privilegios elevados conserva identidad, propietario, tipo y fecha inicial y actualiza `updated_at`. Los constraints replican límites del formulario. La migración crea únicamente la entidad utilizada.

FastAPI tiene configuración Pydantic por entorno, CORS con orígenes explícitos, errores internos sin detalles sensibles y un router de salud. No accede a Supabase ni repite el CRUD. El backend inicia sin claves de IA. `VITE_API_URL` no se utiliza todavía.

En próximas sesiones, FastAPI validará JWT de Supabase antes de acceder a datos de usuario. Gemini será un adaptador servidor, con claves solo en backend. El motor estadístico Python ejecutará cálculos independientemente del modelo; sus resultados verificables alimentarán explicaciones. Conversaciones pertenecerán a proyectos, archivos se reutilizarán dentro del proyecto y resultados se vincularán con ejecuciones. Estas entidades, contratos y adaptadores se crearán cuando se implementen; esta sesión no crea tablas vacías para ellas.

Vercel y Render son destinos previstos, sin despliegue en esta sesión. Para publicar el SPA se necesitará fallback a `index.html` para rutas React Router y configurar los nuevos orígenes y redirects de Auth.
