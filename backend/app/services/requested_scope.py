"""Compromisos de productos derivados del usuario, nunca de una respuesta del modelo.

Reconocimiento finito de nombres públicos, no interpretación universal de prosa.
Una mención de productos no reconocida o una exclusión necesita confirmación.
Se guarda en stage_data JSONB v1; no modifica planes, resultados ni RPC históricos.
"""

import re

from app.models.chat import AssistantReply
from app.services.conversation_text import action_of
from app.services.plan_capabilities import (
    OUTPUTS,
    normalized,
    output_request,
    validate_products,
)
from app.services.planning_errors import PlanningError

LABELS = {
    "global": "Resúmenes globales",
    "grouped": "Resúmenes por grupo",
    "frequencies": "Frecuencias categóricas",
    "grouped_frequencies": "Frecuencias categóricas por grupo",
    "group_frequencies": "Frecuencias de la variable de agrupación",
    "mean_interval": "Intervalo de confianza de la media",
    "no_intervals": "Tablas descriptivas sin intervalos de confianza",
    "pearson_interval": "Intervalo de confianza para Pearson",
    "combined_report": "Informes consolidados de descriptivos, correlación y comparación",
    "p_value": "Valores p",
    "correlation_coefficient": "Coeficientes de correlación",
    "posthoc": "Comparaciones post hoc",
    "global_test": "Estadístico de prueba global",
    "group_means": "Medias por grupo",
    "paired_change_interval": "Estimación del cambio con incertidumbre",
}
USER_ALIASES = {
    **OUTPUTS,
    "globales y por grupo": ("global", "grouped"),
    "frecuencias del grupo": ("group_frequencies",),
}
PRODUCT_WORDS = re.compile(
    r"\b(?:resumen(?:es)?|frecuencias|coeficientes?|intervalos?|informes?|productos?|resultados|graficos|valor(?:es)? p)\b"
)


def user_products(text):
    """Solo acredita nombres del catálogo; los modificadores no se descartan.

    Las frases desconocidas, negaciones o ligaduras libres a componentes no se
    convierten en requisitos cubiertos. Se pide una lista explícita al usuario.
    """
    literal = normalized(text)
    if re.match(
        r"(?:que (?:es|son|significa)|como (?:funciona|se interpreta)|explica(?:me)?\b)", literal.lstrip("¿?¡! ")
    ):
        return set(), False, False  # Una consulta conceptual no pide productos nuevos.
    products = set()
    residue = literal
    for alias in sorted(USER_ALIASES, key=len, reverse=True):
        pattern = r"(?<!\w)" + re.escape(alias) + r"(?!\w)"
        if re.search(pattern, residue):
            products.update(USER_ALIASES[alias])
            residue = re.sub(pattern, " ", residue)
    mentioned = bool(products or PRODUCT_WORDS.search(literal))
    # Estos contenedores no describen productos adicionales.
    residue = re.sub(r"\b(?:productos|resultados)\s*:", " ", residue)
    uncertain = bool(PRODUCT_WORDS.search(residue))
    if products:
        # La lista explícita debe poder consumirse íntegramente. Un calificativo
        # o producto desconocido no se elimina por encontrar otro nombre conocido.
        remainder = re.sub(r"^(?:confirmo alcance:|cambio de alcance:)", "", residue).strip()
        remainder = re.sub(r"^(?:solicito|quiero|necesito|deseo|incluye|incluir|me gustaria)\b", "", remainder).strip()
        remainder = re.sub(
            r"\b(?:en un mismo analisis|en el mismo analisis|alternativas independientes|productos|resultados)\b",
            "",
            remainder,
        )
        remainder = re.sub(r"\b(?:cuatro|tres|dos|una)\b", "", remainder)
        # Forma imperativa de descripción con objetivo anterior a la lista;
        # una conjunción o producto adicional en ese objetivo exige aclaración.
        remainder = re.sub(r"^describe [^:;,\n]+?(?=\s{2,}|[;,:])", "", remainder)
        remainder = re.sub(r"\b(?:y|e)\b|[\s;,:.!\-]+", "", remainder)
        uncertain = uncertain or bool(remainder)
    if mentioned and re.search(r"\b(?:no|excepto|quita|elimina|sustituye|reemplaza|componente)\b", residue):
        uncertain = True
    return products, uncertain, mentioned


