"""Contrato de respuesta según intención y normalizaciones estrictamente equivalentes."""

import json

from pydantic import ValidationError

from app.models.chat import AssistantReply, Plan
from app.services.plan_capabilities import LABELS

NON_PLANNING = {"understanding", "methodology", "document"}


def parse_assistant_reply(text, interaction_mode=None, *, validate_plans_separately=False):
    data = json.loads(text)
    if isinstance(data, dict) and isinstance(data.get("proposals"), list):
        for plan in data["proposals"]:
            if not isinstance(plan, dict) or not isinstance(plan.get("expected_outputs"), list):
                continue
            for i, item in enumerate(plan["expected_outputs"]):
                if isinstance(item, dict) and set(item) == {"product", "component"}:
                    product, component = item["product"], item["component"]
                    if isinstance(product, str) and product in LABELS and component in ("plan", "1", "2", "3", "4"):
                        prefix = "" if component == "plan" else f"Componente {component}: "
                        plan["expected_outputs"][i] = prefix + LABELS[product]
    if interaction_mode in NON_PLANNING and isinstance(data, dict):
        # Los planes no solicitados jamás se validan, muestran ni persisten.
        # Conserva la contradicción de un anuncio estructurado sin objetos para
        # que la evaluación compartida pueda pedir una corrección.
        if data.get("proposals") or data.get("goal_change"):
            data["confirmation_required"] = False
            if data.get("suggested_stage") == "proposal":
                data["suggested_stage"] = "understanding"
        data.update(proposals=[], selected_variables=[], goal_change=False)
    elif validate_plans_separately and isinstance(data, dict):
        raw_plans = data.get("proposals")
        if isinstance(raw_plans, list) and 1 <= len(raw_plans) <= 4:
            plans, invalid = [], []
            for index, raw in enumerate(raw_plans):
                try:
                    plans.append(Plan.model_validate(raw))
                except ValidationError:
                    invalid.append(index)
            result = AssistantReply.model_validate({**data, "proposals": plans})
            result._invalid_plan_positions = tuple(invalid)
            return result
    return AssistantReply.model_validate(data)


def normalize_reply(reply, interaction_mode):
    if interaction_mode in NON_PLANNING:
        return parse_assistant_reply(reply.model_dump_json(), interaction_mode)
    plans = []
    for plan in reply.proposals:
        if len(plan.components) == 1:
            step = plan.components[0]
            same_variables = step.variables == plan.variables
            if (
                not same_variables
                and step.procedure == "group_comparison"
                and len(step.variables) == len(plan.variables) == 2
                and {v.role for v in step.variables} == {"outcome", "group"}
            ):
                # Los roles identifican cada entrada; el orden del contraste
                # se conserva en comparison.groups, no en estas dos referencias.
                same_variables = step.variables == plan.variables[::-1]
            if (
                same_variables
                and not step.depends_on
                and step.method == plan.method
                and (step.procedure == plan.procedure or plan.procedure == "integral")
            ):
                # Un único paso redundante: mismas referencias, roles, método y decisiones.
                plan = plan.model_copy(update={"procedure": step.procedure, "components": []})
        plans.append(plan)
    return reply.model_copy(update={"proposals": plans})
