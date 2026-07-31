from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


TriggerType = Literal[
    "lead.created",
    "lead.score_changed",
    "deal.created",
    "deal.updated",
    "deal.stage_changed",
    "deal.score_changed",
    "communication.created",
    "schedule.deal_inactive",
]
ConditionOperator = Literal[
    "eq",
    "neq",
    "gt",
    "gte",
    "lt",
    "lte",
    "in",
    "contains",
    "is_empty",
]
ActionType = Literal[
    "assign_owner",
    "create_task",
    "send_template",
    "request_approval",
    "update_next_action",
]


class AutomationCondition(BaseModel):
    field: str = Field(min_length=1, max_length=100, pattern=r"^[a-z][a-z0-9_.]*$")
    operator: ConditionOperator
    value: Any = None


class AutomationAction(BaseModel):
    type: ActionType
    config: dict[str, Any] = Field(default_factory=dict)


class WorkflowCreate(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    trigger_type: TriggerType
    conditions: list[AutomationCondition] = Field(default_factory=list, max_length=20)
    condition_logic: Literal["all", "any"] = "all"
    actions: list[AutomationAction] = Field(min_length=1, max_length=20)
    priority: int = Field(default=100, ge=0, le=10000)
    is_active: bool = True


class WorkflowUpdate(BaseModel):
    version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=2, max_length=160)
    description: str | None = Field(default=None, max_length=2000)
    trigger_type: TriggerType | None = None
    conditions: list[AutomationCondition] | None = Field(default=None, max_length=20)
    condition_logic: Literal["all", "any"] | None = None
    actions: list[AutomationAction] | None = Field(default=None, min_length=1, max_length=20)
    priority: int | None = Field(default=None, ge=0, le=10000)
    is_active: bool | None = None


class WorkflowResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    trigger_type: str
    conditions: list[AutomationCondition]
    condition_logic: str
    actions: list[AutomationAction]
    priority: int
    is_active: bool
    version: int
    created_by_id: UUID
    updated_by_id: UUID
    created_at: datetime
    updated_at: datetime


class MessageTemplateCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    channel: str = Field(default="email", min_length=2, max_length=40)
    subject: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1, max_length=20000)


class MessageTemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    channel: str | None = Field(default=None, min_length=2, max_length=40)
    subject: str | None = Field(default=None, min_length=1, max_length=255)
    body: str | None = Field(default=None, min_length=1, max_length=20000)
    is_active: bool | None = None


class MessageTemplateResponse(BaseModel):
    id: UUID
    name: str
    channel: str
    subject: str
    body: str
    is_active: bool
    created_by_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AutomationRunResponse(BaseModel):
    id: UUID
    workflow_id: UUID
    event_key: str
    trigger_type: str
    entity_type: str
    entity_id: UUID
    actor_id: UUID | None
    status: str
    result: list[dict]
    error: str | None
    started_at: datetime
    completed_at: datetime | None


class ApprovalResponse(BaseModel):
    id: UUID
    workflow_id: UUID
    run_id: UUID
    entity_type: str
    entity_id: UUID
    title: str
    reason: str | None
    requested_by_id: UUID | None
    assigned_to_id: UUID | None
    status: str
    priority: str
    due_at: datetime | None
    version: int
    decision_comment: str | None
    decided_by_id: UUID | None
    decided_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ApprovalDecision(BaseModel):
    version: int = Field(ge=1)
    decision: Literal["approved", "rejected"]
    comment: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_rejection_comment(self):
        if self.decision == "rejected" and not self.comment:
            raise ValueError("comment is required for rejection")
        return self


class ApprovalReassign(BaseModel):
    version: int = Field(ge=1)
    assigned_to_id: UUID
    comment: str | None = Field(default=None, max_length=2000)


class ApprovalCancel(BaseModel):
    version: int = Field(ge=1)
    comment: str = Field(min_length=1, max_length=2000)


class ApprovalHistoryResponse(BaseModel):
    id: UUID
    approval_id: UUID
    action: str
    from_status: str | None
    to_status: str | None
    actor_id: UUID | None
    comment: str | None
    metadata: dict[str, Any]
    created_at: datetime


class ScheduledRunResponse(BaseModel):
    evaluated: int
    matched_runs: int


class OutboxResponse(BaseModel):
    id: UUID
    run_id: UUID
    template_id: UUID
    entity_type: str
    entity_id: UUID
    channel: str
    recipient: str
    subject: str
    body: str
    status: str
    attempts: int
    available_at: datetime
    sent_at: datetime | None
    last_error: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class OutboxStatusUpdate(BaseModel):
    status: Literal["sent", "failed", "cancelled"]
    error: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def require_error_for_failure(self):
        if self.status == "failed" and not self.error:
            raise ValueError("error is required for failed status")
        return self
