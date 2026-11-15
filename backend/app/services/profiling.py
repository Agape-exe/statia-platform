"""Inspección preliminar acotada; nunca altera ni combina los originales."""
import csv
import io
import json
import math
import re
import statistics
import zipfile
from collections import Counter
from datetime import date, datetime
from pathlib import PurePath

from fastapi import HTTPException
from openpyxl import load_workbook
from pypdf import PdfReader, apply_configuration

from app.core.config import Settings

MIMES = {'csv': 'text/csv', 'xlsx': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
         'json': 'application/json', 'pdf': 'application/pdf'}
SENSITIVE = re.compile(r'(^id$|_id$|^id_|nombre|name|apellido|correo|email|tel[eé]fono|phone|dni|documento|password|contrase[ñn]a|direcci[oó]n)', re.I)


def invalid(message):
    raise HTTPException(422, message)


def safe_name(name):
    name = name.replace('\\', '/').split('/')[-1]
    return re.sub(r'[^a-zA-Z0-9._-]', '_', name)[-120:] or 'archivo'


def clean(value):
    if value is None or value == '':
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, str):
        if len(value) > 2000:
            invalid('Una celda supera los 2000 caracteres permitidos para la inspección preliminar.')
        return value.strip() or None
    if not isinstance(value, (str, int, float, bool)):
        invalid('El JSON debe contener valores escalares, sin objetos ni arrays anidados.')
    return value


