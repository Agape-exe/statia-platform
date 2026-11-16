# Contexto de tesis — MVP de Sesión 04

El módulo Contexto permite editar los objetivos, pregunta/problema, hipótesis opcionales, variables, metodología, población/muestra, instrumentos e información adicional. Solo aparece en proyectos `thesis`. La navegación y la API rechazan proyectos generales; RLS también impide insertarles contexto directamente.

## Instalación y uso

Aplicar una sola vez `supabase/migrations/202611160006_research_context.sql` después de comprobar 001–005. Es aditiva: crea `research_contexts`, su validador/trigger y un RPC invoker. No modifica proyectos, originales, propuestas ni resultados. No repetir migraciones anteriores. Reiniciar API y frontend o hacer redeploy de ambos.

1. Abrir un proyecto de tesis → Contexto. La ausencia de un documento es un estado válido, no un error.
2. Completar los campos conocidos; dejar vacíos los textos desconocidos. Las listas permiten un elemento por línea. No es obligatorio tener hipótesis ni seguir una estructura metodológica específica.
3. Opcional: abrir **Importar contexto desde JSON**, descargar el [prompt maestro](../frontend/public/contexto-tesis-prompt.md), usarlo con información metodológica no sensible y pegar el JSON o elegir un archivo `.json` de hasta 100 KB. La lectura se realiza en el navegador y no envía el archivo original a Storage ni al proveedor.
4. **Cargar importación para revisar** reemplaza el borrador completo, nunca fusiona automáticamente. Revisar y editar los campos. Valores ausentes se presentan como desconocidos; no se completan con inferencias.
5. **Revisar antes de guardar** abre el documento completo, incluidos campos adicionales y vacíos. Solo **Confirmar y guardar contexto** realiza el PUT autenticado.
6. Un guardado correcto muestra revisión/fecha y actualiza la información de consultas posteriores. Al cambiar de módulo sin guardar se pierde el borrador local; no hay autoguardado.

## Contrato JSON v1

Todos los campos de contenido son opcionales. `schema_version` debe ser el número 1 al importar. API y base de datos revalidan tipos y límites; claves ajenas se rechazan, sin descartarlas silenciosamente.

```json
{
  "schema_version": 1,
  "research_title": null,
  "research_problem": null,
  "general_objective": null,
  "specific_objectives": [],
  "hypotheses": [],
  "variables": [],
  "methodological_design": null,
  "population_sample": null,
  "instruments": [],
  "additional_information": null,
  "additional_fields": {}
}
```

Textos: hasta 2000 caracteres. Listas: hasta 20 textos de 1–500 caracteres. Variables e instrumentos se describen libremente; el contrato no impone rol, escala o disciplina. `additional_fields` acepta hasta 20 claves de 1–80 caracteres con texto de hasta 2000 caracteres o null. Documento normalizado: hasta 16000 caracteres JSON compactos en aplicación. El CHECK SQL admite hasta 18000 caracteres en la representación JSONB con espacios, además de límites por campo; la API conserva el límite compacto más estricto. No incluir datos de participantes, credenciales ni información confidencial.

## API, revisión y seguridad

- GET `/projects/{project_id}/research-context` → `{context: null}` o `{context: {document, revision, updated_at}}`.
- PUT en la misma ruta → `{document, expected_revision, confirmed: true}`. La primera creación usa revisión esperada 0. El resto usa la revisión recuperada. La confirmación debe ser booleana explícita.
- Ambas rutas validan el token en Supabase Auth, comprueban propietario y tipo y usan REST/RPC con el JWT del usuario y clave publicable. No hay `service_role` ni CRUD nuevo de proyectos.
- `save_research_context` bloquea el proyecto durante la transacción y contrasta la revisión vigente. El trigger impide mover el documento a otro proyecto o alterar su fecha de creación, e incrementa la revisión. RLS permite SELECT/INSERT/UPDATE únicamente al propietario de una tesis. No se concede DELETE directo; eliminar el proyecto propio conserva su cascada.
- Si otra pestaña guardó antes, el RPC rechaza el documento obsoleto con 409. El borrador de pantalla se conserva; **Recargar versión guardada** pide confirmar que se reemplazará ese borrador. Un fallo de red también conserva los campos. No se resuelve un conflicto sobreescribiendo automáticamente.

## Integración con el asistente

`current_context` relee el documento y valida su contrato antes de cada consulta que llegue a Gemini. No usa una caché de conversación. `build_context` añade documento, revisión y fecha para tesis, con redacción de patrones sensibles; general recibe null y no consulta la tabla. La redacción no garantiza anonimización universal: el usuario revisa qué confirma.

La información es dato no confiable. Las instrucciones del proveedor explican que null/listas vacías no son hechos inventados, y que el contexto no confirma automáticamente independencia, pareamiento o correspondencia con columnas. El historial conversacional puede contener información anterior: si hay contradicción debe aclararse. El contexto comparte el presupuesto de caracteres existente; un exceso devuelve un error explícito, sin truncar JSON ni eliminar columnas.

El mensaje nuevo registra `metadata.research_context_revision`. No se reescriben mensajes, planes, ejecuciones, artefactos ni sus snapshots anteriores. Al interpretar resultados, el proveedor debe respetar la metodología de esos resultados aunque el contexto actual haya cambiado. No existe una herramienta de actualización de Contexto desde Gemini o el chat: ante una sugerencia metodológica, indica revisar y confirmar en el módulo. La edición por formulario también exige esa confirmación.

## Verificaciones y pendientes

HTTP/proveedor controlados: edición/confirmación, revisión obsoleta, acceso ajeno/general, redacción, lectura vigente entre dos turnos y conservación de mensajes históricos. SQL/PGlite: migración aditiva, validación de JSON, RLS de dos usuarios, RPC real y revisión, inmutabilidad y cascada. UI: importación/borrador, errores sin pérdida de campos, revisión/confirmación y conflicto. Navegador: fixture sintética de presentación en 1440×900 y 390×844, sin Supabase.

Pendiente manual: aplicar/verificar 006 remota, probar dos cuentas con REST/Storage/API reales y completar el recorrido con Gemini y persistencia remota. La guía común está en [DEPLOYMENT](DEPLOYMENT.md). Evidencias finales: [SESSION04_VALIDATION](SESSION04_VALIDATION.md).
