"""Compromisos de productos derivados del usuario, nunca de una respuesta del modelo.

Reconocimiento finito de nombres públicos, no interpretación universal de prosa.
Los productos no reconocidos requieren aclaración; las exclusiones claras se conservan.
Se guarda en stage_data JSONB v1; no modifica planes, resultados ni RPC históricos.
"""

import re

from app.models.chat import AssistantReply
from app.services.conversation_text import (
    action_of,
    independent_proposal,
    informational_mode,
    proposal_limit,
)
from app.services.plan_capabilities import (
    OUTPUTS,
    SUMMARY_STATISTICS,
    normalized,
    output_request,
    validate_products,
)
from app.services.planning_errors import PlanningError
from app.services.statistics.catalog import CATALOG
from app.services.statistics.methods import (
    methods_in_text,
    supported_request,
    unquote_column_references,
)

SCOPE_RECOGNIZER_VERSION = 7

LABELS = {
    **SUMMARY_STATISTICS,
    "numeric_summary": "N válido, media, mediana, DE muestral, mínimo y máximo",
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
    "degrees_of_freedom": "Grados de libertad",
    "paired_change_interval": "Estimación del cambio con incertidumbre",
}
USER_ALIASES = {
    **{alias: kinds for alias, kinds in OUTPUTS.items() if alias != "de"},
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
NEGATION = re.compile(
    r"\b(?:no (?:quiero|incluir|incluyas|solicito|necesito|usar|uses|aplicar|apliques)|"
    r"y no|sin|excepto|en lugar de|excluir|excluye)\s+"
)
COMPLETE_CASES = re.compile(r"\b(?:casos|registros|datos|filas|observaciones) complet[oa]s\b")
MEAN_OBJECTIVE = re.compile(
    r"\b(?:compar|contrast)(?:a(?:r|me)?|e[ns]?|amos|ando|acion de)\s+(?:(?:la|las|el|los)\s+)?"
    r"(?:medias?|promedios?)\b(?!\s+global)"
)
FREQUENCIES = re.compile(r"\b(?:tabla de )?frecuencias(?: absolutas)?(?: y porcentajes)?\b")
EXCLUSIONS = {
    "no_filters": r"\b(?:sin filtros|todos los registros(?: disponibles)?|todas las observaciones)\b",
    "no_groups": r"\b(?:sin|ni) agrupaci(?:on|ones)\b",
    "no_charts": r"\b(?:sin|ni) graficos?\b",
    "only_selected_variables": r"\b(?:sin|ni) otras variables\b",
    "only_requested_outputs": r"\b(?:(?:solo (?:quiero |necesito )?|exclusivamente )una tabla|(?:sin|ni) (?:resultados|productos) adicionales)\b",
}


def request_clauses(text):
    """Conserva la polaridad de una enumeración hasta otra instrucción u oración.

    Una coma enumera productos: no cancela «sin»/«no incluir». Los marcadores
    de sección describen la solicitud, no constituyen productos ejecutables.
    Devuelve fragmentos positivos y excluidos para compartir una interpretación
    entre productos y restricciones, sin consultar al proveedor.
    """
    positive, negative = [], []
    for sentence in re.split(r"[;.!]|\b(?:pero|solo|unicamente|exclusivamente)\b", text):
        excluded = False
        for clause in sentence.split(","):
            clause = re.sub(r"\b(?:productos?|resultados)(?: solicitados?| esperados?)?\s*:", "", clause)
            match = NEGATION.search(clause)
            if match:
                if clause[: match.start()].strip():
                    (negative if excluded else positive).append(clause[: match.start()])
                negative.append(clause[match.end() :])
                excluded = True
            else:
                if re.match(r"\s*(?:quiero|solicito|incluye|incluir|agrega|necesito|usa|utiliza|aplica|con)\b", clause):
                    excluded = False
                (negative if excluded else positive).append(clause)
    return positive, negative


def parse_products(text, grouping_columns=(), column_names=()):
    products, residue = set(), unquote_column_references(text, column_names)
    for alias in sorted(USER_ALIASES, key=len, reverse=True):
        pattern = r"(?<!\w)" + re.escape(alias) + r"(?!\w)"
        if re.search(pattern, residue):
            products.update(USER_ALIASES[alias])
            residue = re.sub(pattern, " ", residue)
    if FREQUENCIES.search(residue):
        if not products & {"frequencies", "grouped_frequencies", "group_frequencies"}:
            products.add("frequencies")
        residue = FREQUENCIES.sub(" ", residue)
    for pattern, product in NATURAL_PRODUCTS:
        if re.search(pattern, residue):
            if pattern != NATURAL_PRODUCTS[0][0] or not products & {
                "frequencies",
                "grouped_frequencies",
                "group_frequencies",
            }:
                products.add(product)
            residue = re.sub(pattern, " ", residue)
    if re.search(r"describir todas las observaciones|describir los datos globalmente", text):
        products.add("global")
    if re.search(r"resumir(?:las|los)? por grupo", text):
        products.add("grouped")
    # «p global»/«contraste global» no describe el alcance de las medias.
    summary_scope = re.sub(r"\b(?:p|anova|contraste|prueba|estadistico(?: de prueba)?) global\b", "", text)
    grouped = re.search(r"\b(?:por|en cada) (?:grupo|categoria|nivel|estrato)\w*\b|\bsegun [\w`]+", text) or any(
        re.search(r"\bpor (?:la columna |la variable )?`?" + re.escape(column) + r"(?!\w)", text)
        for column in grouping_columns
    )
    if (
        grouped
        and not re.search(r"\bglobal(?:es|mente)?\b", summary_scope)
        and products & {"global", "mean", "sample_sd", "valid_n"}
    ):
        means_only = products & {"global", "mean", "sample_sd", "valid_n"} == {"mean"}
        products.discard("global")
        # N/media/DE por grupo ya pertenecen al resumen agrupado. No exigir
        # además un descriptivo de todas las filas por reconocer cada nombre.
        products.difference_update({"mean", "sample_sd", "valid_n"})
        products.add("group_means" if means_only else "grouped")
    return products, residue


def product_request(text, grouping_columns=(), column_names=()):
    literal = normalized(text)
    if proposal_limit(text) is None and informational_mode(text):
        return set(), set(), False, False
    if re.match(
        r"(?:que (?:es|son|significa)|como (?:funciona|se interpreta)|explica(?:me)?\b)", literal.lstrip("¿?¡! ")
    ):
        return set(), set(), False, False
    if re.match(r"(?:es un estudio|es una investigacion)", literal):
        return set(), set(), False, False
    literal = re.sub(r"confirmo que `[^`]+` es cuantitativa (?:discreta|continua)[.;]?", "", literal).strip()
    # Separar exclusiones antes de reconocer productos; nunca acreditarlas como solicitudes.
    positive, negative = request_clauses(literal)
    positive = ["de muestral" if clause.strip() == "de" else clause for clause in positive]
    products, residue = parse_products(
        " ".join(MEAN_OBJECTIVE.sub(" ", clause) for clause in positive), grouping_columns, column_names
    )
    if proposal_limit(text) is not None:
        # La forma genérica de presentar los productos del plan no pide un
        # gráfico concreto ni sustituye los productos estadísticos solicitados.
        residue = re.sub(
            r"\btablas y graficos(?: (?:esperados|previstos))?(?=\s*(?:$|[-:•]|\by (?:las )?limitaciones\b|no ejecutes\b))",
            "",
            residue,
        )
    excluded, _ = parse_products(" ".join(negative), grouping_columns, column_names)
    # Sin IC es una restricción ejecutable del descriptivo, no una solicitud de IC.
    if re.search(r"sin intervalos(?: de confianza)?", literal):
        products.add("no_intervals")
        excluded.discard("mean_interval")
    if re.search(r"(?:sin|no (?:quiero|incluir|incluyas)) (?:comparaciones )?post[ -]?hoc", literal):
        excluded.add("posthoc")
    if re.search(r"sin inferencia|exclusivamente descriptiv|solo descriptiv", literal) or re.search(
        r"\b(?:inferencia|pruebas inferenciales)\b", " ".join(negative)
    ):
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
    prose = unquote_column_references(literal, column_names)
    mentioned = bool(products or excluded or PRODUCT_WORDS.search(prose))
    residue = re.sub(r"\b(?:productos|resultados)\s*:", "", residue)
    # Nombres de columnas/finalidad en prosa son válidos; productos desconocidos,
    # calificativos no ejecutables y ligaduras libres sí necesitan aclaración.
    uncertain = bool(
        PRODUCT_WORDS.search(residue)
        or re.search(
            r"\b(?:predicciones|avanzados|completos|componente|sustituye|reemplaza|quita|elimina)\b",
            COMPLETE_CASES.sub(" ", prose),
        )
    )
    return products, excluded, uncertain, mentioned


def user_products(text):
    products, _, uncertain, mentioned = product_request(text)
    return products, uncertain, mentioned


def requested_scope(conversation, messages, turn, files=()):
    saved = conversation.get("stage_data", {}).get("requested_scope")
    if saved and saved.get("recognizer_version") != SCOPE_RECOGNIZER_VERSION:
        # Reparar únicamente cachés derivadas cuya evidencia completa aún está
        # disponible. Nunca inferir que se puede recortar un historial truncado.
        source_ids = set(saved.get("source_requests", []))
        available = {m.get("metadata", {}).get("request_id") for m in messages if m.get("role") == "user"}
        if source_ids and source_ids <= available and len(messages) < 30:
            saved = None
    scope = dict(saved) if saved else {"version": 1, "products": [], "unresolved": False, "mode": "analysis"}
    scope["source_requests"] = list(scope.get("source_requests", []))
    scope.setdefault("recognizer_version", SCOPE_RECOGNIZER_VERSION)
    columns = [column for file in files for column in file["metadata"].get("profile", {}).get("columns", [])]
    column_names = {normalized(column["name"]) for column in columns}
    grouping_columns = {
        normalized(column["name"])
        for column in columns
        if column.get("statistical_type") in {"categorical", "categorical_or_ordinal"}
    }
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
        products, excluded, uncertain, mentioned = product_request(message["content"], grouping_columns, column_names)
        count = proposal_limit(message["content"])
        positive, negative = request_clauses(literal)
        method_text = " ".join(positive)
        # Una lista de opciones no elige un método. Los nombres en exclusiones
        # e intervenciones informativas tampoco son compromisos del usuario.
        methods, excluded_methods = set(), set()
        if count is not None or not informational_mode(literal):
            excluded_methods = methods_in_text(" ".join(negative), column_names) - {"descriptive"}
            if not re.search(r"\b(?:o|versus|alternativas)\b", method_text):
                methods = methods_in_text(method_text, column_names) - {"descriptive"}
        mentioned = mentioned or bool(methods or excluded_methods)
        constraints = (
            {name for name, pattern in EXCLUSIONS.items() if re.search(pattern, literal)}
            if count or mentioned
            else set()
        )
        exclusions = " ".join(negative)
        if count or mentioned:
            for name, pattern in {
                "no_filters": r"\bfiltros\b",
                "no_groups": r"\bagrupaci(?:on|ones)\b",
                "no_charts": r"\bgraficos?\b",
                "only_selected_variables": r"\botras variables\b",
            }.items():
                if re.search(pattern, exclusions):
                    constraints.add(name)
        # Un producto exclusivo y completo delimita la nueva propuesta aunque
        # la petición empiece con una introducción conversacional («Ahora sí»).
        independent = independent_proposal(message["content"]) or (
            count == 1 and products and not uncertain and "only_requested_outputs" in constraints
        )
        if not mentioned and not constraints and not independent:
            continue
        natural_decision = (
            scope["unresolved"]
            and products
            and not uncertain
            and bool(
                re.search(r"\b(?:solo|unicamente)\b|^confirmo (?:que quiero|la descripcion|la descriptiva)", literal)
            )
        )
        if decision or natural_decision or independent:
            scope["products"], scope["unresolved"] = [], False
            scope["excluded_products"] = []
            scope["excluded_methods"] = []
            scope["constraints"] = []
            scope.pop("variables", None)
            scope.pop("product_sources", None)
            if independent or literal.startswith("cambio de alcance:"):
                scope["required_methods"] = []
                scope["source_requests"] = []
                scope["recognizer_version"] = SCOPE_RECOGNIZER_VERSION
        if methods:
            scope["required_methods"] = sorted(set(scope.get("required_methods", [])) | methods)
        if excluded_methods:
            scope["excluded_methods"] = sorted(set(scope.get("excluded_methods", [])) | excluded_methods)
        scope["products"] = sorted(set(scope["products"]) | products)
        scope["excluded_products"] = sorted(set(scope.get("excluded_products", [])) | excluded)
        if constraints:
            scope["constraints"] = sorted(set(scope.get("constraints", [])) | constraints)
        if "only_selected_variables" in constraints or (
            "only_requested_outputs" in constraints and products == {"frequencies"}
        ):
            matching = [
                {"file_id": file["id"], "sheet": file["metadata"].get("selected_sheet"), "column": column["name"]}
                for file in files
                for column in file["metadata"].get("profile", {}).get("columns", [])
                if re.search(r"(?<!\w)" + re.escape(normalized(column["name"])) + r"(?!\w)", literal)
            ]
            if matching:
                scope["variables"] = matching
        if set(scope["products"]) & set(scope["excluded_products"]) or (
            set(scope.get("required_methods", [])) & set(scope.get("excluded_methods", []))
        ):
            uncertain = True
        scope["unresolved"] = scope["unresolved"] or uncertain
        if "mismo analisis" in literal or decision or count == 1:
            scope["mode"] = "analysis"
        elif "alternativas independientes" in literal or count and count > 1:
            scope["mode"] = "alternatives"
        request_id = message.get("metadata", {}).get("request_id")
        if not request_id and message["content"] == turn.content and turn.action == "message":
            request_id = str(turn.request_id)
        if request_id and request_id not in scope["source_requests"]:
            scope["source_requests"].append(request_id)
        if request_id and products:
            provenance = dict(scope.get("product_sources", {}))
            for product in products:
                provenance[product] = list(dict.fromkeys([*provenance.get(product, []), request_id]))[-30:]
            scope["product_sources"] = provenance
    scope["source_requests"] = scope["source_requests"][-30:]
    scope["through_position"] = max(
        [scope.get("through_position", -1), *[m["position"] for m in candidates if isinstance(m.get("position"), int)]]
    )
    return (
        scope
        if scope["products"]
        or scope.get("required_methods")
        or scope.get("excluded_methods")
        or scope.get("excluded_products")
        or scope.get("constraints")
        or scope["unresolved"]
        else None
    )


def validate_plan_scope(plan, scope, files):
    if not scope:
        return
    if scope["unresolved"]:
        raise PlanningError(
            "requested_scope", "El usuario debe confirmar el alcance antes de recibir propuestas definitivas."
        )
    from app.services.statistics.methods import named_methods
    from app.services.statistics.preparation import plan_filters

    steps = plan.components if plan.procedure == "integral" else [plan]
    constraints = set(scope.get("constraints", []))
    if "no_filters" in constraints and (plan_filters(plan) or plan.comparison and plan.comparison.strata):
        raise PlanningError("requested_scope", "Usa todos los registros y conserva la solicitud sin filtros.")
    if "no_groups" in constraints and any(v.role == "group" for step in steps for v in step.variables):
        raise PlanningError("requested_scope", "El usuario pidió un análisis sin agrupaciones.")
    if variables := scope.get("variables"):
        wanted = {(v["file_id"], v["sheet"], v["column"]) for v in variables}
        if {(v.file_id, v.sheet, v.column) for v in plan.variables} != wanted:
            raise PlanningError("requested_scope", "Usa exclusivamente las variables solicitadas en la propuesta.")
    if "no_charts" in constraints and any(
        re.search(r"\b(?:graficos?|png|histogramas?)\b", normalized(text)) for text in plan.expected_outputs
    ):
        raise PlanningError("requested_scope", "El usuario excluyó los gráficos de los productos esperados.")
    wanted_methods = set(scope.get("required_methods", []))
    proposed_methods = [(step, named_methods(step)) for step in steps]
    if any(names.intersection(scope.get("excluded_methods", [])) for _, names in proposed_methods):
        raise PlanningError("requested_scope", "La propuesta incluye un método excluido expresamente por el usuario.")
    missing_methods = wanted_methods - {
        method
        for step, names in proposed_methods
        for method in wanted_methods
        if names == {method}
        and method in CATALOG
        and step.procedure in CATALOG[method].families
        and supported_request(step)
    }
    if missing_methods:
        raise PlanningError(
            "requested_scope",
            "Conserva el método solicitado en su componente correspondiente: "
            + ", ".join(CATALOG[method].name if method in CATALOG else method for method in sorted(missing_methods))
            + ".",
        )
    validate_products(plan, files)  # Conserva también las ligaduras a componentes.
    declared = {kind for text in plan.expected_outputs for kind in OUTPUTS.get(output_request(text)[1], ())}
    if "only_requested_outputs" in constraints and scope["products"] == ["frequencies"]:
        if len(plan.expected_outputs) != 1 or declared != {"frequencies"} or plan.components or plan.joins:
            raise PlanningError("requested_scope", "Incluye únicamente la tabla de frecuencias categóricas solicitada.")
    from app.services.plan_capabilities import DEFAULT_OUTPUTS

    if (
        plan.procedure in {"descriptive", "exploratory"}
        and not plan.components
        and any(output_request(text)[1] in DEFAULT_OUTPUTS for text in plan.expected_outputs)
    ):
        # El motor del descriptivo simple ya entrega estos productos. Comprobar
        # la cobertura real antes de acreditar un alias, sin cambiar el método.
        for product in set(scope["products"]) & {
            "global",
            "grouped",
            "group_means",
            "frequencies",
            "grouped_frequencies",
        }:
            validate_products(plan.model_copy(update={"expected_outputs": [LABELS[product]]}), files)
            declared.add(product)
    if (
        "global" in scope["products"]
        and "frequencies" in declared
        and plan.procedure in {"descriptive", "exploratory"}
        and not plan.components
    ):
        from app.services.plan_capabilities import product_coverage

        _, groups, measures, categories, covered = product_coverage(plan, files)
        if not groups and measures and measures <= categories and measures <= covered["frequencies"]:
            # En una selección exclusivamente categórica, las frecuencias de
            # todas las observaciones son su descripción global, sin otro método.
            declared.add("global")
    if "global" in declared or "numeric_summary" in declared:
        declared.update(SUMMARY_STATISTICS)
    if set(SUMMARY_STATISTICS) <= declared:
        declared.add("numeric_summary")
        declared.add("global")
    excluded = set(scope.get("excluded_products", []))
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
    if "group_means" in declared and "grouped" in scope["products"]:
        # Equivalencia verificable: el método debe producir el resumen completo
        # para las variables/agrupaciones requeridas, no basta una etiqueta.
        validate_products(plan.model_copy(update={"expected_outputs": [LABELS["grouped"]]}), files)
        declared.add("grouped")
    if "grouped" in declared and "group_means" in scope["products"]:
        validate_products(plan.model_copy(update={"expected_outputs": [LABELS["group_means"]]}), files)
        declared.add("group_means")
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
    elif {"no_filters", "no_groups"} <= set(scope.get("constraints", [])) and any(
        re.search(r"\b(?:deseas|prefieres|quieres)\b.{0,95}\b(?:por grupo|agrup(?:ar|adas|ados))\b", normalized(q))
        for q in reply.questions
    ):
        raise PlanningError("requested_scope", "Ya se indicó utilizar todos los registros sin agrupaciones.")
    elif (
        scope["products"]
        and not scope["unresolved"]
        and any(
            re.search(
                r"que productos?.*(?:definir|deseas|quieres)|(?:define|especifica) (?:el|los) productos?", normalized(q)
            )
            for q in reply.questions
        )
    ):
        raise PlanningError(
            "requested_scope", "Los productos ya están especificados; no solicites definirlos nuevamente."
        )


def scope_question(scope, *, provider_failed=False):
    if provider_failed and not scope["unresolved"]:
        return AssistantReply(
            response="La solicitud tiene un alcance definido, pero el proveedor no generó un plan válido que lo cubra. No se guardó una propuesta incompleta; el alcance y sus exclusiones se conservan.",
            suggested_stage="clarification",
            questions=[
                "Puedes reintentar la misma solicitud para generar otra propuesta; no necesitas redefinir sus productos."
            ],
            clarification_required=True,
            confirmation_required=False,
        )
    products = "; ".join(LABELS[k] for k in scope["products"])
    detail = (
        ("Identifiqué estos productos en tu solicitud: " + products + ". ")
        if products
        else "No podemos verificar qué productos debe incluir la propuesta. "
    )
    conflicts = set(scope.get("required_methods", [])) & set(scope.get("excluded_methods", []))
    if conflicts:
        names = ", ".join(CATALOG[method].name for method in sorted(conflicts))
        question = f"La solicitud incluye y excluye {names}. ¿Qué método quieres usar?"
    else:
        question = "Indica qué producto adicional o cambio deseas. Puedes mantener los productos y restricciones ya reconocidos."
    return AssistantReply(
        response=detail + "Necesito aclarar el resto del alcance antes de preparar la propuesta.",
        suggested_stage="clarification",
        questions=[question],
        clarification_required=True,
        confirmation_required=False,
    )


async def proposal_scope(store, proposal, fallback=None):
    """Lee el alcance de la respuesta que creó la tarjeta. Admite planes legados."""
    if source := proposal.get("source_message_id"):
        rows = await store.rows(
            "messages",
            {"id": source, "conversation_id": proposal["conversation_id"], "role": "assistant"},
            select="metadata",
            limit=1,
        )
        if rows and "requested_scope" in rows[0]["metadata"]:
            return rows[0]["metadata"]["requested_scope"]
    return fallback
