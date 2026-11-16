"""Contratos de ejecución independientes de Plan v1 y de la prosa del proveedor."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, JsonValue

from app.models.chat import Selection, StrictModel, Variable

Method = Literal[
    "descriptive",
    "pearson",
    "spearman",
    "student_t",
    "welch_t",
    "anova",
    "welch_anova",
    "paired_t",
    "mann_whitney",
    "wilcoxon",
    "kruskal",
    "chi_square",
    "fisher_exact",
]
StatisticalType = Literal["continuous", "discrete", "ordinal", "nominal", "binary", "temporal", "identifier"]


class DataDecision(StrictModel):
    variable: Variable
    statistical_type: StatisticalType
    missing_markers: list[str] = Field(default_factory=list, max_length=30)
    retained_markers: list[str] = Field(default_factory=list, max_length=30)
    ordinal_order: list[str] = Field(default_factory=list, max_length=100)
    unit: str = Field(default="", max_length=60)


class ExecutionComponent(StrictModel):
    source_index: int = Field(ge=0, le=3)
    method: Method
    design: Literal["independent", "paired", "not_applicable"] = "not_applicable"
    equal_variances_confirmed: bool = False
    group_values: list[str] = Field(default_factory=list, max_length=20)
    posthoc: Literal["none", "welch_holm"] = "none"


class ExecutionSpec(StrictModel):
    schema_version: Literal[1] = 1
    components: list[ExecutionComponent] = Field(min_length=1, max_length=4)
    decisions: list[DataDecision] = Field(min_length=1, max_length=40)
    filters: list[Selection] = Field(default_factory=list, max_length=6)
    confidence_level: float = Field(default=0.95, ge=0.8, le=0.99, allow_inf_nan=False)
    alternative: Literal["two-sided"] = "two-sided"
    missing_policy: Literal["available_cases_per_procedure"] = "available_cases_per_procedure"
    multiplicity: Literal["none", "holm"] = "none"
    decisions_confirmed: bool


class ExecuteRequest(StrictModel):
    request_id: UUID
    specification: ExecutionSpec


class ResultTable(StrictModel):
    title: str
    columns: list[str]
    rows: list[dict[str, JsonValue]]


class Assumption(StrictModel):
    name: str
    status: Literal["evaluated", "pending", "violated", "not_applicable"]
    detail: str


class ComponentResult(StrictModel):
    source_index: int
    method: Method
    title: str
    status: Literal["completed", "partial", "failed"]
    error: str | None = None
    variables: list[Variable]
    scope: dict[str, str] = Field(default_factory=dict)
    sample: dict[str, JsonValue] = Field(default_factory=dict)
    statistics: dict[str, JsonValue] = Field(default_factory=dict)
    assumptions: list[Assumption] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    tables: list[ResultTable] = Field(default_factory=list)
    charts: list[str] = Field(default_factory=list)
    interpretation: str = ""


class AnalysisResult(StrictModel):
    schema_version: Literal[1] = 1
    run_id: UUID
    project_id: UUID
    conversation_id: UUID
    proposal_id: UUID
    created_at: datetime
    title: str
    specification: ExecutionSpec
    plan_snapshot: dict[str, JsonValue]
    files: list[dict[str, JsonValue]]
    dependencies: dict[str, str]
    components: list[ComponentResult]
    status: Literal["completed", "partial", "failed"]
    summary: str


class Artifact(StrictModel):
    id: UUID
    run_id: UUID
    project_id: UUID
    name: str
    mime_type: str
    size_bytes: int
    sha256: str


class RunView(StrictModel):
    id: UUID
    project_id: UUID
    conversation_id: UUID
    proposal_id: UUID
    request_id: UUID
    title: str
    status: Literal["running", "completed", "partial", "failed"]
    created_at: datetime
    finished_at: datetime | None = None
    error: str | None = None
    result: AnalysisResult | None = None
    artifact_count: int = 0
    methods: list[str] = Field(default_factory=list)
    artifacts: list[Artifact] = Field(default_factory=list)


class ProcedureInfo(StrictModel):
    code: Method
    name: str
    families: list[str]
    variable_types: str
    design: str
    groups: str
    assumptions: list[str]
    parameters: list[str]
    statistics: list[str]
    effects: list[str]
    limitations: list[str]
