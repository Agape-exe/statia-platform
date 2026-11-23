"""Perfiles independientes en una sola apertura incremental del libro, sin uniones."""

import io
import zipfile

from fastapi import HTTPException
from openpyxl import load_workbook


def validate_archive(data, settings):
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        if len(entries) > 500 or sum(x.file_size for x in entries) > settings.max_expanded_bytes:
            raise HTTPException(422, "El XLSX supera el tamaño expandido o la cantidad de entradas permitida.")


def inspect_workbook(data, settings, sheet=None):
    from app.services.profiling import table_profile

    validate_archive(data, settings)
    book = load_workbook(io.BytesIO(data), read_only=True, data_only=True, keep_links=False)
    try:
        names = book.sheetnames
        if len(names) > 30:
            raise HTTPException(422, "El libro supera las 30 hojas permitidas.")
        if sheet is not None and sheet not in names:
            raise HTTPException(422, "La hoja seleccionada no existe en el libro.")
        profiles = []
        # Presupuesto agregado, coherente con las 400 000 celdas del motor.
        remaining = min(400000, settings.max_rows * settings.max_columns)
        # La revalidación de una hoja explícita (preparación/ejecución histórica)
        # no necesita volver a perfilar todas las demás.
        for name in names if sheet is None else [sheet]:
            tab = book[name]
            entry = {"sheet": name, "status": "unavailable", "warnings": []}
            try:
                if (tab.max_row or 0) > settings.max_rows + 1 or (tab.max_column or 0) > settings.max_columns:
                    raise HTTPException(422, "La hoja supera los límites preliminares de filas o columnas.")
                if max(0, (tab.max_row or 0) - 1) * (tab.max_column or 0) > remaining:
                    raise HTTPException(422, "La hoja supera el límite agregado de celdas para examinar el libro.")
                iterator = tab.iter_rows(values_only=True)
                headers = next(iterator, [])

                def records():
                    nonlocal remaining
                    for record in iterator:
                        remaining -= max(1, len(record))
                        if remaining < 0:
                            raise HTTPException(422, "Se agotó el límite agregado de celdas para examinar el libro.")
                        yield record

                if remaining < 0:
                    raise HTTPException(422, "Se agotó el límite agregado de celdas para examinar el libro.")
                entry["profile"] = table_profile(headers, records(), settings, "xlsx")
                entry["status"] = "available"
                entry["warnings"] = [warning for c in entry["profile"]["columns"] for warning in c["warnings"]]
            except HTTPException as exc:
                entry["warnings"] = [str(exc.detail)]
            profiles.append(entry)
        selected = sheet if sheet is not None else names[0] if len(names) == 1 else None
        metadata = {
            "file_type": "xlsx",
            "sheets": names,
            "selected_sheet": selected,
            "needs_sheet_selection": selected is None,
            "workbook_profile_version": 1,
            "sheet_profiles": profiles,
            "warnings": [
                "Los tipos son tentativos. Las hojas se examinan por separado; no se combinan ni se presupone correspondencia entre filas."
            ],
        }
        if selected is not None:
            metadata = select_profile(metadata, selected)
        if sheet is not None:
            metadata.pop("sheet_profiles")
            metadata.pop("workbook_profile_version")
        return metadata
    finally:
        book.close()


def select_profile(metadata, sheet):
    entry = next((p for p in metadata.get("sheet_profiles", []) if p["sheet"] == sheet), None)
    if entry is None:
        raise HTTPException(422, "La hoja seleccionada no existe en el libro.")
    if entry["status"] != "available":
        raise HTTPException(422, "No se puede perfilar esta hoja: " + " ".join(entry["warnings"]))
    sheet_warnings = {warning for item in metadata.get("sheet_profiles", []) for warning in item["warnings"]}
    return {
        **metadata,
        "selected_sheet": sheet,
        "needs_sheet_selection": False,
        "profile": entry["profile"],
        "warnings": list(
            dict.fromkeys([*(w for w in metadata.get("warnings", []) if w not in sheet_warnings), *entry["warnings"]])
        ),
    }
