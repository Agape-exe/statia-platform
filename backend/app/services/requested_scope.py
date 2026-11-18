"""Compromisos de productos derivados del usuario, nunca de una respuesta del modelo.

Reconocimiento finito de nombres públicos, no interpretación universal de prosa.
Los productos no reconocidos requieren aclaración; las exclusiones claras se conservan.
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
    "no_posthoc": "Sin comparaciones post hoc",
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


NATURAL_PRODUCTS = (
    (r"\b(?:descriptiva|descriptivo|descripcion|estadistica descriptiva)(?: global)?\b", "global"),
    (r"\b(?:media|mediana|promedio|desviacion estandar|minimo|maximo)\b", "global"),
    (r"\b(?:pearson|correlacion de pearson)\b", "correlation_coefficient"),
    (r"\b(?:anova(?: de welch)?|f de welch)\b", "global_test"),
)
NEGATION = re.compile(r"\b(?:no (?:quiero|incluir|incluyas|solicito|necesito)|sin|excepto|excluir|excluye)\s+")


def parse_products(text):
    products, residue = set(), text
    for alias in sorted(USER_ALIASES, key=len, reverse=True):
        pattern = r"(?<!\w)" + re.escape(alias) + r"(?!\w)"
        if re.search(pattern, residue):
            products.update(USER_ALIASES[alias])
            residue = re.sub(pattern, " ", residue)
    for pattern, product in NATURAL_PRODUCTS:
        if re.search(pattern, residue):
            products.add(product)
            residue = re.sub(pattern, " ", residue)
    if re.search(r"describir todas las observaciones|describir los datos globalmente", text):
        products.add("global")
    if re.search(r"resumir(?:las|los)? por grupo", text):
        products.add("grouped")
    # Las medidas por grupo no piden además resúmenes globales.
    if "global" in products and re.search(r"por grupo|segun [\w`]+", text) and not re.search(r"global", text):
        products.remove("global")
        products.add("grouped" if re.search(r"descriptiv", text) else "group_means")
    return products, residue


def product_request(text):
    literal = normalized(text)
    if re.match(
        r"(?:que (?:es|son|significa)|como (?:funciona|se interpreta)|explica(?:me)?\b)", literal.lstrip("¿?¡! ")
    ):
        return set(), set(), False, False
    if re.match(r"(?:es un estudio|es una investigacion)", literal):
        return set(), set(), False, False
    literal = re.sub(r"confirmo que `[^`]+` es cuantitativa (?:discreta|continua)[.;]?", "", literal).strip()
    # Separar exclusiones antes de reconocer productos; nunca acreditarlas como solicitudes.
    positive, negative = [], []
    for clause in re.split(r"[,;.!]|\b(?:pero|solo|unicamente)\b", literal):
        match = NEGATION.search(clause)
        if match:
            positive.append(clause[: match.start()])
            negative.append(clause[match.end() :])
        else:
            positive.append(clause)
    products, residue = parse_products(" ".join(positive))
    excluded, excluded_residue = parse_products(" ".join(negative))
    # Sin IC es una restricción ejecutable del descriptivo, no una solicitud de IC.
    if re.search(r"sin intervalos(?: de confianza)?", literal):
        products.add("no_intervals")
        excluded.discard("mean_interval")
        excluded_residue = re.sub(r"intervalos(?: de confianza)?", "", excluded_residue)
    if re.search(r"(?:sin|no (?:quiero|incluir|incluyas)) (?:comparaciones )?post[ -]?hoc", literal):
        excluded.add("posthoc")
    if re.search(r"sin inferencia|exclusivamente descriptiv|solo descriptiv", literal):
        excluded.update(
            {
                "p_value",
                "correlation_coefficient",
                "pearson_interval",
                "posthoc",
                "global_test",
                "paired_change_interval",
            }
        )
    mentioned = bool(products or excluded or PRODUCT_WORDS.search(literal))
    residue = re.sub(r"\b(?:productos|resultados)\s*:", "", residue)
    # Nombres de columnas/finalidad en prosa son válidos; productos desconocidos,
    # calificativos no ejecutables y ligaduras libres sí necesitan aclaración.
    uncertain = bool(
        PRODUCT_WORDS.search(residue)
        or re.search(r"\b(?:predicciones|avanzados|completos|componente|sustituye|reemplaza|quita|elimina)\b", literal)
    )
    return products, excluded, uncertain, mentioned


def user_products(text):
    products, _, uncertain, mentioned = product_request(text)
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
        products, excluded, uncertain, mentioned = product_request(message["content"])
        if not mentioned:
            continue
        natural_decision = (
            scope["unresolved"]
            and products
            and not uncertain
            and bool(
                re.search(r"\b(?:solo|unicamente)\b|^confirmo (?:que quiero|la descripcion|la descriptiva)", literal)
            )
        )
        if decision or natural_decision:
            scope["products"], scope["unresolved"] = [], False
            scope["excluded_products"] = []
        scope["products"] = sorted(set(scope["products"]) | products)
        scope["excluded_products"] = sorted(set(scope.get("excluded_products", [])) | excluded)
        if set(scope["products"]) & set(scope["excluded_products"]):
            uncertain = True
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
    return scope if scope["products"] or scope.get("excluded_products") or scope["unresolved"] else None


def validate_plan_scope(plan, scope, files):
    if not scope:
        return
    if scope["unresolved"]:
        raise PlanningError(
            "requested_scope", "El usuario debe confirmar el alcance antes de recibir propuestas definitivas."
        )
    validate_products(plan, files)  # Conserva también las ligaduras a componentes.
    declared = {kind for text in plan.expected_outputs for kind in OUTPUTS.get(output_request(text)[1], ())}
    excluded = set(scope.get("excluded_products", []))
    steps = plan.components if plan.procedure == "integral" else [plan]
    if {"global_test", "correlation_coefficient", "p_value"} <= excluded and any(
        s.procedure not in {"descriptive", "exploratory"} for s in steps
    ):
        raise PlanningError(
            "requested_scope", "El usuario solicitó un alcance exclusivamente descriptivo, sin inferencia."
        )
    if excluded & declared:
        raise PlanningError("requested_scope", "La propuesta incluye productos excluidos expresamente por el usuario.")
    from app.services.plan_capabilities import requests_posthoc

    if "posthoc" in excluded and any(requests_posthoc(s.method) for s in steps):
        raise PlanningError("requested_scope", "El usuario excluyó comparaciones post hoc.")
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
            "¿Deseas describir todas las observaciones, resumirlas por grupo o combinar ambos alcances? Indica también cualquier producto adicional o exclusión que debamos conservar."
        ],
        clarification_required=True,
        confirmation_required=False,
    )
