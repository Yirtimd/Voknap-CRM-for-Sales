import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.core.config import settings


pytestmark = pytest.mark.postgres


@pytest.fixture
def postgres_connection():
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.fail("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            tenant_a = uuid4()
            tenant_b = uuid4()
            company_a = uuid4()
            company_b = uuid4()
            connection.execute(
                text(
                    "INSERT INTO tenants (id, name, slug, is_active, created_at) VALUES "
                    "(:tenant_a, 'Tenant A', :slug_a, true, now()), "
                    "(:tenant_b, 'Tenant B', :slug_b, true, now())"
                ),
                {
                    "tenant_a": tenant_a,
                    "tenant_b": tenant_b,
                    "slug_a": f"rls-a-{tenant_a}",
                    "slug_b": f"rls-b-{tenant_b}",
                },
            )
            connection.execute(
                text(
                    "INSERT INTO companies (id, tenant_id, name, status, created_at) VALUES "
                    "(:company_a, :tenant_a, 'Company A', 'active', now()), "
                    "(:company_b, :tenant_b, 'Company B', 'active', now())"
                ),
                {
                    "company_a": company_a,
                    "company_b": company_b,
                    "tenant_a": tenant_a,
                    "tenant_b": tenant_b,
                },
            )
            try:
                yield connection, tenant_a, tenant_b, company_a, company_b
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def test_rls_default_deny_and_tenant_scope(postgres_connection):
    connection, tenant_a, _tenant_b, _company_a, _company_b = postgres_connection
    connection.exec_driver_sql(f'SET LOCAL ROLE "{settings.database_runtime_role}"')
    assert connection.execute(text("SELECT count(*) FROM companies")).scalar_one() == 0

    connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_a)},
    )
    visible_tenants = connection.execute(
        text("SELECT DISTINCT tenant_id FROM companies")
    ).scalars().all()
    assert visible_tenants == [tenant_a]


def test_composite_fk_rejects_cross_tenant_reference(postgres_connection):
    connection, tenant_a, _tenant_b, _company_a, company_b = postgres_connection
    connection.exec_driver_sql(f'SET LOCAL ROLE "{settings.database_runtime_role}"')
    connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_a)},
    )
    with pytest.raises(IntegrityError):
        connection.execute(
            text(
                "INSERT INTO contacts "
                "(id, tenant_id, company_id, name, can_call, can_email, "
                "can_open_more, created_at) "
                "VALUES (:id, :tenant_id, :company_id, 'cross-tenant', "
                "true, true, true, now())"
            ),
            {
                "id": uuid4(),
                "tenant_id": tenant_a,
                "company_id": company_b,
            },
        )


def test_team_management_tables_are_default_deny(postgres_connection):
    connection, tenant_a, tenant_b, _company_a, _company_b = postgres_connection
    connection.execute(
        text(
            "INSERT INTO sales_teams "
            "(id, tenant_id, name, is_active, created_at) VALUES "
            "(:team_a, :tenant_a, 'Team A', true, now()), "
            "(:team_b, :tenant_b, 'Team B', true, now())"
        ),
        {
            "team_a": uuid4(),
            "team_b": uuid4(),
            "tenant_a": tenant_a,
            "tenant_b": tenant_b,
        },
    )
    connection.exec_driver_sql(f'SET LOCAL ROLE "{settings.database_runtime_role}"')
    assert connection.execute(text("SELECT count(*) FROM sales_teams")).scalar_one() == 0
    connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_a)},
    )
    assert connection.execute(text("SELECT name FROM sales_teams")).scalar_one() == "Team A"


def test_queue_rejects_cross_tenant_team(postgres_connection):
    connection, tenant_a, tenant_b, _company_a, _company_b = postgres_connection
    team_b = uuid4()
    connection.execute(
        text(
            "INSERT INTO sales_teams (id, tenant_id, name, is_active, created_at) "
            "VALUES (:id, :tenant_id, 'Foreign team', true, now())"
        ),
        {"id": team_b, "tenant_id": tenant_b},
    )
    connection.exec_driver_sql(f'SET LOCAL ROLE "{settings.database_runtime_role}"')
    connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_a)},
    )
    with pytest.raises(IntegrityError):
        connection.execute(
            text(
                "INSERT INTO lead_queues "
                "(id, tenant_id, name, team_id, strategy, routing_cursor, is_active, created_at) "
                "VALUES (:id, :tenant_id, 'Cross tenant', :team_id, "
                "'manual', 0, true, now())"
            ),
            {"id": uuid4(), "tenant_id": tenant_a, "team_id": team_b},
        )


