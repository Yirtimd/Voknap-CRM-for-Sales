import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.core.tenancy import tenant_table_args


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = tenant_table_args(
        "contacts",
        relations=(("company_id", "companies"),),
        membership_columns=("owner_id", "deleted_by_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(80))
    email: Mapped[str | None] = mapped_column(String(255))
    company_name: Mapped[str | None] = mapped_column(String(255))
    role: Mapped[str | None] = mapped_column(String(120))
    owner_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    can_call: Mapped[bool] = mapped_column(Boolean, default=True)
    can_email: Mapped[bool] = mapped_column(Boolean, default=True)
    can_open_more: Mapped[bool] = mapped_column(Boolean, default=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    deleted_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    __mapper_args__ = {"version_id_col": version}

    leads: Mapped[list["Lead"]] = relationship(
        back_populates="contact", foreign_keys="Lead.contact_id"
    )


class Company(Base):
    __tablename__ = "companies"
    __table_args__ = tenant_table_args(
        "companies",
        deferred_relations=(("next_action_id", "next_actions"),),
        relations=(("territory_id", "territories"),),
        membership_columns=("owner_id",),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    website: Mapped[str | None] = mapped_column(String(255))
    industry: Mapped[str | None] = mapped_column(String(120))
    country_code: Mapped[str | None] = mapped_column(String(2))
    region: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="active")
    company_type: Mapped[str | None] = mapped_column(String(40))
    health_score: Mapped[int | None] = mapped_column(Integer)
    client_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    owner_id: Mapped[UUID | None] = mapped_column()
    territory_id: Mapped[UUID | None] = mapped_column(index=True)
    next_action_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "next_actions.id",
            name="fk_companies_next_action_id_next_actions",
            use_alter=True,
        )
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Pipeline(Base):
    __tablename__ = "pipelines"
    __table_args__ = tenant_table_args(
        "pipelines",
        extra=(
            UniqueConstraint("tenant_id", "name", name="uq_pipelines_tenant_name"),
            Index(
                "uq_pipelines_one_default",
                "tenant_id",
                unique=True,
                postgresql_where=text("is_default"),
                sqlite_where=text("is_default"),
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    __mapper_args__ = {"version_id_col": version}

    stages: Mapped[list["PipelineStage"]] = relationship(
        back_populates="pipeline",
        cascade="all, delete-orphan",
        foreign_keys="PipelineStage.pipeline_id",
        order_by="PipelineStage.sort_order",
    )


class PipelineStage(Base):
    __tablename__ = "pipeline_stages"
    __table_args__ = tenant_table_args(
        "pipeline_stages",
        relations=(("pipeline_id", "pipelines"),),
        extra=(
            UniqueConstraint("tenant_id", "pipeline_id", "code", name="uq_pipeline_stages_code"),
            CheckConstraint("stage_type IN ('open', 'won', 'lost')", name="ck_pipeline_stages_type"),
            CheckConstraint("probability >= 0 AND probability <= 100", name="ck_pipeline_stages_probability"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    pipeline_id: Mapped[UUID] = mapped_column(ForeignKey("pipelines.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    code: Mapped[str] = mapped_column(
        String(80), default=lambda: f"stage_{uuid4().hex}", nullable=False
    )
    sort_order: Mapped[int] = mapped_column(default=0)
    probability: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stage_type: Mapped[str] = mapped_column(String(20), default="open", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    required_fields_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)

    pipeline: Mapped[Pipeline] = relationship(
        back_populates="stages", foreign_keys=[pipeline_id]
    )
    deals: Mapped[list["Deal"]] = relationship(
        back_populates="stage", foreign_keys="Deal.stage_id"
    )


class DuplicateCandidate(Base):
    __tablename__ = "duplicate_candidates"
    __table_args__ = tenant_table_args(
        "duplicate_candidates",
        membership_columns=("detected_by_id", "resolved_by_id"),
        extra=(
            UniqueConstraint(
                "tenant_id",
                "entity_type",
                "record_a_id",
                "record_b_id",
                name="uq_duplicate_candidates_pair",
            ),
            CheckConstraint(
                "entity_type IN ('contacts', 'leads', 'deals')",
                name="ck_duplicate_candidates_entity_type",
            ),
            CheckConstraint(
                "status IN ('open', 'dismissed', 'merged')",
                name="ck_duplicate_candidates_status",
            ),
            CheckConstraint(
                "score >= 0 AND score <= 100",
                name="ck_duplicate_candidates_score",
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    record_a_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    record_b_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    matched_fields_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="open", nullable=False, index=True)
    detected_by_id: Mapped[UUID | None] = mapped_column(index=True)
    resolved_by_id: Mapped[UUID | None] = mapped_column(index=True)
    resolution_comment: Mapped[str | None] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __mapper_args__ = {"version_id_col": version}


class Lead(Base):
    __tablename__ = "leads"
    __table_args__ = tenant_table_args(
        "leads",
        relations=(
            ("company_id", "companies"),
            ("contact_id", "contacts"),
            ("queue_id", "lead_queues"),
        ),
        deferred_relations=(("converted_deal_id", "deals"),),
        membership_columns=("owner_id", "qualified_by_id", "converted_by_id", "deleted_by_id"),
        extra=(
            CheckConstraint("score >= 0 AND score <= 100", name="ck_leads_score"),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    contact_id: Mapped[UUID | None] = mapped_column(ForeignKey("contacts.id"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(80), default="new")
    owner_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    queue_id: Mapped[UUID | None] = mapped_column(index=True)
    score: Mapped[int | None] = mapped_column(Integer, index=True)
    score_grade: Mapped[str | None] = mapped_column(String(20), index=True)
    score_factors_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    score_model_version: Mapped[str | None] = mapped_column(String(40))
    score_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    qualified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    qualified_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    converted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    converted_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    converted_deal_id: Mapped[UUID | None] = mapped_column(ForeignKey("deals.id", use_alter=True))
    disqualification_reason: Mapped[str | None] = mapped_column(Text)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    deleted_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    __mapper_args__ = {"version_id_col": version}

    contact: Mapped[Contact | None] = relationship(
        back_populates="leads", foreign_keys=[contact_id]
    )
    deals: Mapped[list["Deal"]] = relationship(
        back_populates="lead", foreign_keys="Deal.lead_id"
    )
    notes: Mapped[list["Note"]] = relationship(
        back_populates="lead", foreign_keys="Note.lead_id"
    )

    @property
    def score_factors(self) -> list[dict]:
        return json.loads(self.score_factors_json or "[]")


class Deal(Base):
    __tablename__ = "deals"
    __table_args__ = tenant_table_args(
        "deals",
        relations=(
            ("company_id", "companies"),
            ("lead_id", "leads"),
            ("stage_id", "pipeline_stages"),
        ),
        deferred_relations=(("next_action_id", "next_actions"),),
        membership_columns=("owner_id", "deleted_by_id"),
        extra=(
            CheckConstraint(
                "opportunity_score >= 0 AND opportunity_score <= 100",
                name="ck_deals_opportunity_score",
            ),
            CheckConstraint(
                "scoring_probability >= 0 AND scoring_probability <= 100",
                name="ck_deals_scoring_probability",
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    lead_id: Mapped[UUID | None] = mapped_column(ForeignKey("leads.id"))
    stage_id: Mapped[UUID] = mapped_column(ForeignKey("pipeline_stages.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[float | None] = mapped_column(Numeric(12, 2))
    discount_percent: Mapped[float | None] = mapped_column(Numeric(5, 2))
    status: Mapped[str] = mapped_column(String(40), default="open")
    probability: Mapped[int | None] = mapped_column(Integer)
    expected_close_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expected_next_event: Mapped[str | None] = mapped_column(String(255))
    next_step: Mapped[str | None] = mapped_column(String(255))
    risk_level: Mapped[str | None] = mapped_column(String(40))
    forecast_category: Mapped[str | None] = mapped_column(String(40))
    opportunity_score: Mapped[int | None] = mapped_column(Integer, index=True)
    score_grade: Mapped[str | None] = mapped_column(String(20), index=True)
    score_factors_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    scoring_probability: Mapped[int | None] = mapped_column(Integer)
    score_model_version: Mapped[str | None] = mapped_column(String(40))
    score_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    owner_id: Mapped[UUID | None] = mapped_column()
    next_action_id: Mapped[UUID | None] = mapped_column(
        ForeignKey(
            "next_actions.id",
            name="fk_deals_next_action_id_next_actions",
            use_alter=True,
        )
    )
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    deleted_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    __mapper_args__ = {"version_id_col": version}

    lead: Mapped[Lead | None] = relationship(
        back_populates="deals", foreign_keys=[lead_id]
    )
    stage: Mapped[PipelineStage] = relationship(
        back_populates="deals", foreign_keys=[stage_id]
    )
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="deal", foreign_keys="Task.deal_id"
    )
    notes: Mapped[list["Note"]] = relationship(
        back_populates="deal", foreign_keys="Note.deal_id"
    )

    @property
    def score_factors(self) -> list[dict]:
        return json.loads(self.score_factors_json or "[]")

    @property
    def forecast_probability(self) -> int | None:
        return self.scoring_probability

    @property
    def probability_source(self) -> str:
        return "scoring" if self.scoring_probability is not None else "stage_or_manual"


class ScoreSnapshot(Base):
    __tablename__ = "score_snapshots"
    __table_args__ = tenant_table_args(
        "score_snapshots",
        membership_columns=("calculated_by_id",),
        extra=(
            CheckConstraint(
                "entity_type IN ('lead', 'deal')",
                name="ck_score_snapshots_entity_type",
            ),
            CheckConstraint("score >= 0 AND score <= 100", name="ck_score_snapshots_score"),
            CheckConstraint(
                "previous_score IS NULL OR (previous_score >= 0 AND previous_score <= 100)",
                name="ck_score_snapshots_previous_score",
            ),
            CheckConstraint(
                "forecast_probability IS NULL OR "
                "(forecast_probability >= 0 AND forecast_probability <= 100)",
                name="ck_score_snapshots_forecast_probability",
            ),
            Index(
                "ix_score_snapshots_entity_history",
                "tenant_id",
                "entity_type",
                "entity_id",
                "calculated_at",
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    entity_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_score: Mapped[int | None] = mapped_column(Integer)
    grade: Mapped[str] = mapped_column(String(20), nullable=False)
    factors_json: Mapped[str] = mapped_column(Text, default="[]", nullable=False)
    forecast_probability: Mapped[int | None] = mapped_column(Integer)
    model_version: Mapped[str] = mapped_column(String(40), nullable=False)
    calculation_reason: Mapped[str] = mapped_column(String(80), nullable=False)
    calculated_by_id: Mapped[UUID | None] = mapped_column(index=True)
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    @property
    def factors(self) -> list[dict]:
        return json.loads(self.factors_json or "[]")


class Task(Base):
    __tablename__ = "tasks"
    __table_args__ = tenant_table_args(
        "tasks",
        relations=(("company_id", "companies"), ("deal_id", "deals")),
        membership_columns=("assigned_to_id", "deleted_by_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    assigned_to_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    deal_id: Mapped[UUID | None] = mapped_column(ForeignKey("deals.id"))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="open")
    priority: Mapped[str] = mapped_column(String(40), default="normal")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    done_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    deleted_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    __mapper_args__ = {"version_id_col": version}

    deal: Mapped[Deal | None] = relationship(
        back_populates="tasks", foreign_keys=[deal_id]
    )


class Note(Base):
    __tablename__ = "notes"
    __table_args__ = tenant_table_args(
        "notes",
        relations=(
            ("company_id", "companies"),
            ("lead_id", "leads"),
            ("deal_id", "deals"),
        ),
        membership_columns=("author_id", "deleted_by_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    author_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    lead_id: Mapped[UUID | None] = mapped_column(ForeignKey("leads.id"))
    deal_id: Mapped[UUID | None] = mapped_column(ForeignKey("deals.id"))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    deleted_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )

    __mapper_args__ = {"version_id_col": version}

    lead: Mapped[Lead | None] = relationship(
        back_populates="notes", foreign_keys=[lead_id]
    )
    deal: Mapped[Deal | None] = relationship(
        back_populates="notes", foreign_keys=[deal_id]
    )


class NextAction(Base):
    __tablename__ = "next_actions"
    __table_args__ = tenant_table_args(
        "next_actions",
        relations=(
            ("company_id", "companies"),
            ("deal_id", "deals"),
            ("contact_id", "contacts"),
        ),
        membership_columns=("assigned_to_id",),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    deal_id: Mapped[UUID | None] = mapped_column(ForeignKey("deals.id"), index=True)
    contact_id: Mapped[UUID | None] = mapped_column(ForeignKey("contacts.id"), index=True)
    assigned_to_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(40), default="manual")
    status: Mapped[str] = mapped_column(String(40), default="open", index=True)
    priority: Mapped[str] = mapped_column(String(40), default="normal")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CompanyFile(Base):
    __tablename__ = "files"
    __table_args__ = tenant_table_args(
        "files",
        relations=(
            ("company_id", "companies"),
            ("deal_id", "deals"),
            ("contact_id", "contacts"),
            ("activity_id", "activities"),
        ),
        membership_columns=("uploaded_by_id",),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    company_id: Mapped[UUID | None] = mapped_column(ForeignKey("companies.id"), index=True)
    deal_id: Mapped[UUID | None] = mapped_column(ForeignKey("deals.id"), index=True)
    contact_id: Mapped[UUID | None] = mapped_column(ForeignKey("contacts.id"), index=True)
    activity_id: Mapped[UUID | None] = mapped_column(ForeignKey("activities.id"), index=True)
    uploaded_by_id: Mapped[UUID | None] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_type: Mapped[str | None] = mapped_column(String(40))
    mime_type: Mapped[str | None] = mapped_column(String(120))
    file_size: Mapped[int | None] = mapped_column(Integer)
    storage_backend: Mapped[str] = mapped_column(String(40), default="local", nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    download_url: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class CustomerInsight(Base):
    __tablename__ = "customer_insights"
    __table_args__ = tenant_table_args(
        "customer_insights",
        relations=(("company_id", "companies"),),
        extra=(
            UniqueConstraint(
                "tenant_id", "company_id", name="uq_customer_insight_tenant_company"
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    company_id: Mapped[UUID] = mapped_column(ForeignKey("companies.id"), nullable=False, index=True)
    health_score: Mapped[int | None] = mapped_column(Integer)
    health_label: Mapped[str | None] = mapped_column(String(80))
    health_trend: Mapped[str | None] = mapped_column(String(20))
    risk_level: Mapped[str | None] = mapped_column(String(40))
    success_chance: Mapped[int | None] = mapped_column(Integer)
    success_chance_delta: Mapped[int | None] = mapped_column(Integer)
    ai_recommendations_json: Mapped[str] = mapped_column(Text, default="[]")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class FieldChange(Base):
    __tablename__ = "crm_field_changes"
    __table_args__ = tenant_table_args(
        "crm_field_changes",
        membership_columns=("changed_by_id",),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    entity_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    field_name: Mapped[str] = mapped_column(String(80), nullable=False)
    old_value_json: Mapped[str | None] = mapped_column(Text)
    new_value_json: Mapped[str | None] = mapped_column(Text)
    changed_by_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), nullable=False)
    entity_version: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
