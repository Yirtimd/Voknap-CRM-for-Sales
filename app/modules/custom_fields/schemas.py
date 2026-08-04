from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


EntityType = Literal["companies", "contacts", "leads", "deals", "tasks"]
FieldType = Literal["text", "number", "date", "datetime", "boolean", "select", "multi_select"]
FilterOperator = Literal["eq", "neq", "contains", "gt", "gte", "lt", "lte", "is_empty"]


class FieldDefinitionCreate(BaseModel):
    entity_type: EntityType
    code: str = Field(min_length=2, max_length=80, pattern=r"^[a-z][a-z0-9_]*$")
    label: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    field_type: FieldType
    options: list[str] = Field(default_factory=list, max_length=100)
    is_required: bool = False
    is_filterable: bool = True
    is_reportable: bool = True
    is_active: bool = True
    sort_order: int = Field(default=100, ge=0, le=10000)

    @model_validator(mode="after")
    def validate_options(self):
        if self.field_type in {"select", "multi_select"} and not self.options:
            raise ValueError("options are required for select fields")
        if self.field_type not in {"select", "multi_select"} and self.options:
            raise ValueError("options are supported only for select fields")
        normalized = [item.strip() for item in self.options if item.strip()]
        if len(normalized) != len(set(normalized)):
            raise ValueError("options must be unique")
        self.options = normalized
        return self


class FieldDefinitionUpdate(BaseModel):
    version: int = Field(ge=1)
    label: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    options: list[str] | None = Field(default=None, max_length=100)
    is_required: bool | None = None
    is_filterable: bool | None = None
    is_reportable: bool | None = None
    is_active: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=10000)

    @model_validator(mode="after")
    def normalize_options(self):
        if self.options is not None:
            normalized = [item.strip() for item in self.options if item.strip()]
            if len(normalized) != len(set(normalized)):
                raise ValueError("options must be unique")
            self.options = normalized
        return self


class FieldDefinitionResponse(BaseModel):
    id: UUID
    entity_type: str
    code: str
    label: str
    description: str | None
    field_type: str
    options: list[str]
    is_required: bool
    is_filterable: bool
    is_reportable: bool
    is_active: bool
    sort_order: int
    version: int
    created_at: datetime
    updated_at: datetime


class FieldValueInput(BaseModel):
    field_id: UUID
    value: Any = None
    version: int = Field(default=0, ge=0)


class FieldValuesUpdate(BaseModel):
    values: list[FieldValueInput] = Field(max_length=100)


class FieldValueResponse(BaseModel):
    field: FieldDefinitionResponse
    value: Any = None
    version: int = 0
    updated_at: datetime | None = None


class CustomFieldFilter(BaseModel):
    field_id: UUID
    operator: FilterOperator
    value: Any = None


class EntitySearchRequest(BaseModel):
    filters: list[CustomFieldFilter] = Field(min_length=1, max_length=20)


class EntitySearchResponse(BaseModel):
    entity_type: str
    entity_ids: list[UUID]
    matched: int


class CustomFieldReportResponse(BaseModel):
    entity_type: str
    group_field: FieldDefinitionResponse
    metric: str
    measure: str | None
    buckets: list[dict[str, Any]]
    generated_at: datetime
