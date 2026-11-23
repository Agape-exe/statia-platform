import io
import json
import zipfile
import csv
import hashlib
from pathlib import Path
from datetime import date

import pytest
from fastapi import HTTPException
from openpyxl import Workbook
from pypdf import PdfWriter

from app.core.config import Settings
from app.services.profiling import inspect_file, safe_name


def xlsx(two_sheets=False):
    workbook = Workbook()
    workbook.active.title = 'Mediciones'
    workbook.active.append(['estudiante_id', 'grupo', 'nota_pretest', 'nota_postest'])
    workbook.active.append([1, 'A', 10, 14])
    workbook.active.append([2, 'B', 11, 15])
    if two_sheets:
        workbook.create_sheet('Instrumento').append(['codigo', 'item'])
    out = io.BytesIO()
    workbook.save(out)
    return out.getvalue()


@pytest.mark.parametrize('data', [b'id,grupo,nota\n1,A,10\n1,A,10\n2,B,\n', b'\xef\xbb\xbfid;grupo;nota\n1;A;10\n1;A;10\n2;B;\n'])
def test_csv_columns_missing_duplicates_and_types(data):
    meta = inspect_file('datos.csv', data, 'dataset', Settings())
    profile = meta['profile']
    assert profile['row_count'] == 3
    assert profile['duplicate_rows'] == 1
    assert profile['missing_count'] == 1
    assert profile['columns'][0]['physical_type'] == 'numeric'
    assert profile['columns'][0]['statistical_type'] == 'identifier'
    assert profile['columns'][2]['statistical_type'] == 'categorical_or_ordinal'
    assert profile['columns'][2]['min'] == 10


def test_xlsx_explicit_sheet_and_profile():
    data = xlsx(True)
    metadata = inspect_file('libro.xlsx', data, 'dataset', Settings())
    assert metadata['sheets'] == ['Mediciones', 'Instrumento']
    assert metadata['needs_sheet_selection']
    selected = inspect_file('libro.xlsx', data, 'dataset', Settings(), 'Mediciones')
    assert selected['profile']['row_count'] == 2
    assert selected['selected_sheet'] == 'Mediciones'
    with pytest.raises(HTTPException) as error:
        inspect_file('libro.xlsx', data, 'dataset', Settings(), 'Ausente')
    assert error.value.status_code == 422


def test_json_sparse_tabular_and_sample():
    data = json.dumps([{'id': 1, 'edad': 18}, {'id': 2, 'grupo': 'B'}]).encode()
    profile = inspect_file('datos.json', data, 'dataset', Settings())['profile']
    assert [c['name'] for c in profile['columns']] == ['id', 'edad', 'grupo']
    assert profile['missing_count'] == 2
    assert profile['samples'][1]['edad'] is None


@pytest.mark.parametrize('name,data,role', [
    ('datos.csv', b'a,a\n1,2', 'dataset'), ('datos.csv', b'a,b\n1,2,3', 'dataset'),
    ('datos.csv', b'a\n\xff', 'dataset'), ('datos.json', b'{"id":1}', 'dataset'),
    ('datos.json', b'[{"obj":{"a":1}}]', 'dataset'), ('datos.json', b'[{"a":NaN}]', 'dataset'),
    ('datos.xlsx', b'invalido', 'dataset'), ('instrumento.pdf', b'invalido', 'instrument'),
    ('datos.exe', b'invalido', 'dataset'), ('datos.csv', b'', 'dataset'),
    ('datos.pdf', b'%PDF-', 'dataset'), ('datos.csv', b'a\n1', 'instrument'),
])
def test_invalid_files(name, data, role):
    with pytest.raises(HTTPException) as caught:
        inspect_file(name, data, role, Settings())
    assert caught.value.status_code == 422


def test_limits_file_rows_columns_cell_expanded():
    with pytest.raises(HTTPException) as caught:
        inspect_file('datos.csv', b'x' * 1025, 'dataset', Settings(max_file_bytes=1024))
    assert caught.value.status_code == 413
    with pytest.raises(HTTPException):
        inspect_file('datos.csv', b'a\n1\n2', 'dataset', Settings(max_rows=1))
    with pytest.raises(HTTPException):
        inspect_file('datos.csv', b'a,b\n1,2', 'dataset', Settings(max_columns=1))
    with pytest.raises(HTTPException):
        inspect_file('datos.csv', b'a\n' + b'x' * 2001, 'dataset', Settings())
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('grande.xml', b'x' * 4000)
    with pytest.raises(HTTPException):
        inspect_file('datos.xlsx', out.getvalue(), 'dataset', Settings(max_expanded_bytes=1024))


