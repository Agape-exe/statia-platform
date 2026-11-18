# Hotfix final: Excel y ejecutabilidad descriptiva

Rama: `fix/correcciones-validacion-sesion6`, continuación de `8747f5f`.
Commits funcionales locales: `2713d8a` (Excel) y `d2a4858` (planes/navegación).
Recomendación: **APTO para una última validación manual local**, pendiente del
Excel y CSV originales y de respuestas reales del proveedor. No autoriza publicación.

## Causas y cambios

- **Excel:** el backend ya perfilaba automáticamente los libros de una hoja. Para
  varias hojas retornaba correctamente `needs_sheet_selection`; el frontend detenía
  comprensión hasta seleccionarla, pero el selector estaba dentro de dos paneles
  plegados. Ahora ambos se abren cuando falta hoja y aparece una indicación visible.
  Los XLSX perfilados muestran archivo, hoja, filas y columnas fuera de los paneles.
  Se conserva la continuación existente tras carga/selección, sin nuevos efectos ni
  solicitudes duplicadas. No se modificaron perfilado, originales ni asociaciones.
  `Notas.xlsx` no fue suministrado: esta causa se reprodujo con libros sintéticos;
  no se atribuye una composición de hojas al archivo original desconocido.
- **Planes:** `validate_plan` no anticipaba los bloqueos descriptivos de temporalidad,
  identificadores y cardinalidad que preparación/motor sí aplicaban. Una validación
  compartida rechaza los bloqueos conocidos durante generación y nueva aceptación:
  identificadores/temporales, más de 100 categorías o más de 20 grupos. Expone el
  motivo en aceptación (422) y al agotarse la corrección semántica (502), sin guardar
  el plan inválido. Las instrucciones exigen explicar limitaciones y reformular sin
  omitir productos pedidos. No se modificaron fórmulas, catálogo ni ejecución.
- **General:** instrucciones y control semántico de la frase observada indican
  revisar/aceptar desde la conversación. Se reutiliza la corrección acotada existente;
  no hay escritura de Contexto ni cambios en su flujo de tesis.

Con filtros/estratos, los recuentos marginales del perfil no demuestran la cardinalidad
del subconjunto: ese control exacto permanece en preparación. No se promete detectar
todo bloqueo usando solo el perfil. No se reescriben propuestas históricas ya aceptadas;
una propuesta antigua todavía pendiente sí se revalida al aceptarla. El control de prosa
es acotado y no garantiza detectar cualquier paráfrasis posible.

## Validación local

Todos los proveedores fueron simulados. No se accedió a Supabase remoto.

| Comprobación | Resultado |
| --- | --- |
| Pytest dirigido: hotfix, Sesión 6B y planificación | 84 aprobadas |
| Vitest dirigido: chat, ejecución y Contexto | 54 aprobadas |
| Pytest completo, una pasada por cada módulo | 574 aprobadas, 26 módulos |
| Regresión posterior del detalle del error | 3 aprobadas |
| Vitest completo | 119 aprobadas, 10 archivos |
| SQL/PGlite | 5 suites aprobadas |
| TypeScript, lint, Prettier y build | Aprobados |
| Calidad Python | 61 archivos, aprobada |
| pip check | Sin dependencias incompatibles |
| Navegador Edge con red simulada | Selector visible y una comprensión en General/Tesis |

La suite completa incluye descriptivos, Pearson, Welch, integral, Contexto, Resultados,
vista de registros/autorización, PDF + CSV, Markdown y selección/historial de proveedores.
Los 12 casos nuevos incluyen CSV/XLSX en ambos modos, selección/idempotencia, temporal,
identificador, límite 100/101 categorías, corrección fallida, rechazo de aceptación y
reformulación seguida de aceptación, preparación y ejecución de tres medidas de ventas.
El CSV de ventas se generó con 4.980 filas y ocho columnas; no es el archivo del usuario.
Las tres medidas producen N = 4.980 y se contrasta la media con Python independiente.

Advertencias existentes: deprecación httpx/Starlette y tamaño del chunk principal de
Vite (~501 kB). Sin fallos nuevos de pruebas. No se ejecutó integración real de IA,
Storage/RLS remoto ni validación manual con los archivos originales.

## Archivos y alcance

Frontend: `StatisticalChat.tsx`, `DatasetCard.tsx`, regresiones de `chat.test.tsx`.
Backend: nuevo `descriptive_feasibility.py`; integración en `gemini.py`, `chat.py`,
`conversation.py`, `interpretation_guards.py`; `test_hotfix_final.py` y lista de
calidad Python. Documentación: plan, informe, SETUP y ARCHITECTURE.

Sin dependencias, variables de entorno ni migraciones nuevas. Autenticación, permisos,
deduplicación y motor estadístico conservados. Riesgo residual: criterio conservador
del perfil y variabilidad del texto real del proveedor, sujetos a validación manual.
No se hizo push, PR, merge ni despliegue; no se alteraron datos históricos.

## Probar localmente

Se dejan Vite en `http://localhost:5173` y FastAPI actualizado en
`http://localhost:8001`, con recarga automática. Si ya están activos, no duplicarlos.
Para iniciarlos de nuevo, desde la raíz y en terminales separadas:

```powershell
cd backend
./.venv/Scripts/python -m uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

```powershell
cd frontend
$env:VITE_API_URL = 'http://localhost:8001'
npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
```

El ajuste de URL afecta solo al proceso; no cambia archivos de entorno.
En General y Tesis: «No tengo instrumento» → Excel de una hoja → comprobar conteos y
comprensión. Repetir con varias hojas → comprobar nombres visibles → seleccionar una
→ una comprensión. Con ventas, solicitar descripción general y comprobar explicación
de límites; reformular a `Units_Sold`, `Price_per_Unit`, `Revenue`, aceptar, preparar y
ejecutar. En General, comprobar que la aceptación se indique en la conversación.