def numeric(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        result = float(value)
        return result if math.isfinite(result) else None
    except (ValueError, TypeError, OverflowError):
        return None


def table_profile(headers, records, settings):
    if not headers or len(headers) > settings.max_columns:
        invalid(f'La tabla debe tener entre 1 y {settings.max_columns} columnas.')
    headers = [str(h).strip() if h is not None else '' for h in headers]
    if any(not h or len(h) > 240 for h in headers) or len(set(headers)) != len(headers):
        invalid('Las columnas deben tener nombres únicos, no vacíos y de hasta 240 caracteres.')
    rows = []
    for record in records:
        if len(rows) >= settings.max_rows:
            invalid(f'La tabla supera el límite preliminar de {settings.max_rows} filas. Divide el archivo.')
        if len(record) != len(headers):
            invalid('Hay filas con un número de celdas diferente al encabezado.')
        rows.append([clean(value) for value in record])
    if not rows:
        invalid('La tabla no contiene registros.')
    columns = []
    for i, name in enumerate(headers):
        values = [r[i] for r in rows if r[i] is not None]
        counts = Counter((type(v).__name__, str(v)) for v in values)
        unique = len(counts)
        numbers = [numeric(v) for v in values]
        is_number = bool(values) and all(v is not None for v in numbers)
        temporal = bool(values) and all(re.match(r'^\d{4}-\d{2}-\d{2}(?:T.*)?$', str(v)) for v in values)
        identifier = bool(values) and (bool(re.search(r'(^id$|_id$|^id_|identificador|c[oó]digo|dni)', name, re.I)) or
                                               (unique == len(rows) and not is_number and not temporal))
        physical = 'empty' if not values else 'boolean' if all(isinstance(v, bool) for v in values) else 'numeric' if is_number else 'text'
        statistical = 'identifier' if identifier else 'temporal' if temporal else 'categorical_or_ordinal' if unique <= 12 else 'quantitative' if is_number else 'categorical'
        column = {'name': name, 'physical_type': physical, 'statistical_type': statistical,
                  'semantic_hint': 'Identificador probable; confirmar su significado.' if identifier else 'Significado por confirmar con el usuario.',
                  'missing': len(rows) - len(values), 'unique': unique, 'possible_identifier': identifier,
                  'possible_temporal': temporal, 'sensitive': bool(SENSITIVE.search(name)),
                  'distribution': [{'value': value[:120], 'count': count} for (_, value), count in counts.most_common(5)]}
        if is_number:
            column.update(min=min(numbers), max=max(numbers), mean=statistics.fmean(numbers))
        elif temporal:
            column.update(min=min(str(v) for v in values), max=max(str(v) for v in values))
        columns.append(column)
    return {'row_count': len(rows), 'column_count': len(headers), 'columns': columns,
            'missing_count': sum(c['missing'] for c in columns),
            'duplicate_rows': len(rows) - len({tuple((type(v).__name__, str(v)) for v in r) for r in rows}),
            'numeric_variables': [c['name'] for c in columns if c['physical_type'] == 'numeric'],
            'categorical_variables': [c['name'] for c in columns if c['statistical_type'] in ('categorical', 'categorical_or_ordinal')],
            'possible_identifiers': [c['name'] for c in columns if c['possible_identifier']],
            'possible_temporal_variables': [c['name'] for c in columns if c['possible_temporal']],
            'samples': [dict(zip(headers, r)) for r in rows[:3]]}


def inspect_file(name: str, data: bytes, role: str, settings: Settings, sheet: str | None = None):
    with apply_configuration(zlib_maximum_output_length=settings.max_expanded_bytes,
                             array_based_stream_maximum_output_length=settings.max_expanded_bytes,
                             lzw_maximum_output_length=settings.max_expanded_bytes,
                             maximum_declared_stream_length=settings.max_expanded_bytes,
                             run_length_maximum_output_length=settings.max_expanded_bytes,
                             stream_decoding_work_maximum_length=settings.max_expanded_bytes,
                             page_tree_maximum_entries=100, page_tree_maximum_page_entries=100,
                             stream_parsing_work_maximum_count=200000, xform_maximum_invocations_per_extraction=50):
        return _inspect_file(name, data, role, settings, sheet)


def _inspect_file(name: str, data: bytes, role: str, settings: Settings, sheet: str | None = None):
    if not data:
        invalid('El archivo está vacío.')
    if len(data) > settings.max_file_bytes:
        raise HTTPException(413, f'El archivo supera el límite de {settings.max_file_bytes // 1048576} MB.')
    extension = PurePath(name).suffix.lower().lstrip('.')
    if extension not in MIMES or (role == 'instrument') != (extension == 'pdf'):
        invalid('Usa CSV, XLSX o JSON para datasets, y PDF para instrumentos.')
    try:
        if extension == 'pdf':
            if not data.startswith(b'%PDF-'):
                invalid('El archivo no es un PDF válido.')
            reader = PdfReader(io.BytesIO(data))
            if reader.is_encrypted:
                invalid('El PDF está cifrado. Adjunta una copia sin contraseña.')
            if len(reader.pages) > 80:
                invalid('El instrumento supera las 80 páginas permitidas en la inspección preliminar.')
            texts, expanded = [], 0
            for page in reader.pages:
                # Primero comprobar los streams para acotar PDFs comprimidos.
                contents = page.get_contents()
                expanded += len(contents.get_data()) if contents else 0
                if expanded > settings.max_expanded_bytes:
                    invalid('El contenido expandido del PDF supera el límite preliminar.')
                if sum(len(t) for t in texts) < 16000:
                    texts.append((page.extract_text() or '')[:16000])
            text = '\n'.join(texts)[:16000]
            return {'file_type': extension, 'sheets': [], 'text_excerpt': text, 'pages': len(reader.pages),
                    'warnings': [] if text.strip() else ['El PDF no contiene texto extraíble. Se conserva el archivo; no se realiza OCR.']}
        if extension == 'xlsx':
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                if sum(x.file_size for x in archive.infolist()) > settings.max_expanded_bytes or len(archive.infolist()) > 500:
                    invalid('El XLSX supera el tamaño expandido o la cantidad de entradas permitida.')
            book = load_workbook(io.BytesIO(data), read_only=True, data_only=True, keep_links=False)
            try:
                names = book.sheetnames
                if len(names) > 30:
                    invalid('El libro supera las 30 hojas permitidas.')
                if sheet is None and len(names) > 1:
                    return {'file_type': extension, 'sheets': names, 'selected_sheet': None, 'needs_sheet_selection': True}
                selected = sheet or names[0]
                if selected not in names:
                    invalid('La hoja seleccionada no existe en el libro.')
                tab = book[selected]
                if (tab.max_row or 0) > settings.max_rows + 1 or (tab.max_column or 0) > settings.max_columns:
                    invalid('La hoja supera los límites preliminares de filas o columnas.')
                iterator = tab.iter_rows(values_only=True)
                headers = next(iterator, [])
                profile = table_profile(headers, iterator, settings)
            finally:
                book.close()
        else:
            try:
                text = data.decode('utf-8-sig')
            except UnicodeDecodeError:
                invalid('No se pudo leer la codificación. Guarda el archivo como UTF-8 o UTF-8 con BOM.')
            if extension == 'csv':
                try:
                    delimiter = csv.Sniffer().sniff(text[:16000], delimiters=',;\t').delimiter
                except csv.Error:
                    delimiter = ';' if text.splitlines()[0].count(';') > text.splitlines()[0].count(',') else ','
                iterator = csv.reader(io.StringIO(text), delimiter=delimiter, strict=True)
                headers = next(iterator, [])
                profile = table_profile(headers, iterator, settings)
                names, selected = ['tabla'], 'tabla'
            else:
                records = json.loads(text, parse_constant=lambda x: invalid('El JSON contiene valores no finitos.'))
                if not isinstance(records, list) or not records or not all(isinstance(r, dict) for r in records):
                    invalid('El JSON debe ser un array no vacío de objetos tabulares.')
                if len(records) > settings.max_rows:
                    invalid(f'El JSON supera {settings.max_rows} filas.')
                headers = list(dict.fromkeys(k for record in records for k in record))
                profile = table_profile(headers, ([record.get(h) for h in headers] for record in records), settings)
                names, selected = ['tabla'], 'tabla'
        return {'file_type': extension, 'sheets': names, 'selected_sheet': selected,
                'needs_sheet_selection': False, 'profile': profile,
                'warnings': ['Los tipos estadísticos y semánticos son hipótesis, no decisiones metodológicas. No se han corregido faltantes ni duplicados.']}
    except HTTPException:
        raise
    except Exception:
        invalid('No se pudo interpretar el archivo. Comprueba su formato, estructura y límites.')
