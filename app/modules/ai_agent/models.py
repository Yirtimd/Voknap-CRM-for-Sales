from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.tenancy import tenant_table_args


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentMessage(Base):
    __tablename__ = "agent_messages"
    __table_args__ = tenant_table_args(
        "agent_messages",
        relations=(("knowledge_query_id", "knowledge_queries"),),
        membership_columns=("user_id",),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    role: Mapped[str] = mapped_column(String(40), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    intent: Mapped[str] = mapped_column(String(40), default="knowledge", nullable=False)
    context_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    sources_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    knowledge_query_id: Mapped[UUID | None] = mapped_column(index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AgentAction(Base):
    __tablename__ = "agent_actions"
    __table_args__ = tenant_table_args("agent_actions", membership_columns=("user_id",))

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    action_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="pending")
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
