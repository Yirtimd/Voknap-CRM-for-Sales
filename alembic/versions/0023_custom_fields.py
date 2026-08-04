"""add tenant-safe typed custom fields

Revision ID: 0023_custom_fields
Revises: 0022_notifications
Create Date: 2026-08-04
"""

from alembic import op
import sqlalchemy as sa


revision = "0023_custom_fields"
down_revision = "0022_notifications"
branch_labels = None
depends_on = None


def _enable_rls(table: str) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.execute(f'ALTER TABLE "{table}" ENABLE ROW LEVEL SECURITY')
    op.execute(f'ALTER TABLE "{table}" FORCE ROW LEVEL SECURITY')
    op.execute(
        f'CREATE POLICY tenant_isolation ON "{table}" '
        "USING (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid) "
        "WITH CHECK (tenant_id = NULLIF(current_setting('app.tenant_id', true), '')::uuid)"
    )


def upgrade() -> None:
    op.create_table(
        "custom_field_definitions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("label", sa.String(160), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("field_type", sa.String(30), nullable=False),
        sa.Column("options_json", sa.Text(), nullable=False),
        sa.Column("is_required", sa.Boolean(), nullable=False),
        sa.Column("is_filterable", sa.Boolean(), nullable=False),
        sa.Column("is_reportable", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=False),
        sa.Column("updated_by_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ('companies', 'contacts', 'leads', 'deals', 'tasks')",
            name="ck_custom_field_definitions_entity",
        ),
        sa.CheckConstraint(
            "field_type IN ('text', 'number', 'date', 'datetime', 'boolean', 'select', 'multi_select')",
            name="ck_custom_field_definitions_type",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_custom_field_definitions_tenant"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "created_by_id"],
            ["memberships.tenant_id", "memberships.user_id"],
            name="fk_custom_field_definitions_tenant_created_by_id",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "updated_by_id"],
            ["memberships.tenant_id", "memberships.user_id"],
            name="fk_custom_field_definitions_tenant_updated_by_id",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_custom_field_definitions_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "entity_type", "code", name="uq_custom_field_definitions_code"
        ),
    )
    for column in ("tenant_id", "entity_type", "is_active"):
        op.create_index(
            op.f(f"ix_custom_field_definitions_{column}"),
            "custom_field_definitions",
            [column],
        )

    op.create_table(
        "custom_field_values",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("field_id", sa.UUID(), nullable=False),
        sa.Column("entity_type", sa.String(30), nullable=False),
        sa.Column("entity_id", sa.UUID(), nullable=False),
        sa.Column("text_value", sa.Text()),
        sa.Column("number_value", sa.Numeric(20, 4)),
        sa.Column("date_value", sa.Date()),
        sa.Column("datetime_value", sa.DateTime(timezone=True)),
        sa.Column("boolean_value", sa.Boolean()),
        sa.Column("json_value", sa.Text()),
        sa.Column("updated_by_id", sa.UUID(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "entity_type IN ('companies', 'contacts', 'leads', 'deals', 'tasks')",
            name="ck_custom_field_values_entity_type",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name="fk_custom_field_values_tenant"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "field_id"],
            ["custom_field_definitions.tenant_id", "custom_field_definitions.id"],
            name="fk_custom_field_values_tenant_field_id",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "updated_by_id"],
            ["memberships.tenant_id", "memberships.user_id"],
            name="fk_custom_field_values_tenant_updated_by_id",
        ),
        sa.UniqueConstraint("tenant_id", "id", name="uq_custom_field_values_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id", "field_id", "entity_id", name="uq_custom_field_values_entity"
        ),
    )
    for column in ("tenant_id", "field_id", "entity_type", "entity_id"):
        op.create_index(
            op.f(f"ix_custom_field_values_{column}"), "custom_field_values", [column]
        )
    for suffix, column in (
        ("text", "text_value"),
        ("number", "number_value"),
        ("date", "date_value"),
        ("boolean", "boolean_value"),
    ):
        op.create_index(
            f"ix_custom_field_values_{suffix}_lookup",
            "custom_field_values",
            ["tenant_id", "field_id", column],
        )

    _enable_rls("custom_field_definitions")
    _enable_rls("custom_field_values")


def downgrade() -> None:
    op.drop_table("custom_field_values")
    op.drop_table("custom_field_definitions")
