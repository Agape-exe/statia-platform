"""Contrato aditivo del contexto confirmado de una tesis, sin supuestos disciplinares."""

import json
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

Text = Annotated[str, StringConstraints(strict=True, max_length=2000)]
Item = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=500)]
Key = Annotated[str, StringConstraints(strict=True, min_length=1, max_length=80)]


class ResearchContext(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1] = 1
    research_title: Text | None = None
    research_problem: Text | None = None
    general_objective: Text | None = None
    specific_objectives: list[Item] = Field(default_factory=list, max_length=20)
    hypotheses: list[Item] = Field(default_factory=list, max_length=20)
    variables: list[Item] = Field(default_factory=list, max_length=20)
    methodological_design: Text | None = None
    population_sample: Text | None = None
    instruments: list[Item] = Field(default_factory=list, max_length=20)
    additional_information: Text | None = None
    additional_fields: dict[Key, Text | None] = Field(default_factory=dict, max_length=20)

    @field_validator("schema_version", mode="before")
    @classmethod
    def numeric_version(cls, value):
        if type(value) is not int:
            raise ValueError("schema_version debe ser el número entero 1.")
        return value

    @model_validator(mode="after")
    def bounded_document(self):
        if len(json.dumps(self.model_dump(), ensure_ascii=False, separators=(",", ":"))) > 16000:
            raise ValueError("El contexto supera los 16000 caracteres permitidos.")
        return self


class ContextSave(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    document: ResearchContext
    expected_revision: int = Field(ge=0, le=2147483646)
    confirmed: Literal[True]

    @field_validator("confirmed", mode="before")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("Confirma los datos antes de guardarlos.")
        return value
