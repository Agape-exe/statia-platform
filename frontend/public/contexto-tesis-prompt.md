# Prompt maestro — Contexto de tesis de Statia v1

Transforma únicamente la información de investigación que yo proporcione a continuación en un objeto JSON válido para Statia. Devuelve solo JSON, sin bloques Markdown ni comentarios.

No inventes información ausente, hipótesis, variables, muestras, instrumentos o diseños. No supongas una disciplina, paradigma o estructura metodológica universal. Usa null para un texto desconocido y [] para listas sin información; ausencia de hipótesis no es un error. Conserva los matices e incertidumbres del documento. Si dos afirmaciones se contradicen, describe la contradicción en additional_information, sin resolverla por tu cuenta. No incluyas datos personales, credenciales ni registros de participantes.

Usa exactamente los campos del contrato de abajo. Textos: máximo 2000 caracteres por campo. Listas: hasta 20 textos de 1–500 caracteres. En variables, describe nombre y significado/escala/rol solo cuando estén aportados, sin inferir una correspondencia con columnas de datasets. additional_fields admite hasta 20 nombres (1–80 caracteres), con valores de texto (hasta 2000) o null para elementos propios de la disciplina. No agregues claves fuera del contrato. Mantén el documento completo dentro de 16000 caracteres. No cambies el valor numérico schema_version.

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

Información proporcionada por mí:
[Pegar aquí los datos metodológicos, sin datos personales ni secretos.]

La salida es un borrador: debo importarla, revisar cada campo y confirmar su guardado en Statia. No afirmes que se guardó o se validó metodológicamente.
