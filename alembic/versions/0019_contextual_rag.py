"""add contextual hybrid RAG audit contract

Revision ID: 0019_contextual_rag
Revises: 0018_sales_production
Create Date: 2026-07-30
"""

from alembic import op
import sqlalchemy as sa


revision = "0019_contextual_rag"
down_revision = "0018_sales_production"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("knowledge_chunks", sa.Column("page_number", sa.Integer()))

    op.add_column("knowledge_queries", sa.Column("document_id", sa.UUID()))
    op.add_column(
        "knowledge_queries",
        sa.Column("retrieval_mode", sa.String(40), server_default="hybrid", nullable=False),
    )
    op.add_column(
        "knowledge_queries",
        sa.Column("sources_json", sa.Text(), server_default="[]", nullable=False),
    )
    op.add_column("knowledge_queries", sa.Column("top_score", sa.Float()))
    op.add_column("knowledge_queries", sa.Column("feedback_rating", sa.String(10)))
    op.add_column("knowledge_queries", sa.Column("feedback_comment", sa.Text()))
    op.add_column(
        "knowledge_queries",
        sa.Column("feedback_at", sa.DateTime(timezone=True)),
    )
    op.create_foreign_key(
        "fk_knowledge_queries_tenant_document_id",
        "knowledge_queries",
        "knowledge_documents",
        ["tenant_id", "document_id"],
        ["tenant_id", "id"],
    )
    op.create_foreign_key(
        "knowledge_queries_document_id_fkey",
        "knowledge_queries",
        "knowledge_documents",
        ["document_id"],
        ["id"],
    )
    op.create_check_constraint(
        "ck_knowledge_queries_feedback_rating",
        "knowledge_queries",
        "feedback_rating IN ('up', 'down') OR feedback_rating IS NULL",
    )
    op.create_index(
        op.f("ix_knowledge_queries_document_id"),
        "knowledge_queries",
        ["document_id"],
    )

    op.add_column(
        "agent_messages",
        sa.Column("intent", sa.String(40), server_default="knowledge", nullable=False),
    )
    op.add_column(
        "agent_messages",
        sa.Column("context_json", sa.Text(), server_default="{}", nullable=False),
    )
    op.add_column(
        "agent_messages",
        sa.Column("sources_json", sa.Text(), server_default="[]", nullable=False),
    )
    op.add_column("agent_messages", sa.Column("knowledge_query_id", sa.UUID()))
    op.create_foreign_key(
        "fk_agent_messages_tenant_knowledge_query_id",
        "agent_messages",
        "knowledge_queries",
        ["tenant_id", "knowledge_query_id"],
        ["tenant_id", "id"],
    )
    op.create_index(
        op.f("ix_agent_messages_knowledge_query_id"),
        "agent_messages",
        ["knowledge_query_id"],
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                "CREATE INDEX ix_knowledge_chunks_text_search "
                "ON knowledge_chunks USING gin (to_tsvector('simple', text))"
            )
        )


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text("DROP INDEX IF EXISTS ix_knowledge_chunks_text_search"))

    op.drop_index(
        op.f("ix_agent_messages_knowledge_query_id"),
        table_name="agent_messages",
    )
    op.drop_constraint(
        "fk_agent_messages_tenant_knowledge_query_id",
        "agent_messages",
        type_="foreignkey",
    )
    for column in ("knowledge_query_id", "sources_json", "context_json", "intent"):
        op.drop_column("agent_messages", column)

    op.drop_index(
        op.f("ix_knowledge_queries_document_id"),
        table_name="knowledge_queries",
    )
    op.drop_constraint(
        "ck_knowledge_queries_feedback_rating",
        "knowledge_queries",
        type_="check",
    )
    op.drop_constraint(
        "fk_knowledge_queries_tenant_document_id",
        "knowledge_queries",
        type_="foreignkey",
    )
    op.drop_constraint(
        "knowledge_queries_document_id_fkey",
        "knowledge_queries",
        type_="foreignkey",
    )
    for column in (
        "feedback_at",
        "feedback_comment",
        "feedback_rating",
        "top_score",
        "sources_json",
        "retrieval_mode",
        "document_id",
    ):
        op.drop_column("knowledge_queries", column)

    op.drop_column("knowledge_chunks", "page_number")
