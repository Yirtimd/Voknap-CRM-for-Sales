from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator


class ContactCreate(BaseModel):
    company_id: UUID
    name: str = Field(min_length=2, max_length=255)
    phone: str | None = Field(default=None, max_length=80)
    email: EmailStr | None = None
    company_name: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, max_length=120)
    owner_id: UUID | None = None


class ContactResponse(BaseModel):
    id: UUID
    company_id: UUID
    name: str
    phone: str | None
    email: str | None
    company_name: str | None
    role: str | None
    owner_id: UUID | None = None
    actions: dict[str, bool] = Field(default_factory=dict)
    is_archived: bool = False
    deleted_at: datetime | None = None
    version: int = 1
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class CompanyCreate(BaseModel):
    name: str = Field(min_length=2, max_length=255)
    website: str | None = Field(default=None, max_length=255)
    industry: str | None = Field(default=None, max_length=120)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    region: str | None = Field(default=None, max_length=120)
    description: str | None = None
    status: str = Field(default="active", max_length=40)
    company_type: str | None = Field(default=None, max_length=40)
    health_score: int | None = Field(default=None, ge=0, le=100)
    client_since: datetime | None = None
    owner_id: UUID | None = None
    next_action_id: UUID | None = None


class CompanyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    website: str | None = Field(default=None, max_length=255)
    industry: str | None = Field(default=None, max_length=120)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    region: str | None = Field(default=None, max_length=120)
    description: str | None = None
    status: str | None = Field(default=None, max_length=40)
    company_type: str | None = Field(default=None, max_length=40)
    health_score: int | None = Field(default=None, ge=0, le=100)
    client_since: datetime | None = None
    owner_id: UUID | None = None
    next_action_id: UUID | None = None


class OwnerResponse(BaseModel):
    id: UUID | None = None
    name: str | None = None
    avatar_url: str | None = None
    initials: str | None = None


class CompanyResponse(BaseModel):
    id: UUID
    name: str
    website: str | None
    industry: str | None
    country_code: str | None = None
    region: str | None = None
    description: str | None
    status: str
    status_label: str | None = None
    company_type: str | None
    health_score: int | None = None
    client_since: datetime | None
    source: str | None = None
    owner: OwnerResponse | None = None
    territory_id: UUID | None = None
    next_action_id: UUID | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class CompanyWorkspaceResponse(BaseModel):
    company: CompanyResponse
    overview: dict
    health: dict = Field(default_factory=dict)
    next_action: dict | None = None
    contacts: list[ContactResponse]
    deals: list["DealResponse"]
    tasks: list["TaskResponse"]
    activities: list[dict]
    files: list[dict] = Field(default_factory=list)
    knowledge_documents: list[dict] = Field(default_factory=list)
    ai_summary: str
    ai_insights: list[str]


class CompanyFileCreate(BaseModel):
    company_id: UUID
    deal_id: UUID | None = None
    contact_id: UUID | None = None
    activity_id: UUID | None = None
    name: str = Field(min_length=1, max_length=255)
    file_type: str | None = Field(default=None, max_length=40)
    mime_type: str | None = Field(default=None, max_length=120)
    file_size: int | None = Field(default=None, ge=0)
    storage_key: str = Field(min_length=1, max_length=500)
    download_url: str | None = Field(default=None, max_length=500)


class CompanyFileResponse(BaseModel):
    id: UUID
    company_id: UUID | None
    deal_id: UUID | None
    contact_id: UUID | None
    activity_id: UUID | None
    uploaded_by_id: UUID | None
    name: str
    file_type: str | None
    mime_type: str | None
    file_size: int | None
    storage_key: str
    download_url: str
    created_at: datetime

    model_config = {"from_attributes": True}


class CustomerInsightUpsert(BaseModel):
    health_score: int | None = Field(default=None, ge=0, le=100)
    health_label: str | None = Field(default=None, max_length=80)
    health_trend: str | None = Field(default=None, max_length=20)
    risk_level: str | None = Field(default=None, max_length=40)
    success_chance: int | None = Field(default=None, ge=0, le=100)
    success_chance_delta: int | None = None
    ai_recommendations: list[dict] = Field(default_factory=list)


class CustomerInsightResponse(CustomerInsightUpsert):
    id: UUID
    company_id: UUID
    updated_at: datetime


class ScoreFactor(BaseModel):
    key: str
    label: str
    points: int
    max_points: int
    signal: str


class ScoreSnapshotResponse(BaseModel):
    id: UUID
    entity_type: str
    entity_id: UUID
    score: int
    previous_score: int | None
    grade: str
    factors: list[ScoreFactor]
    forecast_probability: int | None
    model_version: str
    calculation_reason: str
    calculated_by_id: UUID | None
    calculated_at: datetime

    model_config = {"from_attributes": True}


class LeadCreate(BaseModel):
    company_id: UUID
    title: str = Field(min_length=2, max_length=255)
    source: str | None = Field(default=None, max_length=80)
    contact_id: UUID | None = None
    owner_id: UUID | None = None


