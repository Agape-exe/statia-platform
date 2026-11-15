"""Evaluación por alternativa; nunca persiste un plan que no supere su contrato."""
from dataclasses import dataclass

from app.models.chat import Plan
from app.services.gemini import validate_plan, validate_reply, validate_recommendations
from app.services.planning_errors import PlanningIssue


@dataclass
class Assessment:
    valid_plans: list[Plan]
    issues: list[PlanningIssue]
    envelope_valid: bool


def assess_reply(reply, files, project, context):
    issues, valid = [], []
    try:
        validate_reply(reply, files, project, context, validate_plans=False, check_recommendations=False)
    except ValueError as exc:
        issues.append(PlanningIssue.from_error(exc))
    envelope_valid = not issues
    for index, plan in enumerate(reply.proposals):
        try:
            validate_plan(plan, files, project, context)
            valid.append(plan)
        except ValueError as exc:
            issues.append(PlanningIssue.from_error(exc, index))
    try:
        validate_recommendations(reply.model_copy(update={'proposals': valid}), project, context)
    except ValueError as exc:
        issues.append(PlanningIssue.from_error(exc))
    return Assessment(valid, issues, envelope_valid)


def retain_valid_plans(reply, assessment, files, project, context):
    """Aviso operativo explícito; no recicla prosa que pueda prometer planes descartados."""
    if not assessment.envelope_valid or not assessment.valid_plans or reply.goal_change:
        return None
    count = len(assessment.valid_plans)
    count_text = 'Se validó una alternativa.' if count == 1 else f'Se validaron {count} alternativas.'
    notice = (count_text + ' La respuesta no completó todas las alternativas solicitadas. '
              'Solo se muestran planes validados; puedes revisarlos o pedir otras opciones.')
    variables = {(v.file_id, v.sheet, v.column, v.role): v for p in assessment.valid_plans for v in p.variables}
    retained = reply.model_copy(update={
        'response': notice, 'proposals': assessment.valid_plans,
        # Resumen acotado; las listas completas permanecen intactas en cada plan.
        'selected_variables': list(variables.values())[:60],
        'involved_file_ids': sorted({v.file_id for v in variables.values()}),
        'questions': [], 'warnings': ['Respuesta parcial: se muestran únicamente las alternativas validadas disponibles.'], 'clarification_required': False,
        'context_summary': None, 'suggested_title': None, 'detected_goal': None,
        'goal_change_reason': None, 'suggested_stage': 'proposal', 'confirmation_required': True,
    })
    # Revalidar el contrato interno completo y todos los planes antes de persistir el subconjunto.
    retained = type(reply).model_validate(retained.model_dump())
    validate_reply(retained, files, project, context, check_recommendations=False)
    return retained
