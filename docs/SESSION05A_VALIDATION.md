# Validación de Sesión 5A

17 de noviembre de 2026. Base `develop@74b9577`, PR #6 fusionado antes de iniciar.
La sesión no hizo solicitudes reales a Gemini/OpenAI, no consumió créditos, no aplicó
migraciones remotas, no desplegó y no modificó frontend ni datos de producción.

## Comprobaciones locales

| Comprobación | Resultado |
| --- | --- |
| Nuevas pruebas de transporte/runtime OpenAI y límite Gemini | 36 aprobadas |
| Nuevas pruebas de selección y conservación de resultados | 17 aprobadas |
| Regresión backend completa, 19 módulos en procesos aislados | 455 aprobadas, sin fallos ni omisiones locales |
| PostgreSQL WASM, migraciones y RLS | 5 aprobadas |
| Frontend sin modificaciones | 68 pruebas y 2 controles de configuración aprobados |
| TypeScript, lint, formato y compilación frontend | Aprobados |
| `scripts/check_analysis_quality.py` | Lint y formato aprobados, 46 archivos |
| Lint de módulos heredados modificados (`E4,E7,E9,F`) | Aprobado |
| `pip check` y compilación de sintaxis Python | Aprobados |
| Diff, secretos y alcance | Sin errores de espacios, credenciales locales ni cambios frontend |

Las 53 pruebas nuevas utilizan respuestas/transportes simulados. Una de ellas ejecuta
el motor Python real con datos sintéticos y persistencia/Auth/Storage controlados antes
de cambiar de proveedor; contrasta resultados, recursos y decisiones. No acredita una
integración remota con proveedores o Supabase.

La prueba SQL instala 001–006, crea historial previo y aplica 007; verifica defaults,
modelo histórico desconocido, RLS entre usuarios, permisos invoker, eventos, replay,
payload/modelo incompatibles y bloqueo durante chat/cálculo. Las cuatro pruebas SQL
previas permanecen aprobadas.

Pytest y Vite requirieron ejecución fuera del sandbox por restricciones locales de
temporales/dependencias. Vite conserva su advertencia previa de chunk superior a
500 kB; la compilación terminó correctamente. Starlette/TestClient mantiene su aviso
de deprecación existente. No se modificaron dependencias para ocultar esos avisos.

Los informes históricos `docs/TERRA*`, los diagnósticos aislados y el motor estadístico
permanecen sin diferencias frente a `develop`. Los logs de las pruebas no se versionan.

## CI y validaciones externas

CI se consultará en el PR hacia `develop`; no confundir estos resultados Windows con
una ejecución Linux remota. El workflow existente descubre automáticamente los dos
módulos Python nuevos y el nuevo test SQL; no requiere secretos ni proveedores remotos.

Queda pendiente aplicar/revisar 007 en el entorno autorizado, verificar aislamiento con
dos cuentas reales y desarrollar el selector frontend. Cualquier prueba real pagada
requiere otra autorización. Terra continúa experimental y deshabilitado por defecto.
Los límites por proceso no equivalen a un presupuesto monetario distribuido y el aviso
descriptivo agrupado no demuestra cobertura exhaustiva de cualquier promesa textual.

Configuración, contratos y riesgos completos: [backend multiproveedor](MULTIPROVIDER_BACKEND.md).
