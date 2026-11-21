"""Extracción documental acotada. Nunca ejecuta contenido ni resuelve recursos externos."""

import io
import re
import zipfile
from pathlib import PurePosixPath

from defusedxml.ElementTree import fromstring
from fastapi import HTTPException
from pypdf import PdfReader, apply_configuration

MAX_TEXT = 240_000
MAX_FRAGMENTS = 600
FRAGMENT_SIZE = 1400
WORD_NS = {
    "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "http://purl.oclc.org/ooxml/wordprocessingml/main",
}
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"


def invalid(message):
    raise HTTPException(422, message)


def xml(data):
    return fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)


def paragraph_nodes(paragraph, namespace):
    pending = list(reversed(list(paragraph)))
    while pending:
        node = pending.pop()
        if node.tag == f"{{{namespace}}}p":
            continue  # Los cuadros con párrafos anidados se recuperan por separado.
        yield node
        pending.extend(reversed(list(node)))


class Extraction:
    def __init__(self, extension):
        self.extension = extension
        self.fragments = []
        self.chars = 0
        self.truncated = False
        self.partial = False
        self.warnings = []

    def add(self, text, location):
        text = text.strip()
        for start in range(0, len(text), FRAGMENT_SIZE - 200):
            piece = text[start : start + FRAGMENT_SIZE]
            remaining = MAX_TEXT - self.chars
            if remaining <= 0 or len(self.fragments) >= MAX_FRAGMENTS:
                self.truncated = True
                return
            if len(piece) > remaining:
                self.truncated = True
            piece = piece[:remaining]
            self.fragments.append({"location": location, "offset": start, "text": piece})
            self.chars += len(piece)
            if start + FRAGMENT_SIZE >= len(text):
                break

    def result(self, **metadata):
        if self.truncated:
            self.warnings.append("Extracción parcial: se alcanzó el límite de texto o fragmentos recuperables.")
        if not self.fragments:
            self.warnings.append(
                "No se recuperó texto accesible. No se realiza OCR ni se interpreta texto de imágenes."
            )
        return {
            "file_type": self.extension,
            "sheets": [],
            "instrument_extraction_version": 1,
            "extraction_status": "no_text"
            if not self.fragments
            else "partial"
            if self.truncated or self.partial
            else "extracted",
            "extracted_chars": self.chars,
            "fragments": self.fragments,
            # Vista previa compatible; la recuperación utiliza todos los fragmentos conservados.
            "text_excerpt": "\n".join(f["text"] for f in self.fragments)[:16000],
            "warnings": self.warnings,
            **metadata,
        }


def extract_pdf(data, settings):
    if not data.startswith(b"%PDF-"):
        invalid("El archivo no es un PDF válido.")
    extraction = Extraction("pdf")
    extraction.warnings.append(
        "El orden de lectura del PDF es aproximado; tablas, columnas e imágenes pueden perder estructura."
    )
    with apply_configuration(
        zlib_maximum_output_length=settings.max_expanded_bytes,
        array_based_stream_maximum_output_length=settings.max_expanded_bytes,
        lzw_maximum_output_length=settings.max_expanded_bytes,
        maximum_declared_stream_length=settings.max_expanded_bytes,
        run_length_maximum_output_length=settings.max_expanded_bytes,
        stream_decoding_work_maximum_length=settings.max_expanded_bytes,
        # Son entradas del árbol/diccionarios, no cantidad de páginas.
        page_tree_maximum_entries=4096,
        page_tree_maximum_page_entries=4096,
        stream_parsing_work_maximum_count=200000,
        xform_maximum_invocations_per_extraction=50,
    ):
        reader = PdfReader(io.BytesIO(data), strict=True)
        if reader.is_encrypted:
            invalid("El PDF está cifrado. Adjunta una copia sin contraseña.")
        if len(reader.pages) > 80:
            invalid("El instrumento supera las 80 páginas permitidas.")
        expanded, no_text, failed = 0, [], []
        for number, page in enumerate(reader.pages, 1):
            contents = page.get_contents()
            expanded += len(contents.get_data()) if contents else 0
            if expanded > settings.max_expanded_bytes:
                invalid("El contenido expandido del PDF supera el límite preliminar.")
            try:
                text = page.extract_text() or ""
            except Exception:
                failed.append(number)
                extraction.partial = True
                continue
            if not text.strip():
                no_text.append(number)
                extraction.partial = True
            extraction.add(text, f"Página {number}")
        if no_text:
            extraction.warnings.append(
                "Páginas sin texto accesible: " + ", ".join(map(str, no_text)) + ". Pueden requerir OCR, no disponible."
            )
        if failed:
            extraction.warnings.append("No se pudo extraer texto de las páginas: " + ", ".join(map(str, failed)) + ".")
        return extraction.result(pages=len(reader.pages), pages_without_text=no_text, pages_failed=failed)


