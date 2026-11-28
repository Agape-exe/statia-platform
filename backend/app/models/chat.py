from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

Stage = Literal['reuse', 'instrument', 'upload_instrument', 'upload_dataset', 'understanding', 'clarification', 'goal', 'proposal', 'ready']
ProviderId = Literal['gemini', 'openai']


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ConversationCreate(StrictModel):
    source_conversation_id: UUID | None = None
    provider: ProviderId = 'gemini'


class ProviderChange(StrictModel):
    provider: ProviderId
    expected_provider: ProviderId


class Rename(StrictModel):
    title: str = Field(min_length=1, max_length=120)


class Turn(StrictModel):
    request_id: UUID
    content: str = Field(default="", max_length=6000)
    action: Literal['message', 'reuse', 'new_files', 'instrument_yes', 'instrument_no', 'instruments_done', 'files_ready', 'keep_goal', 'prepare_execution', 'clarify_execution', 'review_execution', 'request_descriptive', 'cancel_execution'] = 'message'
    file_ids: list[UUID] = Field(default_factory=list, max_length=30)
    share_samples: bool = False
    share_instrument_text: bool = False
    proposal_id: UUID | None = None
    question_id: str | None = Field(default=None, max_length=64)
    answer: str | None = Field(default=None, max_length=240)


class Decision(StrictModel):
    status: Literal['accepted', 'rejected']


class FileRows(StrictModel):
    columns: list[str]
    rows: list[list[str | None]]
    offset: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    total_rows: int = Field(ge=0)
    has_more: bool
    sheet: str | None


class Variable(StrictModel):
    file_id: str = Field(min_length=1, max_length=36)
    sheet: str = Field(min_length=1, max_length=120)
    column: str = Field(min_length=1, max_length=240)
    role: Literal['outcome', 'predictor', 'group', 'time', 'pair_id', 'description', 'filter']


class Join(StrictModel):
    left: Variable
    right: Variable
    justification: str = Field(min_length=1, max_length=1000)
    confirmed_by_user: bool = False


Procedure = Literal['descriptive', 'exploratory', 'group_comparison', 'correlation', 'paired_comparison', 'inferential', 'integral']


class Selection(StrictModel):
    variable: Variable
    values: list[str] = Field(min_length=1, max_length=20)


class EffectSize(StrictModel):
    name: Literal['cohen_d', 'hedges_g', 'glass_delta', 'mean_difference']
    standardizer: Literal['pooled_sd', 'average_variance_sd', 'reference_group_sd', 'none']
    definition: str = Field(min_length=12, max_length=1500)
    correction: str = Field(min_length=1, max_length=1000)
    confidence_interval: str = Field(min_length=1, max_length=1000)


class Comparison(StrictModel):
    design: Literal['independent', 'paired', 'unknown']
    groups: list[str] = Field(min_length=2, max_length=2)
    filters: list[Selection] = Field(default_factory=list, max_length=6)
    strata: Selection | None = None
    independence: str = Field(min_length=1, max_length=1200)
    valid_observations: str = Field(min_length=1, max_length=1200)
    missing_data: str = Field(min_length=1, max_length=1200)
    outliers: str = Field(min_length=1, max_length=1200)
    normality: str = Field(min_length=1, max_length=1200)
    variance_assumption: Literal['unequal_allowed', 'equal_required', 'unassessed']
    effect_size: EffectSize
    purpose: Literal['exploratory', 'confirmatory']
    multiplicity: Literal['holm', 'none', 'pending']
    multiplicity_reason: str = Field(min_length=1, max_length=1200)


class AnalysisComponent(StrictModel):
    procedure: Procedure
    method: str = Field(min_length=1, max_length=1500)
    variables: list[Variable] = Field(min_length=1, max_length=40)
    depends_on: list[int] = Field(default_factory=list, max_length=4)


class TypeConfirmation(StrictModel):
    variable: Variable
    statistical_type: Literal['continuous', 'discrete']


class Plan(StrictModel):
    # Versión interna exacta; no forma parte del contrato enviado al proveedor.
    schema_version: int = Field(default=1, ge=1, le=1, strict=True)
    title: str = Field(min_length=1, max_length=160)
    objective: str = Field(min_length=1, max_length=2000)
    variables: list[Variable] = Field(min_length=1, max_length=40)
    procedure: Procedure
    method: str = Field(min_length=1, max_length=1500)
    justification: str = Field(min_length=1, max_length=1500)
    requirements: list[str] = Field(min_length=1, max_length=12)
    limitations: list[str] = Field(min_length=1, max_length=12)
    expected_outputs: list[str] = Field(min_length=1, max_length=12)
    joins: list[Join] = Field(default_factory=list, max_length=5)
    methodology_confirmed: bool = False
    # Campos aditivos en JSONB: los planes previos mantienen su representación.
    comparison: Comparison | None = None
    components: list[AnalysisComponent] = Field(default_factory=list, max_length=4)
    filters: list[Selection] = Field(default_factory=list, max_length=6)
    # Decisiones explícitas del usuario, añadidas por el servidor; sin alterar perfiles.
    type_confirmations: list[TypeConfirmation] = Field(default_factory=list, max_length=40)


class AssistantReply(StrictModel):
    _invalid_plan_positions: tuple[int, ...] = PrivateAttr(default=())

    response: str = Field(min_length=1, max_length=12000)
    suggested_stage: Literal['understanding', 'clarification', 'goal', 'proposal']
    detected_goal: str | None = Field(default=None, max_length=2000)
    suggested_title: str | None = Field(default=None, min_length=1, max_length=120)
    questions: list[str] = Field(default_factory=list, max_length=8)
    clarification_required: bool = False
    involved_file_ids: list[str] = Field(default_factory=list, max_length=30)
    selected_variables: list[Variable] = Field(default_factory=list, max_length=60)
    proposals: list[Plan] = Field(default_factory=list, max_length=4)
    warnings: list[str] = Field(default_factory=list, max_length=12)
    confirmation_required: bool = False
    goal_change: bool = False
    goal_change_reason: str | None = Field(default=None, max_length=1200)
    context_summary: str | None = Field(default=None, max_length=6000)
