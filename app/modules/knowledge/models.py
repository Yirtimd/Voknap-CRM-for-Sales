from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import VECTOR

from app.core.database import Base
from app.core.tenancy import tenant_table_args


PGVECTOR_DIMENSIONS = 1536


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class KnowledgeDocument(Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = tenant_table_args(
        "knowledge_documents",
        relations=(("company_id", "companies"), ("deal_id", "deals"), ("file_id", "files")),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    company_id: Mapped[UUID | None] = mapped_column(ForeignKey("companies.id"), index=True)
    deal_id: Mapped[UUID | None] = mapped_column(ForeignKey("deals.id"), index=True)
    file_id: Mapped[UUID | None] = mapped_column(ForeignKey("files.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(40), default="text")
    visibility: Mapped[str] = mapped_column(String(40), default="global")
    status: Mapped[str] = mapped_column(String(40), default="ready")
    extraction_method: Mapped[str] = mapped_column(String(40), default="manual", nullable=False)
    source_pages: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    chunks: Mapped[list["KnowledgeChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        foreign_keys="KnowledgeChunk.document_id",
        order_by="KnowledgeChunk.chunk_index",
    )


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"
    __table_args__ = tenant_table_args(
        "knowledge_chunks",
        relations=(
            ("document_id", "knowledge_documents"),
            ("company_id", "companies"),
            ("deal_id", "deals"),
        ),
        extra=(
            Index(
                "ix_knowledge_chunks_text_search",
                text("to_tsvector('simple', text)"),
                postgresql_using="gin",
            ).ddl_if(dialect="postgresql"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    document_id: Mapped[UUID] = mapped_column(
        ForeignKey("knowledge_documents.id"),
        nullable=False,
        index=True,
    )
    scope: Mapped[str] = mapped_column(String(40), default="global", index=True)
    company_id: Mapped[UUID | None] = mapped_column(ForeignKey("companies.id"), index=True)
    deal_id: Mapped[UUID | None] = mapped_column(ForeignKey("deals.id"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding_vector: Mapped[list[float]] = mapped_column(
        VECTOR(PGVECTOR_DIMENSIONS), nullable=False
    )
    embedding_provider: Mapped[str] = mapped_column(String(50), default="local", nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(120), default="local-hash-v1", nullable=False)
    embedding_version: Mapped[str] = mapped_column(String(40), default="1", nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(
        Integer, default=PGVECTOR_DIMENSIONS, nullable=False
    )
    token_estimate: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    document: Mapped[KnowledgeDocument] = relationship(
        back_populates="chunks", foreign_keys=[document_id]
    )


class KnowledgeQuery(Base):
    __tablename__ = "knowledge_queries"
    __table_args__ = tenant_table_args(
        "knowledge_queries",
        relations=(
            ("company_id", "companies"),
            ("deal_id", "deals"),
            ("document_id", "knowledge_documents"),
        ),
        membership_columns=("user_id",),
        extra=(
            CheckConstraint(
                "feedback_rating IN ('up', 'down') OR feedback_rating IS NULL",
                name="ck_knowledge_queries_feedback_rating",
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    scope: Mapped[str] = mapped_column(String(40), default="global", index=True)
    company_id: Mapped[UUID | None] = mapped_column(ForeignKey("companies.id"), index=True)
    deal_id: Mapped[UUID | None] = mapped_column(ForeignKey("deals.id"), index=True)
    document_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("knowledge_documents.id"), index=True
    )
    include_global: Mapped[bool] = mapped_column(default=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    retrieval_mode: Mapped[str] = mapped_column(String(40), default="hybrid", nullable=False)
    sources_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    top_score: Mapped[float | None] = mapped_column(Float)
    feedback_rating: Mapped[str | None] = mapped_column(String(10))
    feedback_comment: Mapped[str | None] = mapped_column(Text)
    feedback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
