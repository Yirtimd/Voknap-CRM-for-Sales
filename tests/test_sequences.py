from collections.abc import Generator
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.main  # noqa: F401
from app.core.database import Base, get_db
from app.core.rbac import Role
from app.core.security import create_access_token, hash_password
from app.main import app
from app.modules.accounts.models import Membership, Tenant, User
from app.modules.activity.models import Activity
from app.modules.communication.schemas import CommunicationEventCreate
from app.modules.communication.service import CommunicationService
from app.modules.connectors.models import ConnectorAccount, IntegrationJob
from app.modules.sales.models import Company, Contact, Deal, Pipeline, PipelineStage, Task
from app.modules.sequences.models import CadenceEnrollment, CadenceExecution


@pytest.fixture
def sequence_api() -> Generator[dict, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    tenant = Tenant(name="Sequence Tenant", slug=f"sequence-{uuid4()}")
    other_tenant = Tenant(name="Other Tenant", slug=f"sequence-other-{uuid4()}")
    owner = User(
        email=f"sequence-owner-{uuid4()}@example.com",
        full_name="Sequence Owner",
        password_hash=hash_password("password123"),
    )
    rep = User(
        email=f"sequence-rep-{uuid4()}@example.com",
        full_name="Sequence Rep",
        password_hash=hash_password("password123"),
    )
    db.add_all([tenant, other_tenant, owner, rep])
    db.flush()
    db.add_all(
        [
            Membership(tenant_id=tenant.id, user_id=owner.id, role=Role.OWNER),
            Membership(tenant_id=tenant.id, user_id=rep.id, role=Role.SALES_REP),
        ]
    )
    company = Company(tenant_id=tenant.id, name="Sequence Co", owner_id=rep.id)
    pipeline = Pipeline(tenant_id=tenant.id, name="Sales")
    db.add_all([company, pipeline])
    db.flush()
    stage = PipelineStage(tenant_id=tenant.id, pipeline_id=pipeline.id, name="New")
    contact = Contact(
        tenant_id=tenant.id,
        company_id=company.id,
        name="Ирина Покупатель",
        email="buyer@example.com",
        phone="+79990000000",
        owner_id=rep.id,
    )
    db.add_all([stage, contact])
    db.flush()
    deal = Deal(
        tenant_id=tenant.id,
        company_id=company.id,
        stage_id=stage.id,
        title="Sequence Deal",
        owner_id=rep.id,
    )
    db.add(deal)
    db.commit()

    def override_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        yield {
            "client": TestClient(app),
            "db": db,
            "tenant": tenant,
            "other_tenant": other_tenant,
            "owner": owner,
            "rep": rep,
            "company": company,
            "contact": contact,
            "deal": deal,
        }
    finally:
        app.dependency_overrides.clear()
        db.close()


def _headers(data: dict, user: str = "owner", tenant_id=None) -> dict[str, str]:
    target_user = data[user]
    return {
        "Authorization": f"Bearer {create_access_token(target_user.id)}",
        "X-Tenant-Id": str(tenant_id or data["tenant"].id),
    }


def _create_cadence(data: dict) -> dict:
    response = data["client"].post(
        "/sequences",
        headers=_headers(data),
        json={
            "name": "B2B follow-up",
            "description": "Контакт после discovery",
            "steps": [
                {
                    "step_type": "manual_email",
                    "delay_minutes": 0,
                    "title": "Follow-up для {{contact.name}}",
                    "body": "Здравствуйте, {{contact.name}} из {{company.name}}",
                    "task_priority": "high",
                },
                {
                    "step_type": "call",
                    "delay_minutes": 60,
                    "title": "Обсудить предложение",
                    "task_priority": "normal",
                },
            ],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_sequence_creates_contact_tasks_and_timeline(sequence_api):
    cadence = _create_cadence(sequence_api)
    enrolled = sequence_api["client"].post(
        "/sequences/enrollments",
        headers=_headers(sequence_api, "rep"),
        json={
            "cadence_id": cadence["id"],
            "contact_id": str(sequence_api["contact"].id),
            "deal_id": str(sequence_api["deal"].id),
        },
    )
    assert enrolled.status_code == 201, enrolled.text
    assert enrolled.json()["status"] == "active"

    run = sequence_api["client"].post(
        "/sequences/run-due", headers=_headers(sequence_api)
    )
    assert run.status_code == 200
    assert run.json() == {"evaluated": 1, "executed": 1}

    task = sequence_api["db"].query(Task).one()
    assert task.assigned_to_id == sequence_api["rep"].id
    assert "Ирина Покупатель" in task.title
    execution = sequence_api["db"].query(CadenceExecution).one()
    assert execution.task_id == task.id
    assert execution.status == "succeeded"
    enrollment = sequence_api["db"].query(CadenceEnrollment).one()
    assert enrollment.current_step == 1
    assert enrollment.status == "active"
    activities = sequence_api["db"].query(Activity).filter(Activity.type == "CADENCE").all()
    assert len(activities) == 2
    assert all(row.contact_id == sequence_api["contact"].id for row in activities)


def test_inbound_reply_stops_active_sequence(sequence_api):
    cadence = _create_cadence(sequence_api)
    enrolled = sequence_api["client"].post(
        "/sequences/enrollments",
        headers=_headers(sequence_api, "rep"),
        json={
            "cadence_id": cadence["id"],
            "contact_id": str(sequence_api["contact"].id),
        },
    )
    assert enrolled.status_code == 201

    CommunicationService(sequence_api["db"]).create(
        tenant_id=sequence_api["tenant"].id,
        created_by=sequence_api["rep"].id,
        payload=CommunicationEventCreate(
            channel="email",
            direction="inbound",
            external_id=f"reply-{uuid4()}",
            sender=sequence_api["contact"].email,
            recipient=sequence_api["rep"].email,
            subject="Re: предложение",
            body="Готовы обсудить",
            occurred_at=datetime.now(timezone.utc),
            company_id=sequence_api["company"].id,
            contact_id=sequence_api["contact"].id,
            deal_id=sequence_api["deal"].id,
        ),
    )

    enrollment = sequence_api["db"].query(CadenceEnrollment).one()
    assert enrollment.status == "replied"
    assert enrollment.next_run_at is None
    assert enrollment.stop_reason == "Получен входящий ответ"
    assert (
        sequence_api["db"]
        .query(Activity)
        .filter(Activity.title == "Sequence завершена: получен ответ")
        .count()
        == 1
    )


def test_sequence_permissions_and_cross_tenant_access(sequence_api):
    denied = sequence_api["client"].post(
        "/sequences",
        headers=_headers(sequence_api, "rep"),
        json={
            "name": "Denied",
            "steps": [{"step_type": "task", "title": "Task"}],
        },
    )
    assert denied.status_code == 403

    cadence = _create_cadence(sequence_api)
    foreign = sequence_api["client"].post(
        "/sequences/enrollments",
        headers=_headers(sequence_api, tenant_id=sequence_api["other_tenant"].id),
        json={
            "cadence_id": cadence["id"],
            "contact_id": str(sequence_api["contact"].id),
        },
    )
    assert foreign.status_code == 403


def test_automatic_email_requires_connector_and_uses_background_job(sequence_api):
    created = sequence_api["client"].post(
        "/sequences",
        headers=_headers(sequence_api),
        json={
            "name": "Automatic follow-up",
            "steps": [
                {
                    "step_type": "automatic_email",
                    "delay_minutes": 0,
                    "title": "Для {{contact.name}}",
                    "body": "Компания {{company.name}}",
                }
            ],
        },
    )
    assert created.status_code == 201
    without_connector = sequence_api["client"].post(
        "/sequences/enrollments",
        headers=_headers(sequence_api, "rep"),
        json={
            "cadence_id": created.json()["id"],
            "contact_id": str(sequence_api["contact"].id),
        },
    )
    assert without_connector.status_code == 422
    assert "connected email account" in without_connector.text

    account = ConnectorAccount(
        tenant_id=sequence_api["tenant"].id,
        connector_code="email",
        title="Sales mailbox",
        status="connected",
        credentials_json="{}",
        settings_json="{}",
    )
    sequence_api["db"].add(account)
    sequence_api["db"].commit()
    enrolled = sequence_api["client"].post(
        "/sequences/enrollments",
        headers=_headers(sequence_api, "rep"),
        json={
            "cadence_id": created.json()["id"],
            "contact_id": str(sequence_api["contact"].id),
            "deal_id": str(sequence_api["deal"].id),
            "connector_account_id": str(account.id),
        },
    )
    assert enrolled.status_code == 201, enrolled.text
    run = sequence_api["client"].post(
        "/sequences/run-due", headers=_headers(sequence_api)
    )
    assert run.json()["executed"] == 1

    job = sequence_api["db"].query(IntegrationJob).one()
    assert job.job_type == "email.send"
    assert job.status == "pending"
    assert str(sequence_api["contact"].id) in job.payload_json
    execution = sequence_api["db"].query(CadenceExecution).one()
    assert execution.status == "queued"
    assert execution.integration_job_id == job.id