class LeadResponse(BaseModel):
    id: UUID
    company_id: UUID
    title: str
    source: str | None
    status: str
    contact_id: UUID | None
    owner_id: UUID | None = None
    queue_id: UUID | None = None
    score: int | None = None
    score_grade: str | None = None
    score_factors: list[ScoreFactor] = Field(default_factory=list)
    score_model_version: str | None = None
    score_updated_at: datetime | None = None
    qualified_at: datetime | None = None
    converted_at: datetime | None = None
    converted_deal_id: UUID | None = None
    disqualification_reason: str | None = None
    is_archived: bool = False
    deleted_at: datetime | None = None
    version: int = 1
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class PipelineStageInput(BaseModel):
    id: UUID | None = None
    name: str = Field(min_length=1, max_length=120)
    code: str | None = Field(default=None, pattern=r"^[a-z0-9_]+$", max_length=80)
    probability: int = Field(default=0, ge=0, le=100)
    stage_type: Literal["open", "won", "lost"] = "open"
    required_fields: list[str] = Field(default_factory=list, max_length=20)


class PipelineCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    is_default: bool = False
    stages: list[str | PipelineStageInput] = Field(
        default_factory=lambda: ["Новый", "В работе", "КП", "Сделка"],
        min_length=1,
        max_length=30,
    )


class PipelineUpdate(BaseModel):
    version: int = Field(ge=1)
    name: str | None = Field(default=None, min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=2000)
    is_active: bool | None = None
    is_default: bool | None = None
    stages: list[PipelineStageInput] | None = Field(default=None, min_length=1, max_length=30)


class PipelineStageResponse(BaseModel):
    id: UUID
    name: str
    sort_order: int
    code: str
    probability: int
    stage_type: str
    is_active: bool
    required_fields: list[str] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class PipelineResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    is_active: bool
    is_default: bool
    version: int
    stages: list[PipelineStageResponse]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class DealCreate(BaseModel):
    company_id: UUID
    title: str = Field(min_length=2, max_length=255)
    stage_id: UUID
    lead_id: UUID | None = None
    amount: float | None = Field(default=None, ge=0)
    discount_percent: float | None = Field(default=None, ge=0, le=100)
    probability: int | None = Field(default=None, ge=0, le=100)
    expected_close_date: datetime | None = None
    expected_next_event: str | None = Field(default=None, max_length=255)
    next_step: str | None = Field(default=None, max_length=255)
    risk_level: str | None = Field(default=None, max_length=40)
    forecast_category: str | None = Field(default=None, max_length=40)
    owner_id: UUID | None = None
    next_action_id: UUID | None = None


class DealMoveRequest(BaseModel):
    stage_id: UUID
    version: int = Field(ge=1)


class DealResponse(BaseModel):
    id: UUID
    company_id: UUID
    title: str
    amount: float | None
    discount_percent: float | None = None
    status: str
    lead_id: UUID | None
    stage_id: UUID
    probability: int | None
    expected_close_date: datetime | None
    expected_next_event: str | None
    next_step: str | None
    risk_level: str | None
    forecast_category: str | None
    opportunity_score: int | None = None
    score_grade: str | None = None
    score_factors: list[ScoreFactor] = Field(default_factory=list)
    forecast_probability: int | None = None
    probability_source: str = "stage_or_manual"
    score_model_version: str | None = None
    score_updated_at: datetime | None = None
    owner_id: UUID | None = None
    next_action_id: UUID | None = None
    age_days: int | None = None
    is_archived: bool = False
    deleted_at: datetime | None = None
    version: int = 1
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class TaskCreate(BaseModel):
    company_id: UUID
    title: str = Field(min_length=2, max_length=255)
    description: str | None = None
    deal_id: UUID | None = None
    priority: str = Field(default="normal", max_length=40)
    due_at: datetime | None = None
    assigned_to_id: UUID | None = None


class TaskDoneRequest(BaseModel):
    is_done: bool = True
    version: int = Field(ge=1)


class TaskResponse(BaseModel):
    id: UUID
    company_id: UUID
    title: str
    description: str | None
    deal_id: UUID | None
    assigned_to_id: UUID
    status: str
    priority: str
    due_at: datetime | None
    done_at: datetime | None
    is_archived: bool = False
    deleted_at: datetime | None = None
    version: int = 1
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class NoteCreate(BaseModel):
    company_id: UUID
    text: str = Field(min_length=1)
    lead_id: UUID | None = None
    deal_id: UUID | None = None

    @model_validator(mode="after")
    def validate_target(self) -> "NoteCreate":
        if self.lead_id is None and self.deal_id is None:
            raise ValueError("lead_id or deal_id required")
        return self


class NoteResponse(BaseModel):
    id: UUID
    company_id: UUID
    text: str
    lead_id: UUID | None
    deal_id: UUID | None
    author_id: UUID
    is_archived: bool = False
    deleted_at: datetime | None = None
    version: int = 1
    created_at: datetime
    updated_at: datetime | None = None

    model_config = {"from_attributes": True}


class NextActionCreate(BaseModel):
    company_id: UUID
    deal_id: UUID | None = None
    contact_id: UUID | None = None
    assigned_to_id: UUID | None = None
    title: str = Field(min_length=2, max_length=255)
    description: str | None = None
    source: str = Field(default="manual", max_length=40)
    priority: str = Field(default="normal", max_length=40)
    due_at: datetime | None = None


class NextActionDoneRequest(BaseModel):
    is_done: bool = True


class NextActionResponse(BaseModel):
    id: UUID
    company_id: UUID
    deal_id: UUID | None
    contact_id: UUID | None
    assigned_to_id: UUID | None
    title: str
    description: str | None
    source: str
    status: str
    priority: str
    due_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
