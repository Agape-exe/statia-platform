from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

Stage = Literal['reuse', 'instrument', 'upload_instrument', 'upload_dataset', 'understanding', 'clarification', 'goal', 'proposal', 'ready']


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ConversationCreate(StrictModel):
    source_conversation_id: UUID | None = None


class Rename(StrictModel):
    title: str = Field(min_length=1, max_length=120)


class Turn(StrictModel):
    request_id: UUID
    content: str = Field(default="", max_length=6000)
    action: Literal['message', 'reuse', 'new_files', 'instrument_yes', 'instrument_no', 'instruments_done', 'files_ready', 'keep_goal'] = 'message'
    file_ids: list[UUID] = Field(default_factory=list, max_length=30)
    share_samples: bool = False
    share_instrument_text: bool = False


class Decision(StrictModel):
    status: Literal['accepted', 'rejected']


class Variable(StrictModel):
    file_id: str = Field(min_length=1, max_length=36)
    sheet: str = Field(min_length=1, max_length=120)
    column: str = Field(min_length=1, max_length=240)
    role: Literal['outcome', 'predictor', 'group', 'time', 'pair_id', 'description']


class Join(StrictModel):
    left: Variable
    right: Variable
    justification: str = Field(min_length=1, max_length=1000)
    confirmed_by_user: bool = False


class Plan(StrictModel):
    # Versión interna exacta; no forma parte del contrato enviado al proveedor.
    schema_version: int = Field(default=1, ge=1, le=1, strict=True)
    title: str = Field(min_length=1, max_length=160)
    objective: str = Field(min_length=1, max_length=2000)
    variables: list[Variable] = Field(min_length=1, max_length=40)
    procedure: Literal['descriptive', 'exploratory', 'group_comparison', 'correlation', 'paired_comparison', 'inferential', 'integral']
    method: str = Field(min_length=1, max_length=1500)
    justification: str = Field(min_length=1, max_length=1500)
    requirements: list[str] = Field(min_length=1, max_length=12)
    limitations: list[str] = Field(min_length=1, max_length=12)
    expected_outputs: list[str] = Field(min_length=1, max_length=12)
    joins: list[Join] = Field(default_factory=list, max_length=5)
    methodology_confirmed: bool = False


class AssistantReply(StrictModel):
    response: str = Field(min_length=1, max_length=12000)
    suggested_stage: Literal['understanding', 'clarification', 'goal', 'proposal']
    detected_goal: str | None = Field(default=None, max_length=2000)
    suggested_title: str | None = Field(default=None, min_length=1, max_length=120)
    questions: list[str] = Field(default_factory=list, max_length=8)
    involved_file_ids: list[str] = Field(default_factory=list, max_length=30)
    selected_variables: list[Variable] = Field(default_factory=list, max_length=60)
    proposals: list[Plan] = Field(default_factory=list, max_length=4)
    warnings: list[str] = Field(default_factory=list, max_length=12)
    confirmation_required: bool = False
    goal_change: bool = False
    goal_change_reason: str | None = Field(default=None, max_length=1200)
    context_summary: str | None = Field(default=None, max_length=6000)
