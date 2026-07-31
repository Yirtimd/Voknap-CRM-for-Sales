from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


CadenceStepType = Literal["task", "call", "manual_email", "automatic_email"]


class CadenceStepInput(BaseModel):
    step_type: CadenceStepType
    delay_minutes: int = Field(default=0, ge=0, le=525_600)
    title: str = Field(min_length=2, max_length=255)
    body: str | None = Field(default=None, max_length=100_000)
    task_priority: Literal["low", "normal", "high", "urgent"] = "normal"


class CadenceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=2_000)
    steps: list[CadenceStepInput] = Field(min_length=1, max_length=50)
    is_active: bool = True


class CadenceUpdate(BaseModel):
    version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=2_000)
    steps: list[CadenceStepInput] | None = Field(default=None, min_length=1, max_length=50)
    is_active: bool | None = None


class CadenceStepResponse(CadenceStepInput):
    id: UUID
    position: int


class CadenceResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    is_active: bool
    steps: list[CadenceStepResponse]
    version: int
    created_by_id: UUID
    updated_by_id: UUID
    created_at: datetime
    updated_at: datetime


class EnrollmentCreate(BaseModel):
    cadence_id: UUID
    contact_id: UUID
    deal_id: UUID | None = None
    connector_account_id: UUID | None = None


class EnrollmentAction(BaseModel):
    version: int = Field(ge=1)
    reason: str | None = Field(default=None, max_length=2_000)


class EnrollmentResponse(BaseModel):
    id: UUID
    cadence_id: UUID
    cadence_name: str
    contact_id: UUID
    contact_name: str
    company_id: UUID
    deal_id: UUID | None
    connector_account_id: UUID | None
    owner_id: UUID
    status: str
    current_step: int
    step_count: int
    next_run_at: datetime | None
    last_executed_at: datetime | None
    stop_reason: str | None
    version: int
    created_at: datetime
    updated_at: datetime


class ExecutionResponse(BaseModel):
    id: UUID
    enrollment_id: UUID
    step_id: UUID
    step_position: int
    step_type: str
    title: str
    status: str
    task_id: UUID | None
    communication_event_id: UUID | None
    integration_job_id: UUID | None
    error: str | None
    scheduled_at: datetime
    executed_at: datetime | None


class RunDueResponse(BaseModel):
    evaluated: int
    executed: int


class EmailAccountOption(BaseModel):
    id: UUID
    title: str
    status: str


class EnrollmentListFilters(BaseModel):
    contact_id: UUID | None = None
    company_id: UUID | None = None
    status: str | None = None

    @model_validator(mode="after")
    def validate_status(self):
        if self.status and self.status not in {
            "active",
            "paused",
            "completed",
            "stopped",
            "replied",
            "failed",
        }:
            raise ValueError("Unsupported enrollment status")
        return self
