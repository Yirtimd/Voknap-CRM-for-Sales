from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


KnowledgeScope = Literal["global", "company", "deal"]


class DocumentCreate(BaseModel):
    title: str = Field(min_length=2, max_length=255)
    text: str = Field(min_length=20)
    source_type: str = Field(default="text", max_length=40)
    company_id: UUID | None = None
    deal_id: UUID | None = None
    file_id: UUID | None = None
    visibility: KnowledgeScope = "global"


class DocumentResponse(BaseModel):
    id: UUID
    company_id: UUID | None = None
    deal_id: UUID | None = None
    file_id: UUID | None = None
    title: str
    source_type: str
    visibility: str
    status: str
    created_at: datetime
    chunks_count: int = 0
    download_url: str | None = None
    extraction_method: str = "manual"
    source_pages: int | None = None


class SearchRequest(BaseModel):
    query: str = Field(min_length=2)
    limit: int = Field(default=6, ge=1, le=20)
    scope: KnowledgeScope = "global"
    company_id: UUID | None = None
    deal_id: UUID | None = None
    document_id: UUID | None = None
    include_global: bool = False

    @model_validator(mode="after")
    def validate_scope(self):
        _validate_scope_context(self.scope, self.company_id, self.deal_id)
        return self


class SearchResultResponse(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_title: str
    document_scope: str = "global"
    company_id: UUID | None = None
    deal_id: UUID | None = None
    page_number: int | None = None
    text: str
    score: float
    chunk_index: int
    retrieval_method: str = "hybrid"


class AskRequest(BaseModel):
    question: str = Field(min_length=2)
    limit: int = Field(default=6, ge=1, le=12)
    scope: KnowledgeScope = "global"
    company_id: UUID | None = None
    deal_id: UUID | None = None
    document_id: UUID | None = None
    include_global: bool = False

    @model_validator(mode="after")
    def validate_scope(self):
        _validate_scope_context(self.scope, self.company_id, self.deal_id)
        return self


class CitationResponse(BaseModel):
    chunk_id: UUID
    document_id: UUID
    document_title: str
    document_scope: str = "global"
    company_id: UUID | None = None
    deal_id: UUID | None = None
    chunk_index: int
    page_number: int | None = None
    text: str
    score: float
    retrieval_method: str = "hybrid"


class AskResponse(BaseModel):
    query_id: UUID
    answer: str
    citations: list[CitationResponse]
    scope: KnowledgeScope
    company_id: UUID | None = None
    deal_id: UUID | None = None
    document_id: UUID | None = None
    include_global: bool = False
    retrieval_mode: str = "hybrid"


class QueryFeedbackRequest(BaseModel):
    rating: Literal["up", "down"]
    comment: str | None = Field(default=None, max_length=2000)


class QueryFeedbackResponse(BaseModel):
    query_id: UUID
    rating: Literal["up", "down"]
    comment: str | None = None


def _validate_scope_context(scope: KnowledgeScope, company_id: UUID | None, deal_id: UUID | None) -> None:
    if scope == "global" and (company_id is not None or deal_id is not None):
        raise ValueError("Global knowledge cannot receive company_id or deal_id")
    if scope == "company" and company_id is None:
        raise ValueError("Company knowledge requires company_id")
    if scope == "company" and deal_id is not None:
        raise ValueError("Company knowledge cannot receive deal_id; use deal scope")
    if scope == "deal" and (company_id is None or deal_id is None):
        raise ValueError("Deal knowledge requires company_id and deal_id")
