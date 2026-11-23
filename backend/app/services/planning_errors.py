"""Códigos internos permitidos; mensajes/datos del proveedor nunca se registran."""
import logging
from dataclasses import dataclass

CATEGORIES = frozenset({
    'output_scope', 'output_capability', 'requested_scope',
    'column_reference', 'objective_variables', 'component_variables', 'variable_type',
    'comparison_design', 'comparison_scope', 'effect_definition', 'independence',
    'essential_clarification', 'recommendation_coverage', 'cross_table_relation',
    'response_content', 'document_evidence', 'semantic_validation', 'internal_contract',
    'proposal_missing', 'proposal_limit',
})

FAILURE_DETAILS = {
    'proposal_missing': 'El proveedor no devolvió una propuesta estructurada para revisar.',
    'proposal_limit': 'El proveedor excedió la cantidad solicitada de propuestas.',
    'column_reference': 'La propuesta cita un dataset, una hoja o una columna que no se puede usar.',
    'objective_variables': 'Las variables del objetivo y del procedimiento no coinciden con la selección.',
    'component_variables': 'La selección de variables del plan y de sus procedimientos no coincide.',
    'essential_clarification': 'Quedó una decisión metodológica imprescindible sin resolver.',
    'output_scope': 'La propuesta incluye entregables cuyo alcance no se puede verificar.',
    'output_capability': 'El procedimiento no puede producir todos los entregables propuestos.',
    'requested_scope': 'El plan no cumple el alcance estadístico solicitado.',
    'internal_contract': 'La respuesta no incluyó todos los campos obligatorios en el formato esperado.',
    'response_content': 'La respuesta incluyó una afirmación que Statia no pudo verificar.',
}


class PlanningError(ValueError):
    def __init__(self, category, message):
        self.category = category if category in CATEGORIES else 'semantic_validation'
        super().__init__(message)


@dataclass(frozen=True)
class PlanningIssue:
    category: str
    message: str
    plan_index: int | None = None

    @classmethod
    def from_error(cls, error, plan_index=None):
        category = error.category if isinstance(error, PlanningError) else 'semantic_validation'
        return cls(category, str(error), plan_index)

    def safe_metadata(self):
        return {'category': self.category, 'plan_index': self.plan_index}


def log_issues(issues, attempt):
    for issue in issues:
        logging.getLogger(__name__).warning('Planning validation attempt=%d plan_index=%s category=%s',
                                            attempt, issue.plan_index, issue.category)
