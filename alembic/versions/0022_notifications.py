"""add personal in-app notifications

Revision ID: 0022_notifications
Revises: 0021_sales_sequences
Create Date: 2026-07-31
"""

from alembic import op
import sqlalchemy as sa


revision = "0022_notifications"
down_revision = "0021_sales_sequences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notifications",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("recipient_id", sa.UUID(), nullable=False),
        sa.Column("event_key", sa.String(255), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("priority", sa.String(20), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text()),
        sa.Column("link", sa.String(500)),
        sa.Column("source_type", sa.String(50)),
        sa.Column("source_id", sa.UUID()),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("read_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "category IN ('automation', 'approval', 'task', 'communication', 'system')",
            name="ck_notifications_category",
        ),
        sa.CheckConstraint(
            "priority IN ('low', 'normal', 'high', 'critical')",
            name="ck_notifications_priority",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_notifications_tenant"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "recipient_id"],
            ["memberships.tenant_id", "memberships.user_id"],
            name="fk_notifications_tenant_recipient_id",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_notifications_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "recipient_id",
            "event_key",
            name="uq_notifications_recipient_event",
        ),
    )
    for column in (
        "tenant_id",
        "recipient_id",
        "category",
        "priority",
        "source_type",
        "source_id",
        "read_at",
        "created_at",
    ):
        op.create_index(op.f(f"ix_notifications_{column}"), "notifications", [column])

    if op.get_bind().dialect.name == "postgresql":
        op.execute('ALTER TABLE "notifications" ENABLE ROW LEVEL SECURITY')
        op.execute('ALTER TABLE "notifications" FORCE ROW LEVEL SECURITY')
        op.execute(
            'CREATE POLICY tenant_isolation ON "notifications" '
            "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) "
            "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
        )


def downgrade() -> None:
    op.drop_table("notifications")
