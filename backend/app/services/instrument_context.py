"""Recuperación léxica local sobre texto privado; nunca consulta la red ni infiere códigos."""

import re
import unicodedata

from app.services.planning_errors import PlanningError

# El punto es un separador solo dentro de una referencia alfanumérica.
# Los límites impiden tomar un prefijo de otro ítem o de un número compuesto.
CODE = re.compile(
    r"(?<![\w.])(?:"
    r"(?P<prefix>[a-zA-Z]{1,16})(?:\s*[-_.‐‑–−]\s*|\s+)?\d{1,12}"
    r"(?:[a-zA-Z][a-zA-Z0-9]{0,11}|[-_]\d{1,8})?"
    r"|(?=[\w-]*\d)[a-zA-Z][a-zA-Z0-9_-]{1,39}"
    r")(?![\w-]|\.\d)"
)
STOP = set(
    "a al el la los las de del en por para con que cual cuales como un una y o es son me puedes favor pregunta preguntas instrumento documento pdf docx codigo codigos opciones respuesta respuestas busca buscar explica explicar dice dime sobre contiene consultar informacion muestra mostrar describe describir este esta estos estas su sus".split()
)


def normalized(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if unicodedata.category(c) != "Mn")


def tokens(text):
    return set(re.findall(r"\w+", normalized(text))) - STOP


def canonical_code(value):
    return re.sub(r"[\s_.‐‑–−-]+", "", normalized(value))


def codes(text):
    return {canonical_code(match[0]) for match in code_matches(text)}


def code_matches(text):
    # NFKC recupera letras, números y signos de ancho completo.
    return (
        match
        for match in CODE.finditer(unicodedata.normalize("NFKC", text))
        if (match["prefix"] or "").casefold() not in STOP or match[0].isalnum()
    )


def readable_location(location):
    labels = {
        "document": "Cuerpo del documento",
        "footnotes": "Notas al pie",
        "endnotes": "Notas finales",
        "comments": "Comentarios",
    }
    return re.sub(
        r"word/(document|header\d+|footer\d+|footnotes|endnotes|comments)\.xml",
        lambda match: labels.get(
            match[1], "Encabezado " + match[1][6:] if match[1].startswith("header") else "Pie de página " + match[1][6:]
        ),
        location,
    )


