"""Contrato de respuesta según intención y normalizaciones estrictamente equivalentes."""

import json

from app.models.chat import AssistantReply

NON_PLANNING = {"understanding", "methodology", "document"}


def parse_assistant_reply(text, interaction_mode=None):
    data = json.loads(text)
    if interaction_mode in NON_PLANNING and isinstance(data, dict):
        # Los planes no solicitados jamás se validan, muestran ni persisten.
        data.update(proposals=[], selected_variables=[], confirmation_required=False, goal_change=False)
        if data.get("suggested_stage") == "proposal":
            data["suggested_stage"] = "understanding"
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
