"""Recuperación léxica local sobre texto privado; nunca consulta la red ni infiere códigos."""

import re
import unicodedata

from app.services.planning_errors import PlanningError

CODE = re.compile(r"\b(?=[\w-]*[a-zA-Z])(?=[\w-]*\d)[a-zA-Z][a-zA-Z0-9_-]{1,39}\b")
STOP = set(
    "a al el la los las de del en por para con que cual cuales como un una y o es son me puedes favor pregunta preguntas instrumento documento pdf docx codigo codigos opciones respuesta respuestas".split()
)


def normalized(text):
    return "".join(c for c in unicodedata.normalize("NFD", text.casefold()) if unicodedata.category(c) != "Mn")


def tokens(text):
    return set(re.findall(r"[\w-]+", normalized(text))) - STOP


def retrieve_instruments(files, query, authorized, *, budget=12000):
    results, candidates = {}, []
    code_query = re.sub(r"\S+\.(?:pdf|docx)\b", "", query, flags=re.I)
    requested_codes = {normalized(code) for code in CODE.findall(code_query)}
    terms = tokens(query)
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
            "retrieval": "not_authorized" if not authorized else "no_match",
            "fragments_available": len(fragments),
            "fragments_shared": [],
            "legacy_excerpt_only": legacy,
        }
        if not authorized:
            continue
        for index, fragment in enumerate(fragments):
            text = fragment["text"]
            found = tokens(text)
            code_hits = requested_codes & found
            if requested_codes and not code_hits:
                continue
            score = 100 * len(code_hits) + len(terms & found)
            if not terms:
                score = 1
            if score:
                # Nombre explícito ayuda a priorizar, sin inventar asociación entre archivos.
                score += 20 if normalized(file.get("original_name", "")) in normalized(query) and query else 0
                candidates.append((score, file["id"], index, fragments))
    ranked = sorted(candidates, key=lambda c: -c[0])
    anchors = []
    for code in sorted(requested_codes):
        candidate = next((c for c in ranked if code in tokens(c[3][c[2]]["text"])), None)
        if candidate is not None and candidate not in anchors:
            anchors.append(candidate)
    for fid in results:
        candidate = next((c for c in ranked if c[1] == fid), None)
        if candidate is not None and candidate not in anchors:
            anchors.append(candidate)
    anchors.extend(c for c in ranked if c not in anchors)
    seen = set()
    # Primero las coincidencias de códigos/documentos; después sus opciones vecinas.
    for neighbor_offsets in [(0,), (-1, 1)]:
        for _, fid, index, fragments in anchors[:10]:
            for offset in neighbor_offsets:
                position = index + offset
                if position < 0 or position >= len(fragments) or (fid, position) in seen:
                    continue
                text = fragments[position]["text"]
                if budget < len(text) or len(seen) >= 10:
                    continue
                budget -= len(text)
                seen.add((fid, position))
                results[fid]["fragments_shared"].append({**fragments[position], "index": position})
                results[fid]["retrieval"] = "matched"
    for result in results.values():
        result["fragments_shared"].sort(key=lambda f: f["index"])
        result["fragments_omitted"] = result["fragments_available"] - len(result["fragments_shared"])
    return results


def validate_document_claims(text, context):
    if context.get("interaction_mode") != "document":
        return
    evidence = "\n".join(
        fragment["text"]
        for file in context["files"]
        for fragment in file.get("instrument", {}).get("fragments_shared", [])
    )
    known = {normalized(code) for code in CODE.findall(evidence)}
    for literal in re.findall(r"«([^»]+)»", text):
        if re.sub(r"\s+", " ", normalized(literal)).strip() not in re.sub(r"\s+", " ", normalized(evidence)):
            raise PlanningError(
                "document_evidence",
                "Una cita literal debe coincidir con el texto recuperado. Presenta las paráfrasis como tales y reconoce contenido ausente.",
            )
    for sentence in re.split(r"[.!?\n]", text):
        for code in CODE.findall(sentence):
            if normalized(code) not in known and not re.search(
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