def test_automation_tables_are_forced_rls_and_default_deny(postgres_connection):
    connection, tenant_a, tenant_b, _company_a, _company_b = postgres_connection
    user_a, user_b = uuid4(), uuid4()
    connection.execute(
        text(
            "INSERT INTO users (id, email, full_name, password_hash, is_active, created_at) VALUES "
            "(:user_a, :email_a, 'A', 'hash', true, now()), "
            "(:user_b, :email_b, 'B', 'hash', true, now())"
        ),
        {
            "user_a": user_a,
            "user_b": user_b,
            "email_a": f"rls-auto-a-{user_a}@example.com",
            "email_b": f"rls-auto-b-{user_b}@example.com",
        },
    )
    connection.execute(
        text(
            "INSERT INTO memberships (id, tenant_id, user_id, role, is_active, created_at) VALUES "
            "(:member_a, :tenant_a, :user_a, 'owner', true, now()), "
            "(:member_b, :tenant_b, :user_b, 'owner', true, now())"
        ),
        {
            "member_a": uuid4(),
            "member_b": uuid4(),
            "tenant_a": tenant_a,
            "tenant_b": tenant_b,
            "user_a": user_a,
            "user_b": user_b,
        },
    )
    connection.execute(
        text(
            "INSERT INTO message_templates "
            "(id, tenant_id, name, channel, subject, body, is_active, "
            "created_by_id, created_at, updated_at) VALUES "
            "(:id_a, :tenant_a, 'A', 'email', 'A', 'A', true, :user_a, now(), now()), "
            "(:id_b, :tenant_b, 'B', 'email', 'B', 'B', true, :user_b, now(), now())"
        ),
        {
            "id_a": uuid4(),
            "id_b": uuid4(),
            "tenant_a": tenant_a,
            "tenant_b": tenant_b,
            "user_a": user_a,
            "user_b": user_b,
        },
    )
    connection.execute(
        text(
            "INSERT INTO notifications "
            "(id, tenant_id, recipient_id, event_key, category, priority, title, "
            "metadata_json, created_at) VALUES "
            "(:id_a, :tenant_a, :user_a, 'event-a', 'automation', 'normal', "
            "'A notification', '{}', now()), "
            "(:id_b, :tenant_b, :user_b, 'event-b', 'automation', 'normal', "
            "'B notification', '{}', now())"
        ),
        {
            "id_a": uuid4(),
            "id_b": uuid4(),
            "tenant_a": tenant_a,
            "tenant_b": tenant_b,
            "user_a": user_a,
            "user_b": user_b,
        },
    )
    forced = connection.execute(
        text(
            "SELECT count(*) FROM pg_class WHERE relname IN "
            "('message_templates', 'automation_workflows', 'automation_runs', "
            "'approval_requests', 'automation_outbox', 'notifications') "
            "AND relrowsecurity AND relforcerowsecurity"
        )
    ).scalar_one()
    assert forced == 6
    connection.exec_driver_sql(f'SET LOCAL ROLE "{settings.database_runtime_role}"')
    assert connection.execute(text("SELECT count(*) FROM message_templates")).scalar_one() == 0
    assert connection.execute(text("SELECT count(*) FROM notifications")).scalar_one() == 0
    connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_a)},
    )
    assert connection.execute(text("SELECT name FROM message_templates")).scalar_one() == "A"
    assert connection.execute(text("SELECT title FROM notifications")).scalar_one() == "A notification"


