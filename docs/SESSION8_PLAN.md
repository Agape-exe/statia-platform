# Sesión 08 — plan correctivo

Base verificada: `feat/excel-multihoja`, limpia, con `7d29c61`, `6e0297d`
y `4fa072a`. Trabajo exclusivo en `fix/cierre-validacion-tesis`, creada desde
esa base. La instrucción específica de continuidad prevalece sobre partir de
develop. Sin reset, rebase, publicación, despliegues ni operaciones remotas.

1. Unificar extracción PDF/DOCX con fragmentos, ubicaciones, estados y avisos;
   validar contenedores y XML, acotar recursos y conservar originales privados.
   Rechazar DOC con indicación de conversión, sin conversores del sistema.
2. Recuperar fragmentos según la consulta solo con consentimiento explícito;
   limitar contexto y exigir evidencia documental sin relaciones inventadas.
3. Separar comprensión, consulta documental/metodológica y planificación;
   normalizar únicamente representaciones equivalentes y conservar validadores.
4. Distinguir Contexto confirmado y borrador real, impedir guardados idénticos,
   preservar conflictos y enviar siempre la revisión vigente en tesis.
5. Ocultar trazas técnicas por defecto y aclarar presencia física frente a
   validez sustantiva, sin modificar motor ni resultados históricos.
6. Fixtures diversas, proveedores simulados, regresiones dirigidas y batería
   final backend/frontend/SQL local, calidad, diff y secretos. Informe de cierre
   con limitaciones y validación externa pendiente explícitas.

Necesidad SQL comprobada: `project_files` restringe `file_type` a
CSV/XLSX/JSON/PDF y equipara instrumento a PDF; Storage restringe MIME.
Preparar migración aditiva local, conservando RLS y privacidad. No ejecutarla
en remoto. No cambiar cuotas ni variables reales. Evaluar dependencia XML
pequeña y mantenida; no incorporar OCR ni LibreOffice/antiword.

La evidencia aportada no incluye respuestas JSON ni trazas de proveedores de
los fallos intermitentes. Las causas reproducibles se distinguirán de hipótesis.
