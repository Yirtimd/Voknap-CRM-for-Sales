from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.tenancy import tenant_table_args


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MessageTemplate(Base):
    __tablename__ = "message_templates"
    __table_args__ = tenant_table_args(
        "message_templates",
        membership_columns=("created_by_id",),
        extra=(UniqueConstraint("tenant_id", "name", name="uq_message_templates_tenant_name"),),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    channel: Mapped[str] = mapped_column(String(40), default="email", nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by_id: Mapped[UUID] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )


class AutomationWorkflow(Base):
    __tablename__ = "automation_workflows"
    __table_args__ = tenant_table_args(
        "automation_workflows",
        membership_columns=("created_by_id", "updated_by_id"),
        extra=(
            UniqueConstraint("tenant_id", "name", name="uq_automation_workflows_tenant_name"),
            CheckConstraint(
                "trigger_type IN ('lead.created', 'lead.score_changed', 'deal.created', "
                "'deal.updated', 'deal.stage_changed', 'deal.score_changed', "
                "'communication.created', 'schedule.deal_inactive')",
                name="ck_automation_workflows_trigger",
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    conditions_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    condition_logic: Mapped[str] = mapped_column(String(10), default="all", nullable=False)
    actions_json: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_by_id: Mapped[UUID] = mapped_column(nullable=False)
    updated_by_id: Mapped[UUID] = mapped_column(nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    __mapper_args__ = {"version_id_col": version}


class AutomationRun(Base):
    __tablename__ = "automation_runs"
    __table_args__ = tenant_table_args(
        "automation_runs",
        relations=(("workflow_id", "automation_workflows"),),
        membership_columns=("actor_id",),
        extra=(
            UniqueConstraint(
                "tenant_id", "workflow_id", "event_key", name="uq_automation_runs_event"
            ),
            CheckConstraint(
                "status IN ('running', 'waiting_approval', 'succeeded', 'failed', 'skipped')",
                name="ck_automation_runs_status",
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    workflow_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    event_key: Mapped[str] = mapped_column(String(255), nullable=False)
    trigger_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    actor_id: Mapped[UUID | None] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(20), default="running", nullable=False, index=True)
    context_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    result_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"
    __table_args__ = tenant_table_args(
        "approval_requests",
        relations=(
            ("workflow_id", "automation_workflows"),
            ("run_id", "automation_runs"),
        ),
        membership_columns=("requested_by_id", "assigned_to_id", "decided_by_id"),
        extra=(
            CheckConstraint(
                "status IN ('pending', 'approved', 'rejected', 'cancelled', 'expired')",
                name="ck_approval_requests_status",
            ),
            CheckConstraint(
                "priority IN ('low', 'normal', 'high', 'critical')",
                name="ck_approval_requests_priority",
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    workflow_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    run_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    requested_by_id: Mapped[UUID | None] = mapped_column(index=True)
    assigned_to_id: Mapped[UUID | None] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(20), default="normal", nullable=False, index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    context_snapshot_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    continuation_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    decision_comment: Mapped[str | None] = mapped_column(Text)
    decided_by_id: Mapped[UUID | None] = mapped_column(index=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    __mapper_args__ = {"version_id_col": version}


class ApprovalHistory(Base):
    __tablename__ = "approval_history"
    __table_args__ = tenant_table_args(
        "approval_history",
        relations=(("approval_id", "approval_requests"),),
        membership_columns=("actor_id",),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    approval_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(20))
    to_status: Mapped[str | None] = mapped_column(String(20))
    actor_id: Mapped[UUID | None] = mapped_column(index=True)
    comment: Mapped[str | None] = mapped_column(Text)
    metadata_json: Mapped[str] = mapped_column(Text, default="{}", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AutomationOutbox(Base):
    __tablename__ = "automation_outbox"
    __table_args__ = tenant_table_args(
        "automation_outbox",
        relations=(
            ("run_id", "automation_runs"),
            ("template_id", "message_templates"),
        ),
        extra=(
            CheckConstraint(
                "status IN ('pending', 'sending', 'sent', 'failed', 'cancelled')",
                name="ck_automation_outbox_status",
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    run_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    template_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False)
    entity_id: Mapped[UUID] = mapped_column(nullable=False)
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    recipient: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False, index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
