# Corrección local de bloqueos del PR #7

Base auditada: `f6df957af358e5cf6f2c781a936c16d3e16b8aff`. Rama existente
`feat/integracion-multiproveedor-backend`; checkout inicialmente limpio y PR abierto
hacia `develop`, sin fusión automática.

1. Reproducir los fallos con proveedores simulados, motor Python y PostgreSQL local.
2. Sustituir la advertencia como control de capacidades por validación conservadora:
   catálogo finito de productos, cobertura por componentes y aclaración ante prosa
   desconocida. Revalidar generación, aceptación, preparación y ejecución; conservar
   planes y resultados históricos sin cambios ni recortes de productos.
3. Separar adquisición legacy y adquisición multiproveedor para impedir que un backend
   anterior procese solicitudes vinculadas a OpenAI o a un modelo conocido diferente.
   Reproducir con el backend real de `74b9577`, no una imitación de su ruta.
4. Conservar 007 intacta y añadir 008 transaccional, invoker y bajo RLS. El usuario
   confirmó mediante captura que 007 falta en el entorno consultado; no hay confirmación
   de todos los demás entornos. No acceder a Supabase, Render ni Vercel.
5. Ejecutar suites backend/SQL/frontend, lint, sintaxis, dependencias, compilación y
   revisión de secretos/diff. Documentar pruebas locales, límites y secuencia manual
   de instalación/verificación/recuperación con Terra deshabilitado.
6. Preparar commits locales en español y entregar informe. Sin push, actualización de
   PR, despliegue, migraciones remotas, llamadas a proveedores ni créditos.

No se dispone del script del auditor en el repositorio ni en los comentarios del PR.
Se reconstruye la secuencia descrita usando el código histórico real y PostgreSQL local,
identificando expresamente esta limitación de procedencia de la reproducción.
