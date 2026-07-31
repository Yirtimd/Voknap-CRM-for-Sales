"""add explainable sales scoring

Revision ID: 0020_sales_scoring
Revises: 0019_contextual_rag
Create Date: 2026-07-31
"""

from alembic import op
import sqlalchemy as sa


revision = "0020_sales_scoring"
down_revision = "0019_contextual_rag"
branch_labels = None
depends_on = None


OLD_AUTOMATION_TRIGGERS = (
    "trigger_type IN ('lead.created', 'deal.created', 'deal.updated', "
    "'deal.stage_changed', 'communication.created', 'schedule.deal_inactive')"
)
NEW_AUTOMATION_TRIGGERS = (
    "trigger_type IN ('lead.created', 'lead.score_changed', 'deal.created', "
    "'deal.updated', 'deal.stage_changed', 'deal.score_changed', "
    "'communication.created', 'schedule.deal_inactive')"
)


def upgrade() -> None:
    op.add_column("leads", sa.Column("score", sa.Integer()))
    op.add_column("leads", sa.Column("score_grade", sa.String(20)))
    op.add_column(
        "leads",
        sa.Column("score_factors_json", sa.Text(), server_default="[]", nullable=False),
    )
    op.add_column("leads", sa.Column("score_model_version", sa.String(40)))
    op.add_column("leads", sa.Column("score_updated_at", sa.DateTime(timezone=True)))
    op.create_check_constraint("ck_leads_score", "leads", "score >= 0 AND score <= 100")
    op.create_index(op.f("ix_leads_score"), "leads", ["score"])
    op.create_index(op.f("ix_leads_score_grade"), "leads", ["score_grade"])

    op.add_column("deals", sa.Column("opportunity_score", sa.Integer()))
    op.add_column("deals", sa.Column("score_grade", sa.String(20)))
    op.add_column(
        "deals",
        sa.Column("score_factors_json", sa.Text(), server_default="[]", nullable=False),
    )
    op.add_column("deals", sa.Column("scoring_probability", sa.Integer()))
    op.add_column("deals", sa.Column("score_model_version", sa.String(40)))
    op.add_column("deals", sa.Column("score_updated_at", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        "ck_deals_opportunity_score",
        "deals",
        "opportunity_score >= 0 AND opportunity_score <= 100",
    )
    op.create_check_constraint(
        "ck_deals_scoring_probability",
        "deals",
        "scoring_probability >= 0 AND scoring_probability <= 100",
    )
    op.create_index(op.f("ix_deals_opportunity_score"), "deals", ["opportunity_score"])
    op.create_index(op.f("ix_deals_score_grade"), "deals", ["score_grade"])

    op.create_table(
        "score_snapshots",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("entity_type", sa.String(20), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("score", sa.Integer(), nullable=False),
        sa.Column("previous_score", sa.Integer()),
        sa.Column("grade", sa.String(20), nullable=False),
        sa.Column("factors_json", sa.Text(), nullable=False),
        sa.Column("forecast_probability", sa.Integer()),
        sa.Column("model_version", sa.String(40), nullable=False),
        sa.Column("calculation_reason", sa.String(80), nullable=False),
        sa.Column("calculated_by_id", sa.UUID()),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ('lead', 'deal')",
            name="ck_score_snapshots_entity_type",
        ),
        sa.CheckConstraint(
            "score >= 0 AND score <= 100",
            name="ck_score_snapshots_score",
        ),
        sa.CheckConstraint(
            "previous_score IS NULL OR (previous_score >= 0 AND previous_score <= 100)",
            name="ck_score_snapshots_previous_score",
        ),
        sa.CheckConstraint(
            "forecast_probability IS NULL OR "
            "(forecast_probability >= 0 AND forecast_probability <= 100)",
            name="ck_score_snapshots_forecast_probability",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_score_snapshots_tenant",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "calculated_by_id"],
            ["memberships.tenant_id", "memberships.user_id"],
            name="fk_score_snapshots_tenant_calculated_by_id",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_score_snapshots_tenant_id"),
    )
    op.create_index(op.f("ix_score_snapshots_tenant_id"), "score_snapshots", ["tenant_id"])
    op.create_index(op.f("ix_score_snapshots_entity_type"), "score_snapshots", ["entity_type"])
    op.create_index(op.f("ix_score_snapshots_entity_id"), "score_snapshots", ["entity_id"])
    op.create_index(
        op.f("ix_score_snapshots_calculated_by_id"),
        "score_snapshots",
        ["calculated_by_id"],
    )
    op.create_index(
        "ix_score_snapshots_entity_history",
        "score_snapshots",
        ["tenant_id", "entity_type", "entity_id", "calculated_at"],
    )

    op.drop_constraint(
        "ck_automation_workflows_trigger",
        "automation_workflows",
        type_="check",
    )
    op.create_check_constraint(
        "ck_automation_workflows_trigger",
        "automation_workflows",
        NEW_AUTOMATION_TRIGGERS,
    )

    if op.get_bind().dialect.name == "postgresql":
        op.execute('ALTER TABLE "score_snapshots" ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "score_snapshots" FORCE ROW LEVEL SECURITY')
        op.execute(
            'CREATE POLICY tenant_isolation ON "score_snapshots" '
            "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) "
            "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
        )


def downgrade() -> None:
    op.drop_constraint(
        "ck_automation_workflows_trigger",
        "automation_workflows",
        type_="check",
    )
    op.create_check_constraint(
        "ck_automation_workflows_trigger",
        "automation_workflows",
        OLD_AUTOMATION_TRIGGERS,
    )

    op.drop_table("score_snapshots")

    op.drop_index(op.f("ix_deals_score_grade"), table_name="deals")
    op.drop_index(op.f("ix_deals_opportunity_score"), table_name="deals")
    op.drop_constraint("ck_deals_scoring_probability", "deals", type_="check")
    op.drop_constraint("ck_deals_opportunity_score", "deals", type_="check")
    for column in (
        "score_updated_at",
        "score_model_version",
        "scoring_probability",
        "score_factors_json",
        "score_grade",
        "opportunity_score",
    ):
        op.drop_column("deals", column)

    op.drop_index(op.f("ix_leads_score_grade"), table_name="leads")
    op.drop_index(op.f("ix_leads_score"), table_name="leads")
    op.drop_constraint("ck_leads_score", "leads", type_="check")
    for column in (
        "score_updated_at",
        "score_model_version",
        "score_factors_json",
        "score_grade",
        "score",
    ):
        op.drop_column("leads", column)