def requested_scope(conversation, messages, turn):
    saved = conversation.get("stage_data", {}).get("requested_scope")
    scope = dict(saved) if saved else {"version": 1, "products": [], "unresolved": False, "mode": "analysis"}
    scope["source_requests"] = list(scope.get("source_requests", []))
    if saved:
        watermark = saved.get("through_position", -1)
        candidates = [
            m
            for m in messages
            if m.get("role") == "user" and action_of(m) == "message" and m.get("position", -1) > watermark
        ]
        positions = [m["position"] for m in messages if isinstance(m.get("position"), int)]
        if len(messages) >= 30 and positions and watermark < min(positions) - 1:
            scope["unresolved"] = True
    else:
        # Recuperación conservadora de conversaciones históricas y turnos fallidos.
        # primary_goal/context_summary pueden proceder del modelo: no son evidencia.
        candidates = [m for m in messages if m.get("role") == "user" and action_of(m) == "message"]
        if len(messages) >= 30:
            # El historial acotado no permite asegurar que una finalidad anterior
            # carecía de productos obligatorios. Una decisión explícita la resuelve.
            scope["unresolved"] = True
    if turn.action == "message" and not any(
        m.get("metadata", {}).get("request_id") == str(turn.request_id) for m in candidates
    ):
        candidates.append({"role": "user", "content": turn.content})
    for message in candidates:
        literal = normalized(message["content"])
        decision = literal.startswith(("confirmo alcance:", "cambio de alcance:"))
        products, uncertain, mentioned = user_products(message["content"])
        if not mentioned:
            continue
        if decision:
            scope["products"], scope["unresolved"] = [], False
        scope["products"] = sorted(set(scope["products"]) | products)
        scope["unresolved"] = scope["unresolved"] or uncertain
        if "alternativas independientes" in literal:
            scope["mode"] = "alternatives"
        elif "mismo analisis" in literal or decision:
            scope["mode"] = "analysis"
        request_id = message.get("metadata", {}).get("request_id")
        if not request_id and message["content"] == turn.content and turn.action == "message":
            request_id = str(turn.request_id)
        if request_id and request_id not in scope["source_requests"]:
            scope["source_requests"].append(request_id)
    scope["source_requests"] = scope["source_requests"][-30:]
    scope["through_position"] = max(
        [scope.get("through_position", -1), *[m["position"] for m in candidates if isinstance(m.get("position"), int)]]
    )
    return scope if scope["products"] or scope["unresolved"] else None


def validate_plan_scope(plan, scope, files):
    if not scope:
        return
    if scope["unresolved"]:
        raise PlanningError(
            "requested_scope", "El usuario debe confirmar el alcance antes de recibir propuestas definitivas."
        )
    validate_products(plan, files)  # Conserva también las ligaduras a componentes.
    declared = {kind for text in plan.expected_outputs for kind in OUTPUTS.get(output_request(text)[1], ())}
    missing = set(scope["products"]) - declared
    if missing:
        raise PlanningError(
            "requested_scope",
            "Faltan productos solicitados por el usuario: " + "; ".join(LABELS[k] for k in sorted(missing)),
        )
    # No basta con repetir las etiquetas: los componentes también deben cubrirlas.
    required = plan.model_copy(update={"expected_outputs": [LABELS[k] for k in scope["products"]]})
    validate_products(required, files)


def validate_scope_reply(reply, scope, files):
    if not scope:
        return
    if reply.proposals:
        for plan in reply.proposals:
            validate_plan_scope(plan, scope, files)
    elif not (reply.clarification_required and reply.questions):
        raise PlanningError(
            "requested_scope",
            "La finalidad conserva productos pendientes; explica la limitación y solicita una decisión explícita sin afirmar que está resuelta.",
        )


def scope_question(scope):
    products = "; ".join(LABELS[k] for k in scope["products"])
    detail = (
        ("Siguen pendientes los productos solicitados: " + products + ". ")
        if products
        else "No podemos verificar qué productos debe incluir la propuesta. "
    )
    return AssistantReply(
        response=detail
        + "No se guardó una propuesta que reduzca ese alcance. Necesitamos aclararlo o generar componentes que lo cubran.",
        suggested_stage="clarification",
        questions=[
            "¿Qué productos deben conservarse juntos? Para decidir el alcance escribe «Confirmo alcance:» seguido de los productos del catálogo, por ejemplo «Resúmenes globales; Resúmenes por grupo; Frecuencias de la variable de agrupación». Puedes pedir otra combinación; si no es verificable, la revisaremos antes de proponer."
        ],
        clarification_required=True,
        confirmation_required=False,
    )
