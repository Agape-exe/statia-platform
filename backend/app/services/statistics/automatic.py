"""Prepara, sin calcular contrastes, a partir del plan y de los originales privados."""

import base64
import hashlib
import json
from collections import Counter
from uuid import NAMESPACE_URL, uuid5

import numpy as np

from app.core.config import Settings
from app.models.analysis import (
    ComponentPreparation,
    DataDecision,
    ExecutionComponent,
    ExecutionPreparation,
    ExecutionSpec,
    PreparationChoice,
    PreparationClarification,
    PreparationEvidence,
    PreparationQuestion,
)
from app.models.chat import Plan
from app.services.profiling import numeric
from app.services.statistics.catalog import CATALOG
from app.services.statistics.methods import named_methods, normalized
from app.services.statistics.preparation import (
    CATEGORICAL,
    INDEPENDENT_GROUPS,
    QUANTITATIVE,
    AnalysisError,
    component_order,
    key,
    original_table,
    plan_filters,
    prepare,
    require,
    sources,
    validate_spec,
)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def assess(job):
    plan = Plan.model_validate(job["plan"])
    settings = Settings(_env_file=None, **job.get("limits", {}))
    answers = job.get("answers", {})
    tables, provenance = {}, []
    require({v.file_id for v in plan.variables} == {f["id"] for f in job["files"]}, "Faltan originales del plan.")
    for file in job["files"]:
        data = base64.b64decode(file["data"], validate=True)
        profile, records = original_table(file, data, settings)
        tables[file["id"]] = (file, data, {c["name"]: c for c in profile["columns"]}, records)
        provenance.append(
            {
                "id": file["id"],
                "name": file["original_name"],
                "sheet": file["metadata"]["selected_sheet"],
                "sha256": hashlib.sha256(data).hexdigest(),
                "rows": len(records),
            }
        )
    provenance.sort(key=lambda f: f["id"])
    scope = digest({"plan": job["plan"], "files": provenance})
    from app.services.plan_capabilities import validate_products
    from app.services.planning_errors import PlanningError

    try:
        validate_products(
            plan,
            files=[
                {**f, "metadata": {**f["metadata"], "profile": {"columns": list(columns.values())}}}
                for f, _, columns, _ in tables.values()
            ],
        )
    except PlanningError as exc:
        # El plan histórico no se altera; resolver alcance requiere otra propuesta.
        return ExecutionPreparation(
            request_id=uuid5(NAMESPACE_URL, f"statia:output-scope:{scope}"),
            status="UNSUPPORTED",
            reasons=[str(exc)],
            blockers=[str(exc)],
            files=provenance,
            fingerprint=scope,
        ).model_dump(mode="json")
    questions, clarifications, evidence, blockers, warnings, reasons = [], [], [], [], [], []
    reviewing = job.get("review_question_id")
    owners = set(range(len(sources(plan))))
    question_owners, blocker_owners = {}, {}

    def block(message):
        blockers.append(message)
        blocker_owners.setdefault(message, set()).update(owners)

    def note(subject, origin, detail):
        evidence.append(PreparationEvidence(subject=subject, origin=origin, detail=detail))

    def ask(subject, prompt, explanation, options, variable=None, *, scope_data=None, limitation=None):
        # Identidad local: cambiar otra tabla o el título no borra una decisión
        # sobre esta columna. Los ids previos se conservan al migrar un estado v1.
        local_scope = digest(
            scope_data
            if scope_data is not None
            else {"variable": key(variable), "file": next(f for f in provenance if f["id"] == variable.file_id)}
            if variable
            else {"plan": job["plan"], "files": provenance}
        )
        previous = next(
            (
                q
                for q in job.get("clarifications", [])
                if q.get("subject") == subject and q.get("scope_fingerprint") == local_scope
            ),
            None,
        )
        legacy_id = digest([scope, subject])
        qid = previous["id"] if previous else legacy_id if legacy_id in answers else digest([local_scope, subject])
        choices = [PreparationChoice(value=value, label=label) for value, label in options]
        choices.append(PreparationChoice(value="unknown", label="No lo sé"))
        question = PreparationQuestion(
            id=qid,
            prompt=prompt,
            explanation=explanation,
            choices=choices,
            variable=variable,
            subject=subject,
            scope_fingerprint=local_scope,
            limitation=limitation or "No tenemos información suficiente para resolver esta decisión. " + explanation,
        )
        question_owners.setdefault(qid, set()).update(owners)
        answer = answers.get(qid)
        if answer not in {c.value for c in choices}:
            answer = None
        state = "pending" if reviewing == qid or answer is None else "unknown" if answer == "unknown" else "answered"
        if not any(q.id == qid for q in clarifications):
            clarifications.append(PreparationClarification(**question.model_dump(), status=state, answer=answer))
        if state == "answered":
            display = (
                f"{tables[variable.file_id][0]['original_name']} / {variable.sheet} / {variable.column}"
                if variable
                else prompt
            )
            if ":marker:" in subject:
                display += " · marcador: " + subject.split(":marker:", 1)[1]
            note(display, "user", next(c.label for c in choices if c.value == answer))
        elif state == "pending":
            if not any(q.id == qid for q in questions):
                questions.append(question)
        else:
            warnings.append(question.limitation + " Puedes solicitar una propuesta descriptiva o revisar tu respuesta.")
        return answer if state == "answered" else None

    if plan.joins:
        block("Las uniones entre tablas no están implementadas. Solicita análisis separados.")
    if not sources(plan):
        block("El plan integral antiguo no declara componentes. Solicita una propuesta actualizada.")
    if job.get("thesis") and not plan.methodology_confirmed:
        block("La metodología de tesis requiere una propuesta revisada y confirmada.")

    decisions = []
    for v in plan.variables:
        owners = {i for i, source in enumerate(sources(plan)) if key(v) in {key(x) for x in source.variables}}
        if any(key(v) == key(f.variable) for f in plan_filters(plan)):
            owners = set(range(len(sources(plan))))
        file, _, columns, _ = tables[v.file_id]
        require(
            v.sheet == file["metadata"]["selected_sheet"] and v.column in columns,
            "La hoja o columna del plan ya no existe en el original. Solicita una propuesta revisada.",
        )
        column = columns[v.column]
        subject = json.dumps(key(v))
        kind = None
        if v.role == "pair_id":
            kind = "identifier"
        elif column["possible_identifier"] or column["possible_temporal"]:
            block(f"«{v.column}»: este catálogo no admite identificadores ni fechas como medidas. Revisa la propuesta.")
        elif v.role == "group" or any(key(v) == key(f.variable) for f in plan_filters(plan)):
            kind = "nominal"
            note(
                v.column,
                "inferred",
                "Se usará como categoría por su rol de agrupación o filtro aceptado, sin interpretar sus códigos como magnitudes.",
            )
        elif column["statistical_type"] == "quantitative":
            kind = "continuous"
            note(
                v.column,
                "inferred",
                "Valores numéricos y perfil de medida cuantitativa; se conserva su escala sin inventar unidades.",
            )
        elif column["physical_type"] in {"text", "boolean"} and column["inferred_type"] != "mixed":
            kind = "nominal"
            note(v.column, "inferred", "Valores categóricos; no se impone un orden entre categorías.")
        elif (
            all(s.procedure in {"descriptive", "exploratory"} for s in sources(plan))
            and column["physical_type"] == "numeric"
        ):
            kind = "nominal"
            note(
                v.column,
                "inferred",
                "Códigos de escala desconocida: se mostrarán frecuencias de valores sin calcular medias ni imponer un orden.",
            )
        else:
            kind = ask(
                subject + ":type",
                f"¿Qué representan los valores de «{v.column}»?",
                "Un código numérico puede ser una etiqueta o una medida. El archivo por sí solo no lo demuestra.",
                [("continuous", "Son cantidades medibles"), ("nominal", "Son categorías o códigos sin orden")],
                v,
            )
        decision = DataDecision(variable=v, statistical_type=kind or "nominal")
        for marker in column["missing_markers"]:
            if (
                kind == "continuous"
                and column["statistical_type"] == "quantitative"
                and marker not in column["ambiguous_missing"]
                and numeric(marker) is None
            ):
                decision.missing_markers.append(marker)
                note(
                    v.column,
                    "inferred",
                    f"«{marker}» se tratará como ausencia por el patrón numérico consistente de la medida ({column['missing_markers'][marker]} registros). Revisa esta decisión en detalles u opciones avanzadas.",
                )
                continue
            choice = ask(
                subject + ":marker:" + marker,
                f"En «{v.column}» de {file['original_name']}, ¿qué significa «{marker}»?",
                "Excluir una categoría válida o tratar una ausencia como dato cambia los resultados. La decisión solo se aplicará a esta columna y preparación.",
                [("missing", "Representa información faltante"), ("retained", "Es un valor o categoría válido")],
                v,
            )
            if choice == "missing":
                decision.missing_markers.append(marker)
            elif choice == "retained":
                decision.retained_markers.append(marker)
        decisions.append(decision)
    by_key = {key(d.variable): d for d in decisions}
    note(
        "Originales",
        "verified",
        "Hojas, columnas, tipos físicos y hashes verificados por relectura acotada; no se modifican los archivos.",
    )
    note(
        "Ausencias",
        "verified",
        "Nulos y celdas vacías son ausencias; no se imputa ni se excluyen mezclas silenciosamente.",
    )
    components = []
    for index, source in enumerate(sources(plan)):
        owners = {index}
        component_scope = {
            "source": {
                "procedure": source.procedure,
                "method": source.method,
                "variables": [v.model_dump(mode="json") for v in source.variables],
            },
            "comparison": plan.comparison.model_dump(mode="json") if plan.comparison else None,
            "filters": [
                s.model_dump(mode="json")
                for s in plan_filters(plan)
                if s.variable.file_id in {v.file_id for v in source.variables}
            ],
            "files": [f for f in provenance if f["id"] in {v.file_id for v in source.variables}],
        }
        compatible = [code for code, entry in CATALOG.items() if source.procedure in entry.families]
        named = named_methods(source)
        if not compatible or any(
            word in normalized(source.method)
            for word in (
                "regresion",
                "logistica",
                "games-howell",
                "tukey",
                "medidas repetidas",
                "ancova",
                "manova",
                "permutacion",
                "bootstrap",
            )
        ):
            block(
                f"Componente {index + 1}: el método solicitado no está implementado en este catálogo. Solicita otra propuesta."
            )
            continue
        method = next(iter(named)) if len(named) == 1 else None
        if method and method not in compatible:
            block(f"Componente {index + 1}: el método y la familia aceptados son incompatibles. Revisa la propuesta.")
            continue
        if not method and source.procedure in {"descriptive", "exploratory"}:
            method = "descriptive"
        if not method and not named and source.procedure == "group_comparison":
            group = next((v for v in source.variables if v.role == "group"), None)
            if group:
                _, _, _, rows = tables[group.file_id]
                # Solo usar categorías tras resolver sus marcadores y aplicar los filtros del plan.
                rows = scoped_rows(rows, plan, group.file_id)
                decision = by_key[key(group)]
                levels = {
                    str(r[group.column])
                    for r in rows
                    if r[group.column] is not None
                    and str(r[group.column]).strip()
                    and str(r[group.column]).strip() not in decision.missing_markers
                }
                count = len(plan.comparison.groups) if plan.comparison else len(levels)
                if count == 2 or 3 <= count <= 20:
                    method = "welch_t" if count == 2 else "welch_anova"
                    reasons.append(
                        "Welch permite varianzas distintas y conserva la comparación cuantitativa entre los grupos del plan; no se selecciona por significación."
                    )
                    note(f"Método {index + 1}", "inferred", reasons[-1])
        if (
            not method
            and not named
            and source.procedure == "inferential"
            and len(source.variables) == 2
            and all(by_key[key(v)].statistical_type in CATEGORICAL for v in source.variables)
        ):
            a, b = source.variables
            if a.file_id == b.file_id and a.sheet == b.sheet:
                rows = scoped_rows(tables[a.file_id][3], plan, a.file_id)
                counts = Counter(
                    (str(r[a.column]), str(r[b.column]))
                    for r in rows
                    if r[a.column] is not None
                    and r[b.column] is not None
                    and str(r[a.column]).strip() not in by_key[key(a)].missing_markers
                    and str(r[b.column]).strip() not in by_key[key(b)].missing_markers
                )
                xs, ys = {x for x, _ in counts}, {y for _, y in counts}
                if len(xs) >= 2 and len(ys) >= 2:
                    n = sum(counts.values())
                    small = any(
                        sum(c for (u, _), c in counts.items() if u == x)
                        * sum(c for (_, v), c in counts.items() if v == y)
                        / n
                        < 5
                        for x in xs
                        for y in ys
                    )
                    method = "fisher_exact" if small and len(xs) == len(ys) == 2 else "chi_square"
                    reasons.append(
                        "Asociación categórica según dimensiones y frecuencias esperadas de la tabla, sin usar valores p para elegir el método."
                    )
                    note(f"Método {index + 1}", "inferred", reasons[-1])
        if not method:
            candidates = [code for code in compatible if not named or code in named]
            method = ask(
                f"method:{index}",
                f"¿Cómo quieres estudiar el componente {index + 1}?",
                "El plan antiguo no define un único método. Puedes pedir una propuesta descriptiva si desconoces la relación o el diseño.",
                [
                    (
                        code,
                        {
                            "pearson": "Estudiar una relación lineal (Pearson)",
                            "spearman": "Estudiar una relación que aumenta o disminuye por rangos (Spearman)",
                        }.get(code, CATALOG[code].name),
                    )
                    for code in candidates
                ],
                scope_data=component_scope,
            )
        if not method:
            continue
        if named == {method}:
            reasons.append(f"Se conserva {CATALOG[method].name}, definido en el plan aceptado.")
            note(
                f"Método {index + 1}",
                "verified",
                "Nombre reconocido en el plan aceptado y familia contrastada con el catálogo; se comprobarán roles y datos.",
            )
        design = "not_applicable"
        if method != "descriptive":
            paired = method in {"paired_t", "wilcoxon"}
            # No usar una afirmación del proveedor como evidencia del diseño.
            documented = bool(job.get("independence_evidence")) and not paired
            if not documented:
                answer = ask(
                    f"design:{sorted({(v.file_id, v.sheet) for v in source.variables})}:{paired}",
                    "¿Cada par corresponde a la misma persona o unidad, con pares independientes entre sí?"
                    if paired
                    else "¿Cada observación corresponde a una unidad distinta, sin mediciones repetidas ni agrupaciones relacionadas?",
                    "Por ejemplo, varias mediciones de una misma persona o personas de un mismo grupo relacionado requieren otro diseño. Tener filas distintas no basta para confirmar independencia.",
                    [("yes", "Sí, conozco la recolección y lo confirmo"), ("no", "No, hay observaciones relacionadas")],
                    scope_data={
                        "files": component_scope["files"],
                        "filters": component_scope["filters"],
                        "paired": paired,
                        "pair_ids": [v.model_dump(mode="json") for v in source.variables if v.role == "pair_id"],
                    },
                    limitation="No tenemos información suficiente para confirmar la independencia de las observaciones. Por ahora no puedo presentar este contraste inferencial como metodológicamente validado.",
                )
                if answer == "no":
                    block(
                        "El diseño informado no es compatible con este contraste. Solicita una propuesta revisada o descriptiva."
                    )
                if answer == "yes":
                    design = "paired" if paired else "independent"
            else:
                design = "independent"
                note(
                    "Independencia",
                    "user",
                    "El historial conserva evidencia metodológica explícita del usuario; sigue siendo información declarada, no una prueba empírica.",
                )
        equal = False
        if method in {"student_t", "anova"}:
            equal = (
                ask(
                    f"variance:{index}",
                    "El método aceptado necesita varianzas comparables. ¿Hay justificación metodológica para asumirlo?",
                    "No se sustituirá el método aceptado ni se asumirá igualdad por el resultado de una prueba de normalidad.",
                    [("yes", "Sí, cuento con justificación"), ("no", "No; necesito revisar la propuesta")],
                    scope_data=component_scope,
                )
                == "yes"
            )
            if not equal and any(
                q.subject == f"variance:{index}" and q.status == "answered" and q.answer == "no" for q in clarifications
            ):
                block("Revisa la propuesta antes de cambiar Student o ANOVA clásico por Welch.")
        groups = plan.comparison.groups if plan.comparison and method in INDEPENDENT_GROUPS else []
        if method in INDEPENDENT_GROUPS and not plan.comparison:
            group = next((v for v in source.variables if v.role == "group"), None)
            if group:
                rows = scoped_rows(tables[group.file_id][3], plan, group.file_id)
                groups = sorted(
                    {
                        str(r[group.column])
                        for r in rows
                        if r[group.column] is not None
                        and str(r[group.column]).strip()
                        and str(r[group.column]).strip() not in by_key[key(group)].missing_markers
                    }
                )
                if len(groups) > 20:
                    block("La comparación admite hasta 20 grupos. Revisa la propuesta.")
                    groups = []
                note(
                    "Grupos",
                    "verified",
                    "Se conservan las categorías presentes después de aplicar las decisiones y filtros del plan, sin combinar categorías.",
                )
        components.append(
            ExecutionComponent(
                source_index=index,
                method=method,
                design=design,
                equal_variances_confirmed=equal,
                group_values=groups,
                descriptive_intervals=False,
            )
        )
    multiplicity = plan.comparison.multiplicity if plan.comparison else "none"
    if multiplicity == "pending" or (
        not plan.comparison
        and (
            len(components) > 1
            or any(
                c.method in {"pearson", "spearman"} and len(sources(plan)[c.source_index].variables) > 2
                for c in components
            )
        )
    ):
        multiplicity = "holm"
        note(
            "Comparaciones múltiples",
            "inferred",
            "Si el plan no fija un ajuste, Holm controla el conjunto de contrastes de esta ejecución. Los intervalos siguen siendo individuales; puedes revisarlo en opciones avanzadas.",
        )
    spec = None
    if components:
        spec = ExecutionSpec(
            components=components,
            decisions=decisions,
            filters=plan_filters(plan),
            multiplicity=multiplicity or "none",
            decisions_confirmed=False,
        )
    states = []
    for index, source in enumerate(sources(plan)):
        relevant = [q for q in clarifications if index in question_owners.get(q.id, set())]
        problems = [b for b in blockers if index in blocker_owners.get(b, set())]
        current = next((c for c in components if c.source_index == index), None)
        state = (
            "UNSUPPORTED"
            if problems
            else "BLOCKED_UNCERTAINTY"
            if any(q.status == "unknown" for q in relevant)
            else "NEEDS_CLARIFICATION"
            if any(q.status == "pending" for q in relevant)
            else "READY"
            if current
            else "UNSUPPORTED"
        )
        problems.extend(q.limitation for q in relevant if q.status == "unknown")
        selected = spec.model_copy(update={"components": [current], "partial_execution": True}) if current else None
        fingerprint = ""
        if selected:
            selected_keys = {key(v) for v in source.variables} | {key(f.variable) for f in plan_filters(plan)}
            if plan.comparison and plan.comparison.strata:
                selected_keys.add(key(plan.comparison.strata.variable))
            local = selected.model_copy(
                update={"decisions": [d for d in decisions if key(d.variable) in selected_keys]}
            )
            fingerprint = digest(
                {
                    "source": source.model_dump(mode="json"),
                    "spec": local.model_dump(mode="json"),
                    "files": [f for f in provenance if f["id"] in {v.file_id for v in source.variables}],
                }
            )
            if state == "READY":
                try:
                    validate_spec(plan, selected, require_confirmation=False)
                    prepared = {fid: prepare(file, data, local, settings) for fid, (file, data, _, _) in tables.items()}
                    check_conditions(plan, selected, prepared)
                except AnalysisError as exc:
                    problems.append(str(exc))
                    state = "UNSUPPORTED"
        completed = next(
            (
                c
                for c in job.get("completed_components", [])
                if c.get("source_index") == index
                and c.get("fingerprint") == fingerprint
                and c.get("status") == "COMPLETED"
            ),
            None,
        )
        if completed and state == "READY":
            state = "COMPLETED"
        states.append(
            ComponentPreparation(
                id=f"component:{index}",
                source_index=index,
                method=current.method if current else source.method,
                variables=source.variables,
                status=state,
                fingerprint=fingerprint,
                question_ids=[q.id for q in relevant],
                blockers=problems,
                completed_run_id=completed.get("completed_run_id") if completed and state == "COMPLETED" else None,
                depends_on=getattr(source, "depends_on", []),
                decisions=[
                    d
                    for d in decisions
                    if key(d.variable)
                    in {key(v) for v in source.variables} | {key(f.variable) for f in plan_filters(plan)}
                ],
                filters=plan_filters(plan),
                evidence=[
                    e
                    for e in evidence
                    if e.subject
                    in {v.column for v in source.variables} | {"Originales", "Ausencias", f"Método {index + 1}"}
                    or any(q.status == "answered" and e.subject == q.prompt for q in relevant)
                ],
                assumptions=[q for q in relevant if q.subject.startswith(("design:", "variance:"))],
            )
        )
    # Una familia Holm no se divide entre ejecuciones con ajustes incompatibles.
    inference = [s for s in states if s.method != "descriptive"]
    if multiplicity == "holm" and any(s.status == "READY" for s in inference):
        for state in inference:
            if state.status == "COMPLETED":
                state.status = "READY"
                state.completed_run_id = None
                state.warnings.append(
                    "Se recalculará la familia inferencial completa para mantener un ajuste Holm compatible. Los resultados anteriores se conservan."
                )
    if multiplicity == "holm" and any(s.status not in {"READY", "COMPLETED"} for s in inference):
        for state in inference:
            if state.status == "READY":
                state.status = "NEEDS_CLARIFICATION"
                state.blockers.append(
                    "Pendiente de los otros contrastes de la familia Holm para conservar el control de multiplicidad."
                )
    try:
        for index in component_order(plan):
            state = states[index]
            for dependency in state.depends_on:
                if states[dependency].status not in {"READY", "COMPLETED"}:
                    state.status = states[dependency].status
                    state.blockers.append(f"Requiere completar el componente {dependency + 1} antes de continuar.")
    except AnalysisError as exc:
        for state in states:
            state.status = "UNSUPPORTED"
            state.blockers.append(str(exc))
    available = {s.source_index for s in states if s.status == "READY"}
    if spec:
        if available:
            spec = spec.model_copy(
                update={
                    "components": [c for c in components if c.source_index in available],
                    "partial_execution": len(available) < len(states),
                }
            )
        elif states and all(s.status == "COMPLETED" for s in states):
            spec = None
    uncertain = any(s.status == "BLOCKED_UNCERTAINTY" for s in states)
    if reviewing:
        questions.sort(key=lambda q: q.id != reviewing)
    blockers = list(dict.fromkeys(b for s in states for b in s.blockers)) if states else blockers
    warnings.extend(plan.limitations)
    if any(c.method != "descriptive" for c in components):
        warnings.append(
            "La independencia es un requisito de la inferencia y solo se confirma con evidencia del usuario. Los diagnósticos disponibles se informarán en los resultados; no prueban causalidad ni determinan el método por su valor p."
        )
    note(
        "Parámetros",
        "inferred",
        "Confianza 95 %, contraste bilateral y casos disponibles por procedimiento; no hay limpieza, uniones ni imputación automática.",
    )
    note(
        "Recursos previstos",
        "verified",
        "Catálogo existente: tablas, gráficos, resultados JSON, resumen y ZIP privados. Efectos e intervalos limitados a los implementados por cada método.",
    )
    fingerprint = digest(
        {
            "scope": scope,
            "answers": answers,
            "spec": spec.model_dump(mode="json") if spec else None,
            "components": [s.model_dump(mode="json") for s in states],
            "previous_runs": job.get("previous_runs", []),
        }
    )
    return ExecutionPreparation(
        request_id=uuid5(NAMESPACE_URL, f"statia:preparation:{job.get('proposal_id', '')}:{fingerprint}"),
        status="COMPLETED"
        if states and all(s.status == "COMPLETED" for s in states)
        else "READY"
        if states and all(s.status in {"READY", "COMPLETED"} for s in states)
        else "PARTIALLY_READY"
        if available
        else "UNSUPPORTED"
        if not states or all(s.status == "UNSUPPORTED" for s in states)
        else "NEEDS_CLARIFICATION"
        if any(q.id == reviewing for q in questions)
        else "BLOCKED_UNCERTAINTY"
        if uncertain
        else "NEEDS_CLARIFICATION"
        if questions
        else "UNSUPPORTED",
        components=states,
        specification=spec,
        methods=[CATALOG[c.method].name for c in components],
        reasons=reasons,
        evidence=evidence,
        warnings=list(dict.fromkeys(warnings)),
        questions=questions,
        clarifications=clarifications,
        blockers=blockers,
        files=provenance,
        fingerprint=fingerprint,
    ).model_dump(mode="json")