def test_score_snapshots_are_forced_rls_and_default_deny(postgres_connection):
    connection, tenant_a, tenant_b, _company_a, _company_b = postgres_connection
    connection.execute(
        text(
            "INSERT INTO score_snapshots "
            "(id, tenant_id, entity_type, entity_id, score, grade, factors_json, "
            "model_version, calculation_reason, calculated_at) VALUES "
            "(:id_a, :tenant_a, 'lead', :entity_a, 80, 'hot', '[]', "
            "'rules-v1', 'test', now()), "
            "(:id_b, :tenant_b, 'deal', :entity_b, 40, 'cold', '[]', "
            "'rules-v1', 'test', now())"
        ),
        {
            "id_a": uuid4(),
            "id_b": uuid4(),
            "tenant_a": tenant_a,
            "tenant_b": tenant_b,
            "entity_a": uuid4(),
            "entity_b": uuid4(),
        },
    )
    forced = connection.execute(
        text(
            "SELECT relrowsecurity AND relforcerowsecurity "
            "FROM pg_class WHERE relname = 'score_snapshots'"
        )
    ).scalar_one()
    assert forced is True
    connection.exec_driver_sql(f'SET LOCAL ROLE "{settings.database_runtime_role}"')
    assert connection.execute(text("SELECT count(*) FROM score_snapshots")).scalar_one() == 0
    connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_a)},
    )
    assert connection.execute(text("SELECT score FROM score_snapshots")).scalar_one() == 80


def test_sequence_tables_are_forced_rls_and_tenant_safe(postgres_connection):
    connection, tenant_a, tenant_b, _company_a, _company_b = postgres_connection
    user_a, user_b = uuid4(), uuid4()
    cadence_a, cadence_b = uuid4(), uuid4()
    connection.execute(
        text(
            "INSERT INTO users (id, email, full_name, password_hash, is_active, created_at) VALUES "
            "(:user_a, :email_a, 'A', 'hash', true, now()), "
            "(:user_b, :email_b, 'B', 'hash', true, now())"
        ),
        {
            "user_a": user_a,
            "user_b": user_b,
            "email_a": f"rls-sequence-a-{user_a}@example.com",
            "email_b": f"rls-sequence-b-{user_b}@example.com",
        },
    )
    connection.execute(
        text(
            "INSERT INTO memberships (id, tenant_id, user_id, role, is_active, created_at) VALUES "
            "(:member_a, :tenant_a, :user_a, 'owner', true, now()), "
            "(:member_b, :tenant_b, :user_b, 'owner', true, now())"
        ),
        {
            "member_a": uuid4(),
            "member_b": uuid4(),
            "tenant_a": tenant_a,
            "tenant_b": tenant_b,
            "user_a": user_a,
            "user_b": user_b,
        },
    )
    connection.execute(
        text(
            "INSERT INTO cadences "
            "(id, tenant_id, name, is_active, created_by_id, updated_by_id, version, "
            "created_at, updated_at) VALUES "
            "(:cadence_a, :tenant_a, 'A', true, :user_a, :user_a, 1, now(), now()), "
            "(:cadence_b, :tenant_b, 'B', true, :user_b, :user_b, 1, now(), now())"
        ),
        {
            "cadence_a": cadence_a,
            "cadence_b": cadence_b,
            "tenant_a": tenant_a,
            "tenant_b": tenant_b,
            "user_a": user_a,
            "user_b": user_b,
        },
    )
    forced = connection.execute(
        text(
            "SELECT count(*) FROM pg_class WHERE relname IN "
            "('cadences', 'cadence_steps', 'cadence_enrollments', 'cadence_executions') "
            "AND relrowsecurity AND relforcerowsecurity"
        )
    ).scalar_one()
    assert forced == 4

    connection.exec_driver_sql(f'SET LOCAL ROLE "{settings.database_runtime_role}"')
    assert connection.execute(text("SELECT count(*) FROM cadences")).scalar_one() == 0
    connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_a)},
    )
    assert connection.execute(text("SELECT name FROM cadences")).scalar_one() == "A"
    with pytest.raises(IntegrityError):
        connection.execute(
            text(
                "INSERT INTO cadence_steps "
                "(id, tenant_id, cadence_id, position, step_type, delay_minutes, title, "
                "task_priority, created_at) VALUES "
                "(:id, :tenant_id, :cadence_id, 0, 'task', 0, 'Cross tenant', "
                "'normal', now())"
            ),
            {"id": uuid4(), "tenant_id": tenant_a, "cadence_id": cadence_b},
        )
