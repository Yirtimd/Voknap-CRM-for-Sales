from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class AgentChatRequest(BaseModel):
    message: str = Field(min_length=2)
    context_type: Literal["workspace", "knowledge", "company", "deal", "document"] = "workspace"
    company_id: UUID | None = None
    deal_id: UUID | None = None
    document_id: UUID | None = None
    include_global: bool = False
    page_path: str | None = Field(default=None, max_length=500)


class AgentActionResponse(BaseModel):
    id: UUID
    action_type: str
    status: str
    payload: dict
    result: dict | None = None
    created_at: datetime
    confirmed_at: datetime | None = None


class AgentChatResponse(BaseModel):
    message_id: UUID
    query_id: UUID | None = None
    answer: str
    actions: list[AgentActionResponse] = Field(default_factory=list)
    sources: list[dict] = Field(default_factory=list)
    intent: str
    context: dict = Field(default_factory=dict)


class AgentHistoryMessage(BaseModel):
    id: UUID
    role: str
    content: str
    intent: str = "knowledge"
    context: dict = Field(default_factory=dict)
    sources: list[dict] = Field(default_factory=list)
    query_id: UUID | None = None
    created_at: datetime


class CompanyCopilotResponse(BaseModel):
    company_id: UUID
    summary: str
    next_best_action: str
    deal_risk: dict
    follow_up_draft: str
    meeting_prep: str
    insight: dict
    actions: list[AgentActionResponse] = Field(default_factory=list)


class HomeFocusDeal(BaseModel):
    deal_id: UUID
    company_id: UUID
    company_name: str
    deal_title: str
    amount: float
    stage_name: str
    confidence: int
    risk_score: int
    risk_level: str
    next_action: str


class HomeCopilotResponse(BaseModel):
    generated_at: datetime
    source: str = "backend_copilot"
    title: str
    rationale: str
    company_id: UUID | None = None
    company_name: str | None = None
    deal_id: UUID | None = None
    deal_title: str | None = None
    amount: float = 0
    confidence: int = 0
    risk_score: int = 0
    risk_level: str = "low"
    action_label: str
    primary_url: str
    details_url: str
    signals: list[str] = Field(default_factory=list)
    focus_deals: list[HomeFocusDeal] = Field(default_factory=list)
