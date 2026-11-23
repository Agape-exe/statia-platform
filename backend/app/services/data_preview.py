"""Lectura paginada de originales. No perfila, transforma, ejecuta fórmulas ni llama IA."""

import csv
import io
import json
import math
import zipfile
from datetime import date, datetime

from fastapi import HTTPException
from openpyxl import load_workbook

from app.services.workbook import validate_archive


def invalid(message):
    raise HTTPException(422, message)


def cell(value):
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and not math.isfinite(value):
        invalid("El archivo contiene números no finitos.")
    if not isinstance(value, (str, int, float)):
        invalid("El JSON debe contener valores escalares, sin objetos ni arrays anidados.")
    return str(value)


def preview_rows(file, data, settings, offset, limit, sheet=None):
    if not data or len(data) > settings.max_file_bytes:
        raise HTTPException(413, "El original supera el límite permitido para consultar registros.")
    if file["file_role"] != "dataset" or file["file_type"] not in {"csv", "xlsx", "json"}:
        invalid("Ver datos está disponible para datasets CSV, XLSX y JSON tabular.")
    book = None
    try:
        kind = file["file_type"]
        sheet = sheet if sheet is not None else file["metadata"].get("selected_sheet")
        if kind == "xlsx":
            if not sheet:
                invalid("Selecciona una hoja del XLSX en el asistente antes de ver sus datos.")
            validate_archive(data, settings)
            book = load_workbook(io.BytesIO(data), read_only=True, data_only=False, keep_links=False)
            if len(book.sheetnames) > 30:
                invalid("El libro supera las 30 hojas permitidas.")
            if sheet not in book.sheetnames:
                invalid("La hoja seleccionada no existe en el original.")
            tab = book[sheet]
            if (tab.max_row or 0) > settings.max_rows + 1 or (tab.max_column or 0) > settings.max_columns:
                invalid("La hoja supera los límites de filas o columnas.")
            iterator = tab.iter_rows(values_only=True)
            headers = list(next(iterator, []))
        elif kind == "csv":
            if sheet not in (None, "tabla"):
                invalid("La hoja solicitada no existe en esta tabla.")
            text = data.decode("utf-8-sig")
            try:
                delimiter = csv.Sniffer().sniff(text[:16000], delimiters=",;\t").delimiter
            except csv.Error:
                delimiter = ";" if text.splitlines()[0].count(";") > text.splitlines()[0].count(",") else ","
            iterator = csv.reader(io.StringIO(text), delimiter=delimiter, strict=True)
            headers = next(iterator, [])
        else:
            if sheet not in (None, "tabla"):
                invalid("La hoja solicitada no existe en esta tabla.")
            # Conservar la representación de números JSON sin pérdida de precisión JS.
            objects = json.loads(
                data.decode("utf-8-sig"),
                parse_float=str,
                parse_int=str,
                parse_constant=lambda _: invalid("El JSON contiene números no finitos."),
            )
            if not isinstance(objects, list) or not objects or not all(isinstance(row, dict) for row in objects):
                invalid("El JSON debe ser un array no vacío de objetos tabulares.")
            if len(objects) > settings.max_rows:
                invalid("El JSON supera el límite de filas.")
            headers = list(dict.fromkeys(key for row in objects for key in row))
            iterator = ([row.get(h) for h in headers] for row in objects)
        if not headers or len(headers) > settings.max_columns:
            invalid("El original no tiene encabezados válidos o supera el límite de columnas.")
        columns = [cell(h) for h in headers]
        if any(h is None or not h.strip() or len(h) > 240 for h in columns) or len(
            set(h.strip() for h in columns)
        ) != len(columns):
            invalid("Los encabezados deben ser únicos y no vacíos.")
        rows, total = [], 0
        for row in iterator:
            total += 1
            if total > settings.max_rows or len(row) != len(columns):
                invalid("El original supera el límite de filas o contiene filas de distinto ancho.")
            values = [cell(v) for v in row]
            if any(v is not None and len(v) > 2000 for v in values):
                invalid("Una celda supera el límite de longitud permitido.")
            if offset <= total - 1 < offset + limit:
                rows.append(values)
        return {
            "columns": columns,
            "rows": rows,
            "offset": offset,
            "limit": limit,
            "total_rows": total,
            "has_more": offset + len(rows) < total,
            "sheet": sheet,
        }
    except HTTPException:
        raise
    except (
        ValueError,
        TypeError,
        KeyError,
        IndexError,
        OSError,
        csv.Error,
        zipfile.BadZipFile,
        SyntaxError,
        RecursionError,
        EOFError,
    ):
        invalid("No se pudo leer el original. Comprueba su formato y hoja seleccionada.")
    finally:
        if book is not None:
            book.close()