def test_pdf_no_text_is_retained_without_ocr():
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    out = io.BytesIO()
    writer.write(out)
    profile = inspect_file('instrumento.pdf', out.getvalue(), 'instrument', Settings())
    assert profile['pages'] == 1
    assert not profile['text_excerpt']
    assert any('OCR' in warning for warning in profile['warnings'])


def test_filename_cannot_escape_path():
    assert safe_name('../../datos.csv') == 'datos.csv'
    assert '/' not in safe_name('..\\..\\año 2026.csv')


@pytest.mark.parametrize('marker', ['NA', 'N/A', 'null', 'NaN', 'None', '<NA>', ''])
def test_numeric_missing_markers_preserve_source_and_infer_number(marker):
    # Una segunda columna evita que un registro vacío se interprete como línea en blanco.
    data = f'masa_g,grupo\n10,A\n{marker},B\n20,A'.encode()
    result = inspect_file('datos.csv', data, 'dataset', Settings())
    column = result['profile']['columns'][0]
    assert column['physical_type'] == 'numeric'
    assert column['source_representation'] == 'csv_text'
    assert column['statistical_type'] == 'quantitative'
    assert column['missing'] == 1 and column['mean'] == 15
    assert data.decode().splitlines()[2] == f'{marker},B'


def test_legitimate_category_na_mixed_empty_ids_and_year():
    data = b'estudiante_id,region,medida,vacia,year\n1,NA,10,,2007\n2,EU,invalido,,2008\n3,NA,20,,2009'
    profile = inspect_file('datos.csv', data, 'dataset', Settings())['profile']
    columns = {c['name']: c for c in profile['columns']}
    assert columns['region']['missing'] == 0
    assert columns['region']['ambiguous_missing'] == {'NA': 2}
    assert columns['region']['unique'] == 2
    assert columns['medida']['inferred_type'] == 'mixed'
    assert columns['medida']['missing'] == 0
    assert columns['medida']['warnings']
    assert columns['vacia']['statistical_type'] == 'unknown'
    assert columns['vacia']['missing'] == 3
    assert columns['estudiante_id']['possible_identifier']
    assert columns['year']['possible_temporal']
    assert 'year' not in profile['numeric_variables']
    assert 'estudiante_id' not in profile['numeric_variables']


def test_configurable_markers_and_explicit_decision_for_categorical_data():
    settings = Settings(missing_value_markers='NA,desconocido', missing_value_overrides={'region': ['NA']})
    profile = inspect_file('datos.csv', b'masa_g,region\n10,NA\ndesconocido,EU\n20,AS', 'dataset', settings)['profile']
    assert [c['missing'] for c in profile['columns']] == [1, 1]
    assert profile['columns'][1]['ambiguous_missing'] == {}


def test_temporal_native_origin_and_invalid_calendar_values():
    book = Workbook()
    book.active.append(['fecha', 'year'])
    book.active.append([date(2020, 1, 1), 2020])
    book.active.append([date(2020, 2, 1), 2020])
    out = io.BytesIO()
    book.save(out)
    profile = inspect_file('fechas.xlsx', out.getvalue(), 'dataset', Settings())['profile']
    assert profile['columns'][0]['source_representation'] == 'native_temporal'
    assert profile['columns'][0]['possible_temporal']
    invalid = inspect_file('fechas.csv', b'fecha\n2020-99-99\n2020-01-01', 'dataset', Settings())['profile']
    assert not invalid['columns'][0]['possible_temporal']


def test_original_penguins_against_independent_reference_without_modifying_bytes():
    data = (Path(__file__).parent / 'fixtures/penguins.csv').read_bytes()
    digest = 'f204db2c753b0937caac3cb35258562c14f073e4bbc76be24b4c51ce22767a93'
    assert hashlib.sha256(data).hexdigest() == digest
    reference = list(csv.DictReader(io.StringIO(data.decode())))
    counts = {name: sum(row[name] == 'NA' for row in reference) for name in reference[0]}
    profile = inspect_file('penguins.csv', data, 'dataset', Settings())['profile']
    assert profile['row_count'] == len(reference) == 344
    assert profile['column_count'] == len(reference[0]) == 8
    for column in profile['columns']:
        if column['name'] in ('bill_length_mm', 'bill_depth_mm', 'flipper_length_mm', 'body_mass_g'):
            assert column['physical_type'] == 'numeric'
            assert column['statistical_type'] == 'quantitative'
            assert column['missing'] == counts[column['name']] == 2
    assert profile['missing_count'] == 8
    assert profile['ambiguous_missing_count'] == counts['sex'] == 11
    confirmed = inspect_file('penguins.csv', data, 'dataset', Settings(missing_value_overrides={'sex': ['NA']}))['profile']
    assert {c['name']: c['missing'] for c in confirmed['columns']} == counts
    assert confirmed['missing_count'] == 19
    assert hashlib.sha256(data).hexdigest() == digest
