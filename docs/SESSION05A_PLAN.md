# Sesión 5A: integración backend multiproveedor

Base verificada: `develop` en `74b9577`, con PR #6 fusionado el 17 de noviembre de 2026.
Rama: `feat/integracion-multiproveedor-backend`. Checkout inicial limpio; actualización por avance rápido.

1. Inspeccionar Gemini, su protocolo, contexto, contratos, corrección semántica, RPC/RLS,
   ejecución Python y evidencia sanitizada A/D/M/I del PR #6.
2. Implementar Responses API con el transporte estricto validado, modelo fijo Terra,
   habilitación explícita, cancelación, tiempos, cuotas locales, métricas y diagnósticos seguros.
3. Añadir selección cerrada Gemini/OpenAI por conversación y procedencia por turno/respuesta.
   Preservar Gemini predeterminado, compatibilidad histórica e idempotencia sin fallback.
4. Añadir migración aditiva con RPC invoker y serialización bajo RLS, sin aplicar en remoto.
5. Advertir determinísticamente del alcance descriptivo agrupado detectado en I,
   sin cambiar el motor, originales o resultados históricos.
6. Probar transporte y orquestación simulados, migraciones/RLS locales y regresiones;
   revisar diff, secretos, lint/formato, TypeScript y compilación.
7. Documentar configuración, riesgos y contrato de la siguiente sesión frontend;
   crear PR hacia `develop`, consultar CI y detenerse sin fusionar ni desplegar.

No se autorizan llamadas reales a modelos, consumo de créditos, cambios frontend,
despliegues ni escrituras de datos productivos. Las pruebas remotas de Supabase y
proveedores quedan pendientes y no equivalen a los dobles automatizados.