def retrieve_instruments(files, query, authorized, *, budget=12000):
    results, candidates = {}, []
    code_query = re.sub(r"\S+\.(?:pdf|docx)\b", "", query, flags=re.I)
    requested_codes = codes(code_query)
    terms = tokens(code_query)
    for file in files:
        if file["file_role"] != "instrument":
            continue
        meta = file["metadata"]
        fragments = meta.get("fragments")
        legacy = fragments is None
        if legacy:
            text = meta.get("text_excerpt", "")[:16000]
            fragments = [
                {"location": "Extracto histórico sin ubicación", "offset": i, "text": text[i : i + 1400]}
                for i in range(0, len(text), 1200)
            ]
        results[file["id"]] = {
            "status": meta.get("extraction_status", "legacy_excerpt"),
            "format": file.get("file_type", "pdf"),
            "retrieval": "not_authorized" if not authorized else "no_text" if not fragments else "no_match",
            "fragments_available": len(fragments),
            "fragments_shared": [],
            "legacy_excerpt_only": legacy,
        }
        if not authorized:
            continue
        for index, fragment in enumerate(fragments):
            text = fragment["text"]
            found = tokens(text)
            code_hits = requested_codes & codes(text)
            if requested_codes and not code_hits:
                continue
            score = 100 * len(code_hits) + len(terms & found)
            if not terms:
                score = 1
            if score:
                # Nombre explícito ayuda a priorizar, sin inventar asociación entre archivos.
                score += 20 if normalized(file.get("original_name", "")) in normalized(query) and query else 0
                candidates.append((score, file["id"], index, fragments, code_hits))
    ranked = sorted(candidates, key=lambda c: -c[0])
    anchors = []
    for code in sorted(requested_codes):
        candidate = next((c for c in ranked if code in c[4]), None)
        if candidate is not None and candidate not in anchors:
            anchors.append(candidate)
    for fid in results:
        candidate = next((c for c in ranked if c[1] == fid), None)
        if candidate is not None and candidate not in anchors:
            anchors.append(candidate)
    seen = set()
    # Reservar espacio para opciones contiguas antes de otras coincidencias débiles.
    for neighbor_offsets in [(0,), (1, -1), *((offset,) for offset in range(2, 9))]:
        for _, fid, index, fragments, _ in anchors[:10]:
            for offset in neighbor_offsets:
                position = index + offset
                if position < 0 or position >= len(fragments) or (fid, position) in seen:
                    continue
                text = fragments[position]["text"]
                if budget < len(text) or len(seen) >= 10:
                    continue
                budget -= len(text)
                seen.add((fid, position))
                results[fid]["fragments_shared"].append(
                    {
                        **fragments[position],
                        "location": readable_location(fragments[position]["location"]),
                        "index": position,
                    }
                )
                results[fid]["retrieval"] = "matched"
    for _, fid, index, fragments, _ in ranked:
        text = fragments[index]["text"]
        if (fid, index) not in seen and len(seen) < 10 and len(text) <= budget:
            seen.add((fid, index))
            budget -= len(text)
            results[fid]["fragments_shared"].append(
                {**fragments[index], "location": readable_location(fragments[index]["location"]), "index": index}
            )
            results[fid]["retrieval"] = "matched"
    for result in results.values():
        result["fragments_shared"].sort(key=lambda f: f["index"])
        result["fragments_omitted"] = result["fragments_available"] - len(result["fragments_shared"])
    return results


def validate_document_claims(text, context):
    if context.get("interaction_mode") != "document":
        return
    excerpts = [
        fragment["text"]
        for file in context["files"]
        for fragment in file.get("instrument", {}).get("fragments_shared", [])
    ]
    evidence = "\n".join(excerpts)
    known = {code for excerpt in excerpts for code in codes(excerpt)}
    for literal in re.findall(r"«([^»]+)»", text):
        if re.sub(r"\s+", " ", normalized(literal)).strip() not in re.sub(r"\s+", " ", normalized(evidence)):
            raise PlanningError(
                "document_evidence",
                "Una cita literal debe coincidir con el texto recuperado. Presenta las paráfrasis como tales y reconoce contenido ausente.",
            )
    # Separar afirmaciones tras normalizar las referencias completas. Un punto
    # o salto dentro del código no debe ocultar el identificador al validador.
    normalized_text = unicodedata.normalize("NFKC", text)
    parts, last = [], 0
    for match in code_matches(normalized_text):
        parts.extend((normalized_text[last : match.start()], canonical_code(match[0])))
        last = match.end()
    parts.append(normalized_text[last:])
    for sentence in re.split(r"[.!?\n]", "".join(parts)):
        for code in codes(sentence):
            if code not in known and not re.search(
                r"no (?:se |lo |he )?(?:encontr|aparece|consta|dispon|recuper)|sin evidencia|no puedo|no tengo",
                normalized(sentence),
            ):
                raise PlanningError(
                    "document_evidence",
                    "No atribuyas códigos o preguntas ausentes a los documentos. Reconoce el límite de los fragmentos recuperados.",
                )
    if re.search(
        r"(?:he |hemos )?leido (?:todo|complet|integramente)|instrumento completo|documento completo", normalized(text)
    ) and not re.search(r"no (?:he |hemos )?(?:leido|consultado)|no puedo|no se garantiza", normalized(text)):
        raise PlanningError(
            "document_evidence",
            "Solo consultaste fragmentos recuperados; no afirmes haber leído el documento completo.",
        )
