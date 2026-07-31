import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, DateTime, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.tenancy import tenant_table_args


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Notification(Base):
    __tablename__ = "notifications"
    __table_args__ = tenant_table_args(
        "notifications",
        membership_columns=("recipient_id",),
        extra=(
            UniqueConstraint(
                "tenant_id",
                "recipient_id",
                "event_key",
                name="uq_notifications_recipient_event",
            ),
            CheckConstraint(
                "category IN ('automation', 'approval', 'task', 'communication', 'system')",
                name="ck_notifications_category",
            ),
            CheckConstraint(
                "priority IN ('low', 'normal', 'high', 'critical')",
                name="ck_notifications_priority",
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    recipient_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    event_key: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(20), default="normal", nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(String(500))
    source_type: Mapped[str | None] = mapped_column(String(50), index=True)
    source_id: Mapped[UUID | None] = mapped_column(index=True)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, nullable=False, index=True
    )

    @property
    def metadata_payload(self) -> dict:
        try:
            value = json.loads(self.metadata_json)
        except (TypeError, json.JSONDecodeError):
            return {}
        return value if isinstance(value, dict) else {}
