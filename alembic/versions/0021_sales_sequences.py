"""add sales sequences and cadence execution

Revision ID: 0021_sales_sequences
Revises: 0020_sales_scoring
Create Date: 2026-07-31
"""

from alembic import op
import sqlalchemy as sa


revision = "0021_sales_sequences"
down_revision = "0020_sales_scoring"
branch_labels = None
depends_on = None


TABLES = ("cadences", "cadence_steps", "cadence_enrollments", "cadence_executions")


def upgrade() -> None:
    op.create_table(
        "cadences",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=False),
        sa.Column("updated_by_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_cadences_tenant"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by_id"],
            ["memberships.tenant_id", "memberships.user_id"],
            name="fk_cadences_tenant_created_by_id",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "updated_by_id"],
            ["memberships.tenant_id", "memberships.user_id"],
            name="fk_cadences_tenant_updated_by_id",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_cadences_tenant_id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_cadences_tenant_name"),
    )
    _indexes("cadences", "tenant_id", "is_active", "created_by_id", "updated_by_id")

    op.create_table(
        "cadence_steps",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("cadence_id", sa.UUID(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("step_type", sa.String(30), nullable=False),
        sa.Column("delay_minutes", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column("task_priority", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "step_type IN ('task', 'call', 'manual_email', 'automatic_email')",
            name="ck_cadence_steps_type",
        ),
        sa.CheckConstraint("delay_minutes >= 0", name="ck_cadence_steps_delay"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_cadence_steps_tenant"),
        sa.ForeignKeyConstraint(["cadence_id"], ["cadences.id"]),
        sa.ForeignKeyConstraint(
            ["tenant_id", "cadence_id"],
            ["cadences.tenant_id", "cadences.id"],
            name="fk_cadence_steps_tenant_cadence_id",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_cadence_steps_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "cadence_id", "position", name="uq_cadence_steps_position"
        ),
    )
    _indexes("cadence_steps", "tenant_id", "cadence_id")

    op.create_table(
        "cadence_enrollments",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("cadence_id", sa.UUID(), nullable=False),
        sa.Column("contact_id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("deal_id", sa.UUID()),
        sa.Column("connector_account_id", sa.UUID()),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("enrolled_by_id", sa.UUID(), nullable=False),
        sa.Column("stopped_by_id", sa.UUID()),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("current_step", sa.Integer(), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True)),
        sa.Column("last_executed_at", sa.DateTime(timezone=True)),
        sa.Column("stop_reason", sa.Text()),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('active', 'paused', 'completed', 'stopped', 'replied', 'failed')",
            name="ck_cadence_enrollments_status",
        ),
        sa.CheckConstraint("current_step >= 0", name="ck_cadence_enrollments_step"),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_cadence_enrollments_tenant"
        ),
        *[
            sa.ForeignKeyConstraint([column], [f"{target}.id"])
            for column, target in (
                ("cadence_id", "cadences"),
                ("contact_id", "contacts"),
                ("company_id", "companies"),
                ("deal_id", "deals"),
                ("connector_account_id", "connector_accounts"),
            )
        ],
        *[
            sa.ForeignKeyConstraint(
                ["tenant_id", column],
                [f"{target}.tenant_id", f"{target}.id"],
                name=f"fk_cadence_enrollments_tenant_{column}",
            )
            for column, target in (
                ("cadence_id", "cadences"),
                ("contact_id", "contacts"),
                ("company_id", "companies"),
                ("deal_id", "deals"),
                ("connector_account_id", "connector_accounts"),
            )
        ],
        *[
            sa.ForeignKeyConstraint(
                ["tenant_id", column],
                ["memberships.tenant_id", "memberships.user_id"],
                name=f"fk_cadence_enrollments_tenant_{column}",
            )
            for column in ("owner_id", "enrolled_by_id", "stopped_by_id")
        ],
        sa.UniqueConstraint("tenant_id", "id", name="uq_cadence_enrollments_tenant_id"),
    )
    _indexes(
        "cadence_enrollments",
        "tenant_id",
        "cadence_id",
        "contact_id",
        "company_id",
        "deal_id",
        "connector_account_id",
        "owner_id",
        "enrolled_by_id",
        "stopped_by_id",
        "status",
        "next_run_at",
    )
    op.create_index(
        "uq_cadence_enrollments_active_contact",
        "cadence_enrollments",
        ["tenant_id", "cadence_id", "contact_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('active', 'paused')"),
        sqlite_where=sa.text("status IN ('active', 'paused')"),
    )

    op.create_table(
        "cadence_executions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("enrollment_id", sa.UUID(), nullable=False),
        sa.Column("step_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("task_id", sa.UUID()),
        sa.Column("communication_event_id", sa.UUID()),
        sa.Column("integration_job_id", sa.UUID()),
        sa.Column("error", sa.Text()),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'succeeded', 'failed', 'skipped')",
            name="ck_cadence_executions_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_cadence_executions_tenant"
        ),
        *[
            sa.ForeignKeyConstraint([column], [f"{target}.id"])
            for column, target in (
                ("enrollment_id", "cadence_enrollments"),
                ("step_id", "cadence_steps"),
                ("task_id", "tasks"),
                ("communication_event_id", "communication_events"),
                ("integration_job_id", "integration_jobs"),
            )
        ],
        *[
            sa.ForeignKeyConstraint(
                ["tenant_id", column],
                [f"{target}.tenant_id", f"{target}.id"],
                name=f"fk_cadence_executions_tenant_{column}",
            )
            for column, target in (
                ("enrollment_id", "cadence_enrollments"),
                ("step_id", "cadence_steps"),
                ("task_id", "tasks"),
                ("communication_event_id", "communication_events"),
                ("integration_job_id", "integration_jobs"),
            )
        ],
        sa.UniqueConstraint("tenant_id", "id", name="uq_cadence_executions_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "enrollment_id", "step_id", name="uq_cadence_executions_step"
        ),
    )
    _indexes(
        "cadence_executions",
        "tenant_id",
        "enrollment_id",
        "step_id",
        "status",
        "task_id",
        "communication_event_id",
        "integration_job_id",
    )

    if op.get_bind().dialect.name == "postgresql":
        for table in TABLES:
            op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
            op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
            op.execute(
                f'CREATE POLICY tenant_isolation ON "{table}" '
                "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) "
                "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
            )


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)


def _indexes(table: str, *columns: str) -> None:
    for column in columns:
        op.create_index(op.f(f"ix_{table}_{column}"), table, [column])
