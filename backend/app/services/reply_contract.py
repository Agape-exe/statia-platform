"""Contrato de respuesta según intención y normalizaciones estrictamente equivalentes."""

import json

from pydantic import ValidationError

from app.models.chat import AssistantReply, Plan

NON_PLANNING = {"understanding", "methodology", "document"}


def parse_assistant_reply(text, interaction_mode=None, *, validate_plans_separately=False):
    data = json.loads(text)
    if interaction_mode in NON_PLANNING and isinstance(data, dict):
        # Los planes no solicitados jamás se validan, muestran ni persisten.
        data.update(proposals=[], selected_variables=[], confirmation_required=False, goal_change=False)
        if data.get("suggested_stage") == "proposal":
            data["suggested_stage"] = "understanding"
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
            same_variables = [v.model_dump_json() for v in step.variables] == [
                v.model_dump_json() for v in plan.variables
            ]
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
