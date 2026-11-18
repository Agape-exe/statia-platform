# Sesión 5B — selector multiproveedor frontend

Validación local: 17 de noviembre de 2026. **APTO para publicar el PR de 5B**,
con el alcance frontend validado mediante simulaciones; no acredita Terra en producción.
Rama: `feat/selector-proveedores-frontend`, creada desde `origin/develop` actualizado
en `fb73642` (fusión del PR #7). Sin push, PR, despliegue ni cambios de configuración externa.

## Comportamiento implementado

- Catálogo autenticado `GET assistant-providers` independiente del historial: carga,
  disponibilidad, modelo, experimental y recuperación explícita ante fallo. No hay catálogo simulado en producción.
- Selector compacto en el encabezado. Terra deshabilitado o sin configurar permanece
  visible y no seleccionable. Si está disponible, la elección abre una confirmación
  informada sobre mensajes futuros, historial, perfiles, Contexto de tesis y agregados.
- Cambio con `expected_provider` confirmado por el servidor, sin selección optimista.
  Un 409 recarga la conversación y explica el conflicto. Si falla esa recarga, o se
  pierde la respuesta del cambio, se bloquean operaciones hasta recuperar el estado.
- Bloqueo durante apertura, generación, preparación, cálculo, revisión avanzada,
  turnos pendientes y actividad remota informada por el detalle. Los errores de cambio
  y creación se muestran dentro del diálogo. Cancelar devuelve el foco al control.
- «Nuevo chat» y el historial conservan la creación rápida Gemini. La flecha contigua
  permite elegir proveedor para un chat nuevo: Gemini inicial y confirmación informada
  para Terra. Crear no envía turnos. Un fallo no muestra un chat inexistente.
  Una nueva finalidad siempre solicita Gemini, incluso si su origen usaba Terra.
- Procedencia por respuesta desde `metadata.generation` o `generation`, sin inferirla
  desde la selección actual. `selected_provider` solo no acredita generación.
  Se distinguen modelo histórico desconocido, acciones deterministas y eventos de cambio.
- Privacidad y comprensión de archivos nombran al proveedor confirmado. Se conservan
  los valores y el envío real de `share_samples` / `share_instrument_text`.
- Reintentos conservan UUID y payload. Un 409 conserva el conflicto; «Escribir otra
  solicitud» habilita una solicitud explícita con UUID nuevo. Sin fallback automático.
- El control de configuración de producción rechaza también variables privadas o de
  habilitación `VITE_OPENAI_*` y `VITE_TERRA_*`. No se agregan variables ni dependencias.

## Archivos

| Archivo | Cambio |
| --- | --- |
| `frontend/src/types/chat.ts` | Catálogo, selección persistida y procedencia |
| `frontend/src/services/chat.ts` | GET catálogo, POST con proveedor y PATCH con expectativa |
| `frontend/src/lib/assistant-provider.ts` | Etiquetas de disponibilidad y procedencia histórica |
| `frontend/src/components/AssistantProviderSelector.tsx` | Selector accesible y aviso compartido |
| `frontend/src/components/StatisticalChat.tsx` | Confirmaciones, creación, concurrencia y recuperación |
| `frontend/src/components/ChatComposer.tsx` | Privacidad dinámica y reintentos en conflicto |
| `frontend/src/index.css` | Ajuste compacto y responsive |
| `frontend/src/test/providers.test.tsx` | Contratos HTTP y experiencia multiproveedor |
| `frontend/src/test/chat.test.tsx` | Adaptación de fixtures y bloqueo durante preparación/cálculo |
| `frontend/scripts/check-production-env.mjs` | Protección de configuración OpenAI/Terra |
| `frontend/scripts/production-env.check.mjs` | Casos de configuración sintética |
| `docs/SETUP.md`, `docs/ARCHITECTURE.md`, este informe | Configuración y trazabilidad de 5B |

## Verificación

| Control local | Resultado |
| --- | --- |
| `npm run typecheck` | Correcto |
| `npm run lint` | Correcto, sin avisos |
| `npm run format:check` | Correcto |
| `npm test` | 105 pruebas, 8 archivos, todas correctas; 68 previas y 37 añadidas |
| `npm run test:deployment` | 2 pruebas correctas; configuración pública válida y casos inválidos sintéticos |
| `npm run build` | Correcto; aviso de Vite por chunk principal de 500,71 kB |
| Diff, formato Git y secretos | Revisión focalizada de los cambios; sin claves ni archivos de usuario añadidos |

Las pruebas nuevas usan el servicio y cliente HTTP reales del frontend, `fetch`
interceptado y una sesión sintética; también hay dobles controlados para preparación
y cálculo. Verifican los 20 puntos solicitados: catálogo/default, Terra habilitado y
deshabilitado, confirmación en ambos sentidos, cancelación/fallo/409, bloqueos,
persistencia/navegación, procedencia/determinismo, UUID incompatible, creación de
ambos proveedores, nueva finalidad, privacidad y accesibilidad responsive.
La suite previa continúa cubriendo sesión, proyectos, contexto, archivos, propuestas,
resultados, historial y recuperación. No se alteraron backend, SQL, Plan v1 ni fórmulas.

Navegador local: componente real aislado con servicios simulados, sin cargar `.env`
y con el cliente Supabase bloqueado. Inspección a 320×740, 390×844, 768×900 y
1280×800; selector dentro del ancho disponible, controles e historial adaptados,
Terra experimental, procedencia anterior intacta, confirmación legible, selección con
flechas, cancelación con Escape y foco restaurado. Capturas locales fuera de Git.
El arnés temporal está en `frontend/__qa__/session5b/`, ya excluido por `.gitignore`;
no entra en el bundle de producción.

Correcciones detectadas durante la revisión: margen global excesivo en la etiqueta
del selector móvil, errores ocultos detrás del diálogo, foco perdido al cancelarlo,
etiqueta de evento de cambio confundida con estado del plan, protección incompleta
de configuración OpenAI/Terra y operaciones habilitadas con selección incierta.

## Validación visual final de escritorio

La prioridad de uso es escritorio y laptops, conservando responsive. Se montó el
`Workspace` real, con `AppHeader`, navegación de módulos, historial lateral,
`StatisticalChat`, selector y compositor. Las capturas son del frontend real en
navegador local; la sesión, proyecto, catálogo y conversación son sintéticos.
No son una maqueta ni una comprobación de integración remota.

| Viewport | Panel del chat (ancho) | Navegación / historial | Diálogo centrado |
| --- | --- | --- | --- |
| 1366×768 | ≈868 px | 220 / 224 px | 550×354 px |
| 1440×900 | 942 px | 220 / 224 px | 550×354 px |
| 1920×1080 | 1422 px | 220 / 224 px | 550×354 px |

En los tres tamaños no hay desbordamiento horizontal del documento ni solapes.
El selector de 250 px permanece en la misma fila del encabezado; el modelo y la
disponibilidad se leen también debajo del control cuando su opción se trunca.
El compositor permanece visible al pie y la conversación tiene desplazamiento
propio. En Full HD se conserva la anchura de lectura del contenido, sin estirar
los mensajes a toda la pantalla. El diálogo usa texto legible, botones en una
fila y no necesita desplazamiento interno; no se justificó agrandarlo ni rediseñarlo.
Se comprobó selección Gemini/Terra y se mantuvo la procedencia anterior.

Se reprodujo un único defecto visual al redimensionar desde escritorio a móvil:
el compositor vacío podía conservar una altura de 160 px por medir el ancho antes
de que se plegara el historial. `ChatComposer` ahora observa cambios de ancho del
campo y recalcula su altura en el siguiente cuadro de renderizado, después de
redistribuirse los paneles; ignora cambios de altura y cancela cuadros pendientes
al desmontar para evitar avisos de ciclo del observador. Se verificó que termina en 45 px a 390×844, sin
recargar, tanto desde laptop como desde Full HD. Una prueba de regresión conserva
el borrador y verifica que el ajuste no envía mensajes.

Se repitieron la suite frontend completa (105 pruebas), TypeScript, lint, formato
y build después del ajuste. Sin errores; persiste únicamente el aviso de tamaño
del chunk principal ya documentado. La comprobación previa de configuración de
despliegue (2 pruebas) no se modificó.
La repetición final de los cambios de viewport y selección no registró errores
ni advertencias en la consola del navegador, incluidos avisos de `ResizeObserver`.

Capturas locales conservadas fuera de Git:
`statia-5b-workspace-1366x768.jpg`, `statia-5b-workspace-1440x900.jpg`,
`statia-5b-workspace-terra-1440x900.jpg`, `statia-5b-workspace-1920x1080.jpg`
y diálogos `statia-5b-confirmacion-1366x768.jpg`,
`statia-5b-confirmacion-1440x900.jpg`, `statia-5b-confirmacion-1920x1080.jpg`.

### Aclaración del conteo de archivos

El diff de la rama respecto a `fb73642` contiene **14 archivos versionados**:
11 de implementación/pruebas/configuración frontend y 3 de documentación.
Los **18 archivos editados** de la entrega anterior incluyen además los cuatro
auxiliares locales en `frontend/__qa__/session5b/`: `frame.html`, `index.html`,
`supabase.mjs` y `vite.config.mjs`. Git confirma que estos cuatro están ignorados.
No forman parte de los commits ni de la compilación de producción. Esta revisión
modifica archivos ya existentes y no aumenta el número de archivos del diff.

## Límites y entrega

Terra disponible se comprobó **solo por simulación**, sin llamadas Gemini/OpenAI ni
consumo de créditos. No se accedió a Supabase, Vercel o Render. Las migraciones 007/008
se consideran aplicadas según la confirmación del responsable; no se inspeccionaron remotamente.
No se requieren nuevas migraciones ni ajustes externos para este frontend.

Pendientes relacionados con 5B: recorrido integral con sesión y backend reales por
el responsable, y cualquier validación real de Terra bajo autorización separada.
El backend no expone proveedor/modelo del `retry_turn`; la incompatibilidad se conoce
por su 409 y nunca se intenta inferir o reparar reutilizando el UUID con otro destinatario.
El aviso de tamaño de bundle no impide la compilación; no se amplió esta sesión a optimización general.

Entrega en commits locales convencionales en español: `ea9160a` incluye implementación
y pruebas de 5B; un segundo bloque documenta alcance/validación. La decisión APTO corresponde a abrir el PR
para revisión; no autoriza publicación automática, fusión ni despliegue.
