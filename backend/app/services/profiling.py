"""Inspección preliminar acotada; nunca altera ni combina los originales."""
import csv
import io
import json
import math
import re
import statistics
from collections import Counter
from datetime import date, datetime
from pathlib import PurePath

from fastapi import HTTPException
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


def temporal_value(value):
    if not re.match(r'^\d{4}-\d{2}-\d{2}(?:T.*)?$', str(value)):
        return False
    try:
        datetime.fromisoformat(str(value))
        return True
    except ValueError:
        return False


def table_profile(headers, records, settings, source='native'):
    if not headers or len(headers) > settings.max_columns:
        invalid(f'La tabla debe tener entre 1 y {settings.max_columns} columnas.')
    headers = [str(h).strip() if h is not None else '' for h in headers]
    if any(not h or len(h) > 240 for h in headers) or len(set(headers)) != len(headers):
        invalid('Las columnas deben tener nombres únicos, no vacíos y de hasta 240 caracteres.')
    rows = []
    origins = [set() for _ in headers]
    for record in records:
        if len(rows) >= settings.max_rows:
            invalid(f'La tabla supera el límite preliminar de {settings.max_rows} filas. Divide el archivo.')
        if len(record) != len(headers):
            invalid('Hay filas con un número de celdas diferente al encabezado.')
        cleaned = [clean(value) for value in record]
        for index, value in enumerate(record):
            if cleaned[index] is not None:
                origins[index].add('native_temporal' if isinstance(value, (date, datetime)) else 'native_boolean' if isinstance(value, bool)
                                   else 'native_numeric' if isinstance(value, (int, float)) else 'native_text')
        rows.append(cleaned)
    if not rows:
        invalid('La tabla no contiene registros.')
    columns = []
    marker_tokens = {v.strip().casefold() for v in settings.missing_value_markers.split(',') if v.strip()}
    for i, name in enumerate(headers):
        original = [r[i] for r in rows]
        present = [v for v in original if v is not None]
        explicit_tokens = {v.casefold() for v in settings.missing_value_overrides.get(name, [])}
        candidates = Counter(v for v in present if isinstance(v, str) and v.casefold() in marker_tokens | explicit_tokens)
        ordinary = [v for v in present if not (isinstance(v, str) and v in candidates)]
        numeric_evidence = len(ordinary) >= 2 and all(numeric(v) is not None for v in ordinary)
        # Solo inferir ausencia en columnas por lo demás numéricas. En texto, NA se conserva.
        inferred_tokens = {v for v in candidates if numeric_evidence or v.casefold() in explicit_tokens}
        values = [v for v in present if v not in inferred_tokens]
        ambiguous = {v: count for v, count in candidates.items() if v not in inferred_tokens}
        inferred_missing = sum(candidates[v] for v in inferred_tokens)
        counts = Counter((type(v).__name__, str(v)) for v in values)
        unique = len(counts)
        numbers = [numeric(v) for v in values]
        is_number = bool(values) and all(v is not None for v in numbers)
        year = bool(values) and bool(re.search(r'(^|_)(year|año|anio)(_|$)', name, re.I)) and is_number and all(v.is_integer() and 1000 <= v <= 3000 for v in numbers)
        temporal = year or (bool(values) and all(temporal_value(v) for v in values))
        identifier = bool(values) and (bool(re.search(r'(^id$|_id$|^id_|identificador|c[oó]digo|dni)', name, re.I)) or
            all(re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', str(v), re.I) for v in values))
        physical = 'empty' if not values else 'boolean' if all(isinstance(v, bool) for v in values) else 'numeric' if is_number else 'text'
        mixed = bool(values) and any(numeric(v) is not None for v in values) and not is_number
        measurement = bool(re.search(r'(_mm|_cm|_kg|_g|length|depth|mass|longitud|masa|peso)(_|$)', name, re.I))
        statistical = ('identifier' if identifier else 'temporal' if temporal else 'unknown' if not values else 'mixed' if mixed
                       else 'quantitative' if is_number and (measurement or unique > 12) else 'categorical_or_ordinal' if unique <= 12 else 'categorical')
        column = {'name': name, 'physical_type': physical, 'statistical_type': statistical,
                  'source_representation': 'csv_text' if source == 'csv' else next(iter(origins[i])) if len(origins[i]) == 1 else 'native_mixed' if origins[i] else 'empty',
                  'inferred_type': 'mixed' if mixed else physical,
                  'semantic_hint': 'Identificador probable; confirmar su significado.' if identifier else 'Significado por confirmar con el usuario.',
                  'missing': len(rows) - len(values), 'unique': unique, 'possible_identifier': identifier,
                  'missing_confirmed': len(rows) - len(present), 'missing_inferred': inferred_missing,
                  'ambiguous_missing': ambiguous, 'missing_markers': dict(candidates),
                  'warnings': ([f'{name}: se interpretaron {inferred_missing} marcadores como ausencia para el perfil, sin modificar el original.'] if inferred_missing else [])
                              + ([f'{name}: {sum(ambiguous.values())} cadenas podrían indicar ausencia o categorías legítimas; se conservan hasta confirmar su significado.'] if ambiguous else [])
                              + ([f'{name}: mezcla números y texto no interpretable como número; no se convirtió ni descartó ese texto.'] if mixed else []),
                  'possible_temporal': temporal, 'sensitive': bool(SENSITIVE.search(name)),
                  'distribution': [{'value': value[:120], 'count': count} for (_, value), count in counts.most_common(5)]}
        if unique <= 20 and not column['sensitive'] and not identifier:
            column['levels'] = [{'value': value, 'count': count} for (_, value), count in counts.items()]
        if is_number:
            column.update(min=min(numbers), max=max(numbers), mean=statistics.fmean(numbers))
        elif temporal:
            column.update(min=min(str(v) for v in values), max=max(str(v) for v in values))
        columns.append(column)
    return {'profile_version': 2, 'row_count': len(rows), 'column_count': len(headers), 'columns': columns,
            'missing_count': sum(c['missing'] for c in columns),
            'ambiguous_missing_count': sum(sum(c['ambiguous_missing'].values()) for c in columns),
            'duplicate_rows': len(rows) - len({tuple((type(v).__name__, str(v)) for v in r) for r in rows}),
            'numeric_variables': [c['name'] for c in columns if c['physical_type'] == 'numeric' and not c['possible_identifier'] and not c['possible_temporal']],
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
            from app.services.workbook import inspect_workbook
            return inspect_workbook(data, settings, sheet)
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
                profile = table_profile(headers, iterator, settings, 'csv')
                names, selected = ['tabla'], 'tabla'
            else:
                records = json.loads(text, parse_constant=lambda x: invalid('El JSON contiene valores no finitos.'))
                if not isinstance(records, list) or not records or not all(isinstance(r, dict) for r in records):
                    invalid('El JSON debe ser un array no vacío de objetos tabulares.')
                if len(records) > settings.max_rows:
                    invalid(f'El JSON supera {settings.max_rows} filas.')
                headers = list(dict.fromkeys(k for record in records for k in record))
                profile = table_profile(headers, ([record.get(h) for h in headers] for record in records), settings, 'json')
                names, selected = ['tabla'], 'tabla'
        return {'file_type': extension, 'sheets': names, 'selected_sheet': selected,
                'needs_sheet_selection': False, 'profile': profile,
                'warnings': ['Los tipos estadísticos y semánticos son hipótesis, no decisiones metodológicas. No se han corregido faltantes ni duplicados.']
                            + [warning for column in profile['columns'] for warning in column['warnings']]}
    except HTTPException:
        raise
    except Exception:
        invalid('No se pudo interpretar el archivo. Comprueba su formato, estructura y límites.')
