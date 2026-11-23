"""Recuperación local sobre texto privado por códigos, palabras y temas acotados."""

import re
import unicodedata
from itertools import zip_longest

from app.services.instrument_terms import contains_phrase, requested_topics
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
SEARCH_STOP = STOP | set(
    "ayuda necesito quiero favor relacionada relacionadas relacionados relacion tema temas item items "
    "acceso uso utiliza indican identificar lista menciona incluye encuentra indica enunciados originales "
    "find show list related the which what does do you about of to and or in is are for from with "
    "question questions questionnaire instrument document items item options answers access use".split()
)
PARTIAL_EVIDENCE = "No encontré evidencia suficiente para el resto de la consulta."


def normalized(text):
    return "".join(c for c in unicodedata.normalize("NFKD", text.casefold()) if unicodedata.category(c) != "Mn")


def tokens(text):
    return set(re.findall(r"\w+", normalized(text))) - SEARCH_STOP


def word_text(text):
    return " " + " ".join(re.findall(r"\w+", normalized(text))) + " "


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


def search_query(query):
    query = re.sub(r"\S+\.(?:pdf|docx)\b", "", query, flags=re.I)
    # Un marcador de lista no puede formar un código con la frase anterior.
    return re.sub(r"^[^\S\r\n]*\d+[.)](?=\s|$)", ":", query, flags=re.M)


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
    code_query = search_query(query)
    requested_codes = codes(code_query)
    terms = tokens(code_query)
    topics = {} if requested_codes else requested_topics(word_text(code_query))
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
            code_hits = requested_codes & codes(text) if requested_codes else set()
            if requested_codes and not code_hits:
                continue
            words = word_text(text) if topics else ""
            topic_hits = {topic for topic, evidence in topics.items() if contains_phrase(words, evidence)}
            score = 100 * len(code_hits) + 3 * len(terms & found) + 5 * len(topic_hits)
            if not terms and not topics and not requested_codes:
                score = 1
            if score:
                if topic_hits and "?" in text:
                    score += 2
                # Nombre explícito ayuda a priorizar, sin inventar asociación entre archivos.
                name = file.get("original_name")
                score += 20 if name and normalized(name) in normalized(query) else 0
                candidates.append((score, file["id"], index, fragments, code_hits | topic_hits))
    ranked = sorted(candidates, key=lambda c: -c[0])
    anchors = []
    for key in sorted(requested_codes or topics):
        candidate = next((c for c in ranked if key in c[4]), None)
        if candidate is not None and candidate not in anchors:
            anchors.append(candidate)
    for fid in results:
        candidate = next((c for c in ranked if c[1] == fid), None)
        if candidate is not None and candidate not in anchors:
            anchors.append(candidate)
    if topics:
        # Al encontrar una fila de Word, reservar también su pregunta cercana y
        # la escala que pueda seguirla antes de los demás fragmentos vecinos.
        for score, fid, index, fragments, hits in anchors[:]:
            if not hits or results[fid]["format"] != "docx" or "?" in fragments[index]["text"]:
                continue
            part = fragments[index]["location"].split(" · ")[0]
            for previous in range(index - 1, max(-1, index - 9), -1):
                fragment = fragments[previous]
                if fragment["location"].split(" · ")[0] != part:
                    break
                if "?" in fragment["text"]:
                    anchor = (score, fid, previous, fragments, hits)
                    if not any((fid, previous) == (item[1], item[2]) for item in anchors):
                        anchors.append(anchor)
                    break
    seen = set()

    def share(fid, fragments, index):
        nonlocal budget
        if not 0 <= index < len(fragments) or (fid, index) in seen or len(seen) >= 10:
            return
        fragment = fragments[index]
        if len(fragment["text"]) > budget:
            return
        seen.add((fid, index))
        budget -= len(fragment["text"])
        results[fid]["fragments_shared"].append(
            {**fragment, "location": readable_location(fragment["location"]), "index": index}
        )
        results[fid]["retrieval"] = "matched"

    for _, fid, index, fragments, _ in anchors:
        share(fid, fragments, index)
    if topics:
        for _, fid, index, fragments, _ in anchors:
            if "?" in fragments[index]["text"]:
                share(fid, fragments, index + 1)
        # Dar espacio a filas relacionadas de cada tema antes de llenar con
        # párrafos vecinos. Por ejemplo, dispositivos y escalas de una tabla.
        by_topic = [[item for item in ranked if topic in item[4]] for topic in topics]
        for round_items in zip_longest(*by_topic):
            for _, fid, index, fragments, _ in filter(None, round_items):
                share(fid, fragments, index)
            if len(seen) >= 10:
                break
    # Reservar opciones contiguas, especialmente en consultas por códigos.
    for offset in (1, -1, *range(2, 9)):
        for _, fid, index, fragments, _ in anchors[:10]:
            share(fid, fragments, index + offset)
    for _, fid, index, fragments, _ in ranked:
        share(fid, fragments, index)
    for result in results.values():
        result["fragments_shared"].sort(key=lambda f: f["index"])
        result["fragments_omitted"] = result["fragments_available"] - len(result["fragments_shared"])
        if result["fragments_shared"] and topics:
            result["retrieval_method"] = "thematic"
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
    if uses_thematic_evidence(context):
        validate_thematic_reply(text, excerpts)
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


def uses_thematic_evidence(context):
    return context.get("interaction_mode") == "document" and any(
        file.get("instrument", {}).get("retrieval_method") == "thematic" for file in context["files"]
    )


def validate_thematic_reply(text, excerpts):
    normalized_excerpts = [" ".join(unicodedata.normalize("NFC", excerpt).split()) for excerpt in excerpts]
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        if line == PARTIAL_EVIDENCE:
            continue
        quote = re.fullmatch(r"(?:[-*] )?«([^»]+)»", line)
        literal = " ".join(unicodedata.normalize("NFC", quote[1]).split()) if quote else ""
        if not literal or not any(literal in excerpt for excerpt in normalized_excerpts):
            raise PlanningError(
                "document_evidence",
                f"Para esta búsqueda temática, escribe cada extracto literal en una línea entre «». "
                f"Si alguna parte no está respaldada, usa exactamente: {PARTIAL_EVIDENCE}",
            )
