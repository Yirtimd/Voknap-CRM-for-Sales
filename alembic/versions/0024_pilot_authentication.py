"""add pilot-ready authentication sessions, reset and MFA

Revision ID: 0024_pilot_authentication
Revises: 0023_custom_fields
Create Date: 2026-08-06
"""

from alembic import op
import sqlalchemy as sa


revision = "0024_pilot_authentication"
down_revision = "0023_custom_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True)))
    op.add_column("users", sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("users", sa.Column("mfa_secret_encrypted", sa.Text()))
    op.add_column("users", sa.Column("mfa_pending_secret_encrypted", sa.Text()))
    op.add_column("users", sa.Column("mfa_recovery_codes_json", sa.Text(), nullable=False, server_default="[]"))
    op.add_column("users", sa.Column("mfa_enabled_at", sa.DateTime(timezone=True)))

    op.create_table(
        "user_sessions",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("family_id", sa.UUID(), nullable=False),
        sa.Column("refresh_token_hash", sa.String(64), nullable=False),
        sa.Column("replaced_by_id", sa.UUID()),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("user_agent", sa.String(500)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoke_reason", sa.String(80)),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["replaced_by_id"], ["user_sessions.id"]),
        sa.UniqueConstraint("refresh_token_hash", name="uq_user_sessions_refresh_token_hash"),
    )
    for column in ("user_id", "family_id", "refresh_token_hash", "expires_at", "revoked_at"):
        op.create_index(op.f(f"ix_user_sessions_{column}"), "user_sessions", [column])

    op.create_table(
        "auth_tokens",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("purpose", sa.String(30), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("purpose IN ('password_reset', 'mfa_login')", name="ck_auth_tokens_purpose"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("token_hash", name="uq_auth_tokens_token_hash"),
    )
    for column in ("user_id", "purpose", "token_hash", "expires_at"):
        op.create_index(op.f(f"ix_auth_tokens_{column}"), "auth_tokens", [column])

    op.create_table(
        "auth_rate_limits",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("blocked_until", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("key_hash", name="uq_auth_rate_limits_key_hash"),
    )
    for column in ("key_hash", "action", "blocked_until"):
        op.create_index(op.f(f"ix_auth_rate_limits_{column}"), "auth_rate_limits", [column])

    op.create_table(
        "auth_events",
        sa.Column("id", sa.UUID(), primary_key=True),
        sa.Column("user_id", sa.UUID()),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("user_agent", sa.String(500)),
        sa.Column("metadata_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
    )
    for column in ("user_id", "event_type", "created_at"):
        op.create_index(op.f(f"ix_auth_events_{column}"), "auth_events", [column])


def downgrade() -> None:
    op.drop_table("auth_events")
    op.drop_table("auth_rate_limits")
    op.drop_table("auth_tokens")
    op.drop_table("user_sessions")
    op.drop_column("users", "mfa_enabled_at")
    op.drop_column("users", "mfa_recovery_codes_json")
    op.drop_column("users", "mfa_pending_secret_encrypted")
    op.drop_column("users", "mfa_secret_encrypted")
    op.drop_column("users", "mfa_enabled")
    op.drop_column("users", "password_changed_at")
