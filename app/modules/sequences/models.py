from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.tenancy import tenant_table_args


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Cadence(Base):
    __tablename__ = "cadences"
    __table_args__ = tenant_table_args(
        "cadences",
        membership_columns=("created_by_id", "updated_by_id"),
        extra=(UniqueConstraint("tenant_id", "name", name="uq_cadences_tenant_name"),),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_by_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    updated_by_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    __mapper_args__ = {"version_id_col": version}


class CadenceStep(Base):
    __tablename__ = "cadence_steps"
    __table_args__ = tenant_table_args(
        "cadence_steps",
        relations=(("cadence_id", "cadences"),),
        extra=(
            UniqueConstraint(
                "tenant_id", "cadence_id", "position", name="uq_cadence_steps_position"
            ),
            CheckConstraint(
                "step_type IN ('task', 'call', 'manual_email', 'automatic_email')",
                name="ck_cadence_steps_type",
            ),
            CheckConstraint("delay_minutes >= 0", name="ck_cadence_steps_delay"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    cadence_id: Mapped[UUID] = mapped_column(ForeignKey("cadences.id"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    step_type: Mapped[str] = mapped_column(String(30), nullable=False)
    delay_minutes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str | None] = mapped_column(Text)
    task_priority: Mapped[str] = mapped_column(String(20), default="normal", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CadenceEnrollment(Base):
    __tablename__ = "cadence_enrollments"
    __table_args__ = tenant_table_args(
        "cadence_enrollments",
        relations=(
            ("cadence_id", "cadences"),
            ("contact_id", "contacts"),
            ("company_id", "companies"),
            ("deal_id", "deals"),
            ("connector_account_id", "connector_accounts"),
        ),
        membership_columns=("owner_id", "enrolled_by_id", "stopped_by_id"),
        extra=(
            CheckConstraint(
                "status IN ('active', 'paused', 'completed', 'stopped', 'replied', 'failed')",
                name="ck_cadence_enrollments_status",
            ),
            CheckConstraint("current_step >= 0", name="ck_cadence_enrollments_step"),
            Index(
                "uq_cadence_enrollments_active_contact",
                "tenant_id",
                "cadence_id",
                "contact_id",
                unique=True,
                postgresql_where=text("status IN ('active', 'paused')"),
                sqlite_where=text("status IN ('active', 'paused')"),
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    cadence_id: Mapped[UUID] = mapped_column(ForeignKey("cadences.id"), nullable=False, index=True)
    contact_id: Mapped[UUID] = mapped_column(ForeignKey("contacts.id"), nullable=False, index=True)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    deal_id: Mapped[UUID | None] = mapped_column(ForeignKey("deals.id"), index=True)
    connector_account_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("connector_accounts.id"), index=True
    )
    owner_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    enrolled_by_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    stopped_by_id: Mapped[UUID | None] = mapped_column(index=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False, index=True)
    current_step: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    last_executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stop_reason: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    __mapper_args__ = {"version_id_col": version}


class CadenceExecution(Base):
    __tablename__ = "cadence_executions"
    __table_args__ = tenant_table_args(
        "cadence_executions",
        relations=(
            ("enrollment_id", "cadence_enrollments"),
            ("step_id", "cadence_steps"),
            ("task_id", "tasks"),
            ("communication_event_id", "communication_events"),
            ("integration_job_id", "integration_jobs"),
        ),
        extra=(
            UniqueConstraint(
                "tenant_id", "enrollment_id", "step_id", name="uq_cadence_executions_step"
            ),
            CheckConstraint(
                "status IN ('queued', 'succeeded', 'failed', 'skipped')",
                name="ck_cadence_executions_status",
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    enrollment_id: Mapped[UUID] = mapped_column(
        ForeignKey("cadence_enrollments.id"), nullable=False, index=True
    )
    step_id: Mapped[UUID] = mapped_column(ForeignKey("cadence_steps.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    task_id: Mapped[UUID | None] = mapped_column(ForeignKey("tasks.id"), index=True)
    communication_event_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("communication_events.id"), index=True
    )
    integration_job_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("integration_jobs.id"), index=True
    )
    error: Mapped[str | None] = mapped_column(Text)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