def extract_docx(data, settings):
    if data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        invalid(
            "El Word está cifrado o usa un contenedor binario incompatible. Adjunta una copia sin contraseña en DOCX o PDF."
        )
    extraction = Extraction("docx")
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        names = [item.filename for item in entries]
        if len(entries) > 500 or len(set(names)) != len(names):
            invalid("El DOCX contiene demasiadas entradas o nombres duplicados.")
        if sum(item.file_size for item in entries) > settings.max_expanded_bytes:
            invalid("El DOCX supera el tamaño expandido permitido.")
        for entry in entries:
            path = PurePosixPath(entry.filename)
            if entry.flag_bits & 1:
                invalid("El DOCX está cifrado. Adjunta una copia sin contraseña.")
            if path.is_absolute() or ".." in path.parts or "\\" in entry.filename:
                invalid("El DOCX contiene rutas incompatibles.")
            if entry.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                invalid("El DOCX usa una compresión incompatible.")
            if entry.file_size > max(1, entry.compress_size) * 200:
                invalid("El DOCX tiene una expansión comprimida peligrosa.")
            if re.search(r"vbaproject|/embeddings/|activex", entry.filename, re.I):
                invalid(
                    "El DOCX contiene macros u objetos activos no admitidos. Convierte una copia a DOCX sin objetos o PDF."
                )
        if not {"[Content_Types].xml", "_rels/.rels", "word/document.xml"}.issubset(names):
            invalid("El archivo no contiene la estructura real de un DOCX.")

        def read_xml(name):
            # La lectura real comprueba CRC y tamaño; no extrae archivos a disco.
            if archive.getinfo(name).file_size > 8 * 1024 * 1024:
                invalid("Una sección XML del DOCX supera el límite permitido.")
            return xml(archive.read(name))

        # Comprobar también integridad de partes no interpretadas, sin escribirlas ni ejecutarlas.
        expanded = 0
        for entry in entries:
            with archive.open(entry) as stream:
                while block := stream.read(65536):
                    expanded += len(block)
                    if expanded > settings.max_expanded_bytes:
                        invalid("El DOCX supera el tamaño expandido permitido.")

        types = read_xml("[Content_Types].xml")
        types_namespace = "http://schemas.openxmlformats.org/package/2006/content-types"
        if types.tag != f"{{{types_namespace}}}Types" or not any(
            p.tag == f"{{{types_namespace}}}Override"
            and p.get("PartName") == "/word/document.xml"
            and p.get("ContentType") == DOCX_MIME
            for p in types
        ):
            invalid("El contenedor no es un documento Word DOCX compatible sin macros.")
        if any(
            "macroenabled" in p.get("ContentType", "").lower() or "vbaproject" in p.get("ContentType", "").lower()
            for p in types
        ):
            invalid("No se admiten documentos Word habilitados para macros.")
        root_rels = read_xml("_rels/.rels")
        rels_namespace = "http://schemas.openxmlformats.org/package/2006/relationships"
        if root_rels.tag != f"{{{rels_namespace}}}Relationships" or not any(
            p.tag == f"{{{rels_namespace}}}Relationship"
            and p.get("Type", "").endswith("/officeDocument")
            and p.get("Target") in ("word/document.xml", "/word/document.xml")
            and p.get("TargetMode") != "External"
            for p in root_rels
        ):
            invalid("El DOCX no declara una parte principal Word válida.")
        external = False
        for name in names:
            if name.endswith(".rels"):
                external |= any(p.get("TargetMode") == "External" for p in read_xml(name))
        if external:
            extraction.warnings.append("El documento referencia recursos externos; no se abrieron ni descargaron.")

        main = read_xml("word/document.xml")
        namespace = main.tag.split("}")[0].lstrip("{")
        if (
            namespace not in WORD_NS
            or main.tag != f"{{{namespace}}}document"
            or main.find(f"{{{namespace}}}body") is None
        ):
            invalid("La estructura principal del DOCX es incompatible.")
        parts = ["word/document.xml"] + sorted(
            name
            for name in names
            if re.fullmatch(r"word/(?:header\d+|footer\d+|footnotes|endnotes|comments)\.xml", name)
        )
        for part in parts:
            root = main if part == "word/document.xml" else read_xml(part)
            # Recorrido de párrafos en orden XML: incluye tablas, celdas y cuadros de texto.
            index = 0
            for paragraph in root.iter(f"{{{namespace}}}p"):
                index += 1
                text = "".join(
                    node.text or ""
                    if node.tag == f"{{{namespace}}}t"
                    else "\t"
                    if node.tag == f"{{{namespace}}}tab"
                    else "\n"
                    if node.tag in (f"{{{namespace}}}br", f"{{{namespace}}}cr")
                    else ""
                    for node in paragraph_nodes(paragraph, namespace)
                )
                extraction.add(text, f"{part} · párrafo {index}")
            if any(
                node.tag.rsplit("}", 1)[-1] in ("drawing", "pict", "altChunk", "numPr", "del", "ins")
                for node in root.iter()
            ):
                extraction.partial = True
                extraction.warnings.append(
                    "Hay imágenes, numeración automática, revisiones u objetos: no se garantiza recuperar sus etiquetas ni su representación visual."
                )
        extraction.warnings.append(
            "Ubicaciones por parte y párrafo; DOCX no proporciona páginas estables. Encabezados, pies y notas se recuperan aparte del cuerpo."
        )
        extraction.warnings = list(dict.fromkeys(extraction.warnings))
        return extraction.result(parts=parts)


def extract_instrument(extension, data, settings):
    try:
        return extract_pdf(data, settings) if extension == "pdf" else extract_docx(data, settings)
    except HTTPException:
        raise
    except Exception:
        invalid(
            f"No se pudo interpretar el {extension.upper()}: está dañado, cifrado o tiene una estructura incompatible."
        )
