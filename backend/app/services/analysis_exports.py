"""Artefactos en memoria; se suben completos antes de finalizar la transacción."""

import csv
import hashlib
import io
import json
import zipfile


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2).encode("utf-8")


def csv_value(value):
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, allow_nan=False)
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def table_csv(table):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\r\n")
    writer.writerow([csv_value(column) for column in table["columns"]])
    writer.writerows([[csv_value(row.get(column)) for column in table["columns"]] for row in table["rows"]])
    return stream.getvalue().encode("utf-8-sig")


def report(result):
    lines = [
        f"# {result['title']}",
        "",
        f"Ejecución: {result['run_id']}",
        f"Fecha UTC: {result['created_at']}",
        f"Estado: {result['status']}",
        "",
        result["summary"],
        "",
        "Las cifras completas están en resultados.json y los CSV; el texto usa redondeo de presentación.",
        "",
    ]
    for component in result["components"]:
        lines.extend(
            [
                f"## {component['title']}",
                f"Estado: {component['status']}",
                f"Ámbito: {json.dumps(component['scope'], ensure_ascii=False)}",
                "",
                component["interpretation"],
                "",
            ]
        )
        if component["error"]:
            lines.extend([component["error"], ""])
        lines.extend(["### Muestra y exclusiones", json.dumps(component["sample"], ensure_ascii=False), ""])
        for assumption in component["assumptions"]:
            lines.append(f"- {assumption['name']} ({assumption['status']}): {assumption['detail']}")
        lines.extend(["", *[f"- {warning}" for warning in component["warnings"]], ""])
        for item in component["tables"]:

            def cell(v):
                if v is None:
                    return "No disponible"
                if isinstance(v, float):
                    return f"{v:.6g}"
                return str(v).replace("|", "\\|").replace("\n", " ")

            lines.extend(
                [
                    f"### {item['title']}",
                    "| " + " | ".join(map(cell, item["columns"])) + " |",
                    "| " + " | ".join(["---"] * len(item["columns"])) + " |",
                ]
            )

            def formatted(row, column):
                value = row.get(column)
                is_p = (
                    column.lower() == "p"
                    or column.lower().startswith("p ")
                    or (column == "Valor" and row.get("Medida") == "p")
                )
                return "< 0.001" if is_p and isinstance(value, (int, float)) and value < 0.001 else cell(value)

            lines.extend("| " + " | ".join(formatted(row, c) for c in item["columns"]) + " |" for row in item["rows"])
            lines.append("")
        lines.extend(f"![Gráfico calculado]({path})" for path in component["charts"])
    return "\n".join(lines).encode("utf-8")


def build_exports(result, charts):
    resources = {name: (content, "image/png") for name, content in charts.items()}
    resources["resultados.json"] = (json_bytes(result), "application/json")
    resources["resumen.md"] = (report(result), "text/markdown")
    resources["metodologia/especificacion.json"] = (json_bytes(result["specification"]), "application/json")
    resources["metodologia/plan_aceptado.json"] = (json_bytes(result["plan_snapshot"]), "application/json")
    for i, component in enumerate(result["components"], 1):
        for j, item in enumerate(component["tables"], 1):
            resources[f"tablas/componente_{i}_tabla_{j}.csv"] = (table_csv(item), "text/csv")
    manifest = {
        "schema_version": 1,
        "run_id": result["run_id"],
        "date": result["created_at"],
        "status": result["status"],
        "procedures": [c["method"] for c in result["components"]],
        "files": result["files"],
        "dependencies": result["dependencies"],
        "resources": [
            {"name": name, "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "mime_type": mime}
            for name, (data, mime) in resources.items()
        ],
        "notes": "No contiene datasets originales. El manifiesto no se incluye a sí mismo ni al ZIP en sus hashes.",
    }
    resources["manifiesto.json"] = (json_bytes(manifest), "application/json")
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=4) as output:
        for name, (data, _) in resources.items():
            output.writestr(name, data)
    resources["resultados_analisis.zip"] = (archive.getvalue(), "application/zip")
    return resources