def test_workflow_rejects_cross_tenant_actor(postgres_connection):
    connection, tenant_a, tenant_b, _company_a, _company_b = postgres_connection
    user_b = uuid4()
    connection.execute(
        text(
            "INSERT INTO users (id, email, full_name, password_hash, is_active, created_at) "
            "VALUES (:id, :email, 'Foreign', 'hash', true, now())"
        ),
        {"id": user_b, "email": f"foreign-workflow-{user_b}@example.com"},
    )
    connection.execute(
        text(
            "INSERT INTO memberships (id, tenant_id, user_id, role, is_active, created_at) "
            "VALUES (:id, :tenant_id, :user_id, 'owner', true, now())"
        ),
        {"id": uuid4(), "tenant_id": tenant_b, "user_id": user_b},
    )
    connection.exec_driver_sql(f'SET LOCAL ROLE "{settings.database_runtime_role}"')
    connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_a)},
    )
    with pytest.raises(IntegrityError):
        connection.execute(
            text(
                "INSERT INTO automation_workflows "
                "(id, tenant_id, name, trigger_type, conditions_json, condition_logic, "
                "actions_json, priority, is_active, created_by_id, updated_by_id, "
                "version, created_at, updated_at) VALUES "
                "(:id, :tenant_id, 'Cross tenant', 'lead.created', '[]', 'all', "
                "'[{\"type\":\"assign_owner\",\"config\":{}}]', 100, true, "
                ":user_id, :user_id, 1, now(), now())"
            ),
            {"id": uuid4(), "tenant_id": tenant_a, "user_id": user_b},
        )


def test_integration_tables_are_forced_rls_and_reject_cross_tenant_actor(
    postgres_connection,
):
    connection, tenant_a, tenant_b, _company_a, _company_b = postgres_connection
    user_a, user_b = uuid4(), uuid4()
    connection.execute(
        text(
            "INSERT INTO users (id, email, full_name, password_hash, is_active, created_at) VALUES "
            "(:user_a, :email_a, 'A', 'hash', true, now()), "
            "(:user_b, :email_b, 'B', 'hash', true, now())"
        ),
        {
            "user_a": user_a,
            "user_b": user_b,
            "email_a": f"rls-integration-a-{user_a}@example.com",
            "email_b": f"rls-integration-b-{user_b}@example.com",
        },
    )
    connection.execute(
        text(
            "INSERT INTO memberships (id, tenant_id, user_id, role, is_active, created_at) VALUES "
            "(:member_a, :tenant_a, :user_a, 'owner', true, now()), "
            "(:member_b, :tenant_b, :user_b, 'owner', true, now())"
        ),
        {
            "member_a": uuid4(),
            "member_b": uuid4(),
            "tenant_a": tenant_a,
            "tenant_b": tenant_b,
            "user_a": user_a,
            "user_b": user_b,
        },
    )
    connection.execute(
        text(
            "INSERT INTO webhook_endpoints "
            "(id, tenant_id, title, url, event_types_json, secret_encrypted, "
            "is_active, created_by_id, created_at, updated_at) VALUES "
            "(:id_a, :tenant_a, 'A', 'https://a.example.com', '[]', 'secret', "
            "true, :user_a, now(), now()), "
            "(:id_b, :tenant_b, 'B', 'https://b.example.com', '[]', 'secret', "
            "true, :user_b, now(), now())"
        ),
        {
            "id_a": uuid4(),
            "id_b": uuid4(),
            "tenant_a": tenant_a,
            "tenant_b": tenant_b,
            "user_a": user_a,
            "user_b": user_b,
        },
    )
    forced = connection.execute(
        text(
            "SELECT count(*) FROM pg_class WHERE relname IN "
            "('integration_jobs', 'webhook_endpoints', 'public_api_keys') "
            "AND relrowsecurity AND relforcerowsecurity"
        )
    ).scalar_one()
    assert forced == 3

    connection.exec_driver_sql(f'SET LOCAL ROLE "{settings.database_runtime_role}"')
    assert connection.execute(text("SELECT count(*) FROM webhook_endpoints")).scalar_one() == 0
    connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_a)},
    )
    assert connection.execute(text("SELECT title FROM webhook_endpoints")).scalar_one() == "A"
    with pytest.raises(IntegrityError):
        connection.execute(
            text(
                "INSERT INTO webhook_endpoints "
                "(id, tenant_id, title, url, event_types_json, secret_encrypted, "
                "is_active, created_by_id, created_at, updated_at) VALUES "
                "(:id, :tenant_a, 'Cross', 'https://cross.example.com', '[]', 'secret', "
                "true, :user_b, now(), now())"
            ),
            {"id": uuid4(), "tenant_a": tenant_a, "user_b": user_b},
        )
