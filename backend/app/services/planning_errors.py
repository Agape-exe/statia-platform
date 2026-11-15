"""Códigos internos permitidos; mensajes/datos del proveedor nunca se registran."""
import logging
from dataclasses import dataclass

CATEGORIES = frozenset({
    'column_reference', 'objective_variables', 'component_variables', 'variable_type',
    'comparison_design', 'comparison_scope', 'effect_definition', 'independence',
    'essential_clarification', 'recommendation_coverage', 'cross_table_relation',
    'response_content', 'semantic_validation', 'internal_contract',
})


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