def scoped_rows(rows, plan, file_id):
    for selection in plan_filters(plan):
        if selection.variable.file_id == file_id:
            rows = [r for r in rows if str(r.get(selection.variable.column)) in selection.values]
    return rows


def check_conditions(plan, spec, prepared):
    """Solo estructura, tamaños y dispersión; no calcula estadísticos inferenciales."""
    for component in spec.components:
        source = sources(plan)[component.source_index]
        for file_id in {v.file_id for v in source.variables}:
            dataset = prepared[file_id]
            variables = [v for v in source.variables if v.file_id == file_id]
            rows = dataset.rows
            decisions = dataset.decisions

            def quantitative(v):
                require(
                    decisions[v.column].statistical_type in QUANTITATIVE,
                    f"«{v.column}» necesita una escala cuantitativa confirmada para este método.",
                )

            if component.method in INDEPENDENT_GROUPS:
                outcome = next(v for v in variables if v.role == "outcome")
                group = next(v for v in variables if v.role == "group")
                require(decisions[group.column].statistical_type in CATEGORICAL, "La agrupación debe ser categórica.")
                if component.method not in {"mann_whitney", "kruskal"}:
                    quantitative(outcome)
                else:
                    require(
                        decisions[outcome.column].statistical_type in QUANTITATIVE | {"ordinal"},
                        "Los contrastes de rangos requieren una medida cuantitativa o un orden confirmado.",
                    )
                levels = component.group_values or sorted(
                    {r[group.column] for r in rows if r[group.column] is not None}
                )
                require(
                    (
                        len(levels) == 2
                        if component.method in {"student_t", "welch_t", "mann_whitney"}
                        else 3 <= len(levels) <= 20
                    ),
                    "El número de grupos no es compatible con el método aceptado. Solicita una propuesta revisada.",
                )
                scopes = plan.comparison.strata.values if plan.comparison and plan.comparison.strata else [None]
                for scope in scopes:
                    current = (
                        [r for r in rows if str(r[plan.comparison.strata.variable.column]) == scope] if scope else rows
                    )
                    require(
                        len(
                            {
                                r[outcome.column]
                                for r in current
                                if r[group.column] in levels and r[outcome.column] is not None
                            }
                        )
                        > 1,
                        "Todos los resultados son iguales; el contraste no es calculable.",
                    )
                    for level in levels:
                        values = [
                            r[outcome.column]
                            for r in current
                            if r[group.column] == level and r[outcome.column] is not None
                        ]
                        require(len(values) >= 2, "Cada grupo o estrato necesita al menos dos observaciones completas.")
                        if component.method in {"student_t", "welch_t", "anova", "welch_anova"}:
                            require(
                                float(np.var(values)) > 0,
                                "Hay un grupo sin variación; este contraste no puede prepararse.",
                            )
            elif component.method in {"pearson", "spearman"}:
                from itertools import combinations

                measures = [v for v in variables if v.role not in {"group", "time", "pair_id"}]
                for a, b in combinations(measures, 2):
                    if component.method == "pearson":
                        quantitative(a)
                        quantitative(b)
                    complete = [
                        (r[a.column], r[b.column]) for r in rows if r[a.column] is not None and r[b.column] is not None
                    ]
                    require(
                        len(complete) >= 3 and all(len({r[i] for r in complete}) > 1 for i in (0, 1)),
                        "La correlación requiere al menos tres parejas completas y variables no constantes.",
                    )
            elif component.method in {"chi_square", "fisher_exact"}:
                require(
                    len(variables) == 2 and all(decisions[v.column].statistical_type in CATEGORICAL for v in variables),
                    "La asociación requiere dos variables categóricas.",
                )
                a, b = variables
                counts = Counter(
                    (r[a.column], r[b.column]) for r in rows if r[a.column] is not None and r[b.column] is not None
                )
                xs, ys = {x for x, _ in counts}, {y for _, y in counts}
                require(
                    2 <= len(xs) <= 20 and 2 <= len(ys) <= 20,
                    "La tabla de asociación requiere entre 2 y 20 categorías por variable.",
                )
                if component.method == "fisher_exact":
                    require(len(xs) == len(ys) == 2, "Fisher solo está implementado para tablas 2×2.")
                else:
                    n = sum(counts.values())
                    require(
                        all(
                            sum(c for (a, _), c in counts.items() if a == x)
                            * sum(c for (_, b), c in counts.items() if b == y)
                            / n
                            >= 5
                            for x in xs
                            for y in ys
                        ),
                        "Hay frecuencias esperadas menores que 5. Revisa la propuesta; Fisher es una alternativa para tablas 2×2.",
                    )
            elif component.method in {"paired_t", "wilcoxon"}:
                measures = [v for v in variables if v.role == "outcome"]
                pair = next(v for v in variables if v.role == "pair_id")
                for v in measures:
                    quantitative(v)
                ids = [r[pair.column] for r in rows if r[pair.column] is not None]
                require(len(ids) == len(set(ids)), "El identificador de par debe ser único.")
                require(
                    decisions[pair.column].statistical_type == "identifier",
                    "Declara el identificador de par como identificador.",
                )
                complete = [r for r in rows if all(r[v.column] is not None for v in [*measures, pair])]
                require(len(complete) >= 3, "Se necesitan al menos tres pares completos identificados.")
                differences = [r[measures[0].column] - r[measures[1].column] for r in complete]
                require(
                    float(np.var(differences)) > 0,
                    "Las diferencias entre medidas son constantes; el contraste pareado no está habilitado para ese caso.",
                )
                if component.method == "wilcoxon":
                    require(
                        sum(d != 0 for d in differences) >= 10,
                        "Wilcoxon asintótico requiere al menos diez diferencias no nulas.",
                    )
            elif component.method == "descriptive":
                groups = [v for v in variables if v.role == "group"]
                require(
                    len(groups) <= 1 and any(v.role != "group" for v in variables),
                    "El descriptivo necesita variables que resumir y admite una sola agrupación.",
                )
                if groups:
                    group = groups[0]
                    require(
                        decisions[group.column].statistical_type in CATEGORICAL,
                        "La agrupación descriptiva debe ser categórica.",
                    )
                    require(
                        len({r[group.column] for r in rows if r[group.column] is not None}) <= 20,
                        "El descriptivo admite hasta 20 grupos.",
                    )
                for v in variables:
                    decision = decisions[v.column]
                    require(
                        decision.statistical_type not in {"temporal", "identifier"},
                        "Los descriptivos temporales o de identificadores no están implementados.",
                    )
                    if decision.statistical_type in CATEGORICAL:
                        require(
                            len({r[v.column] for r in rows if r[v.column] is not None}) <= 100,
                            "La tabla descriptiva admite hasta 100 categorías por variable.",
                        )
