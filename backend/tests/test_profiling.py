import io
import json
import zipfile

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
    assert 'OCR' in profile['warnings'][0]


def test_filename_cannot_escape_path():
    assert safe_name('../../datos.csv') == 'datos.csv'
    assert '/' not in safe_name('..\\..\\año 2026.csv')
