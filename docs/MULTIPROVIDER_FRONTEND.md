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
| `npm test` | 104 pruebas, 8 archivos, todas correctas; 68 previas y 36 añadidas |
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
