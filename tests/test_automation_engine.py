from collections.abc import Generator
from datetime import datetime, timedelta, timezone
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
from app.modules.automation.models import (
    ApprovalRequest,
    AutomationOutbox,
    AutomationRun,
    MessageTemplate,
)
from app.modules.notifications.models import Notification
from app.modules.sales.models import Company, Contact, Deal, NextAction, Pipeline, PipelineStage, Task


@pytest.fixture
def automation_api() -> Generator[dict, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    tenant = Tenant(name="Automation Tenant", slug=f"automation-{uuid4()}")
    other_tenant = Tenant(name="Other Tenant", slug=f"automation-other-{uuid4()}")
    db.add_all([tenant, other_tenant])
    db.flush()

    users = {}
    memberships = {}
    for name, role in (
        ("owner", Role.OWNER),
        ("manager", Role.SALES_MANAGER),
        ("rep", Role.SALES_REP),
    ):
        user = User(
            email=f"automation-{name}-{uuid4()}@example.com",
            full_name=name,
            password_hash=hash_password("password123"),
        )
        db.add(user)
        db.flush()
        membership = Membership(tenant_id=tenant.id, user_id=user.id, role=role)
        db.add(membership)
        users[name] = user
        memberships[name] = membership
    db.flush()
    memberships["rep"].manager_membership_id = memberships["manager"].id

    pipeline = Pipeline(tenant_id=tenant.id, name="Sales")
    db.add(pipeline)
    db.flush()
    new_stage = PipelineStage(tenant_id=tenant.id, pipeline_id=pipeline.id, name="Новый", sort_order=0)
    proposal_stage = PipelineStage(tenant_id=tenant.id, pipeline_id=pipeline.id, name="КП", sort_order=1)
    company = Company(tenant_id=tenant.id, name="Automation Co", owner_id=users["rep"].id)
    db.add_all([new_stage, proposal_stage, company])
    db.flush()
    contact = Contact(
        tenant_id=tenant.id,
        company_id=company.id,
        name="Buyer",
        email="buyer@example.com",
        owner_id=users["rep"].id,
    )
    deal = Deal(
        tenant_id=tenant.id,
        company_id=company.id,
        stage_id=new_stage.id,
        title="Automation Deal",
        amount=100000,
        owner_id=users["rep"].id,
        created_at=datetime.now(timezone.utc) - timedelta(days=8),
    )
    db.add_all([contact, deal])
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
            "users": users,
            "memberships": memberships,
            "company": company,
            "contact": contact,
            "deal": deal,
            "new_stage": new_stage,
            "proposal_stage": proposal_stage,
        }
    finally:
        app.dependency_overrides.clear()
        db.close()


def _headers(data: dict, user: str = "owner") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {create_access_token(data['users'][user].id)}",
        "X-Tenant-Id": str(data["tenant"].id),
    }


def _workflow(data: dict, payload: dict) -> dict:
    response = data["client"].post(
        "/automations/workflows",
        headers=_headers(data),
        json=payload,
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_new_lead_can_be_assigned_to_owner_manager(automation_api):
    _workflow(
        automation_api,
        {
            "name": "Escalate inbound lead",
            "trigger_type": "lead.created",
            "conditions": [{"field": "source", "operator": "eq", "value": "website"}],
            "actions": [{"type": "assign_owner", "config": {"assignee": "owner_manager"}}],
        },
    )
    response = automation_api["client"].post(
        "/sales/leads",
        headers=_headers(automation_api),
        json={
            "company_id": str(automation_api["company"].id),
            "title": "Website lead",
            "source": "website",
        },
    )

    assert response.status_code == 201
    assert response.json()["owner_id"] == str(automation_api["users"]["manager"].id)
    run = automation_api["db"].query(AutomationRun).one()
    assert run.status == "succeeded"


def test_inactive_deal_scan_is_idempotent_and_creates_task(automation_api):
    _workflow(
        automation_api,
        {
            "name": "Stale deal follow-up",
            "trigger_type": "schedule.deal_inactive",
            "conditions": [{"field": "inactive_days", "operator": "gte", "value": 7}],
            "actions": [
                {
                    "type": "create_task",
                    "config": {
                        "title": "Связаться по {{title}}",
                        "assignee": "owner",
                        "due_in_days": 1,
                    },
                }
            ],
        },
    )
    first = automation_api["client"].post(
        "/automations/run-scheduled", headers=_headers(automation_api)
    )
    second = automation_api["client"].post(
        "/automations/run-scheduled", headers=_headers(automation_api)
    )

    assert first.status_code == 200
    assert first.json()["matched_runs"] == 1
    assert second.json()["matched_runs"] == 0
    tasks = automation_api["db"].query(Task).filter(Task.deal_id == automation_api["deal"].id).all()
    assert len(tasks) == 1
    assert tasks[0].assigned_to_id == automation_api["users"]["rep"].id


def test_proposal_stage_queues_rendered_template(automation_api):
    template = automation_api["client"].post(
        "/automations/templates",
        headers=_headers(automation_api),
        json={
            "name": "Proposal",
            "channel": "email",
            "subject": "КП: {{title}}",
            "body": "Сумма: {{amount}}",
        },
    )
    assert template.status_code == 201
    _workflow(
        automation_api,
        {
            "name": "Send proposal",
            "trigger_type": "deal.stage_changed",
            "conditions": [{"field": "stage_name", "operator": "eq", "value": "КП"}],
            "actions": [
                {
                    "type": "send_template",
                    "config": {"template_id": template.json()["id"]},
                }
            ],
        },
    )
    moved = automation_api["client"].patch(
        f"/sales/deals/{automation_api['deal'].id}/move",
        headers=_headers(automation_api),
        json={"stage_id": str(automation_api["proposal_stage"].id), "version": 1},
    )

    assert moved.status_code == 200
    outbox = automation_api["db"].query(AutomationOutbox).one()
    assert outbox.status == "pending"
    assert outbox.recipient == "buyer@example.com"
    assert outbox.subject == "КП: Automation Deal"


def test_large_discount_requests_approval_and_manager_decides(automation_api):
    _workflow(
        automation_api,
        {
            "name": "Discount approval",
            "trigger_type": "deal.updated",
            "conditions": [
                {"field": "discount_percent", "operator": "gte", "value": 20},
                {"field": "changed_fields", "operator": "contains", "value": "discount_percent"},
            ],
            "actions": [
                {
                    "type": "request_approval",
                    "config": {
                        "title": "Скидка {{discount_percent}}%",
                        "reason": "Сделка {{title}}",
                        "user_id": str(automation_api["users"]["manager"].id),
                    },
                }
            ],
        },
    )
    updated = automation_api["client"].patch(
        f"/sales/deals/{automation_api['deal'].id}",
        headers=_headers(automation_api),
        json={"version": 1, "discount_percent": 25},
    )
    assert updated.status_code == 200
    approval = automation_api["db"].query(ApprovalRequest).one()
    decision = automation_api["client"].post(
        f"/automations/approvals/{approval.id}/decision",
        headers=_headers(automation_api, "manager"),
        json={"version": approval.version, "decision": "approved", "comment": "Допустимо"},
    )

    assert decision.status_code == 200
    assert decision.json()["status"] == "approved"
    assert decision.json()["decided_by_id"] == str(automation_api["users"]["manager"].id)


def test_approval_pauses_remaining_actions_until_decision(automation_api):
    _workflow(
        automation_api,
        {
            "name": "Pause for approval",
            "trigger_type": "deal.updated",
            "conditions": [{"field": "discount_percent", "operator": "gte", "value": 15}],
            "actions": [
                {
                    "type": "request_approval",
                    "config": {
                        "title": "Approve discount",
                        "user_id": str(automation_api["users"]["manager"].id),
                        "due_in_hours": 12,
                        "priority": "high",
                    },
                },
                {
                    "type": "create_task",
                    "config": {
                        "title": "Prepare approved offer",
                        "user_id": str(automation_api["users"]["rep"].id),
                        "due_in_days": 1,
                    },
                },
            ],
        },
    )
    updated = automation_api["client"].patch(
        f"/sales/deals/{automation_api['deal'].id}",
        headers=_headers(automation_api),
        json={"version": 1, "discount_percent": 20},
    )
    assert updated.status_code == 200
    run = automation_api["db"].query(AutomationRun).one()
    approval = automation_api["db"].query(ApprovalRequest).one()
    assert run.status == "waiting_approval"
    assert run.completed_at is None
    assert automation_api["db"].query(Task).count() == 0

    decision = automation_api["client"].post(
        f"/automations/approvals/{approval.id}/decision",
        headers=_headers(automation_api, "manager"),
        json={"version": approval.version, "decision": "approved", "comment": "OK"},
    )
    automation_api["db"].refresh(run)
    assert decision.status_code == 200
    assert run.status == "succeeded"
    assert run.completed_at is not None
    assert automation_api["db"].query(Task).one().title == "Prepare approved offer"


def test_pipeline_configuration_is_versioned_and_terminal_stage_updates_deal(automation_api):
    created = automation_api["client"].post(
        "/sales/pipelines",
        headers=_headers(automation_api),
        json={
            "name": "Enterprise",
            "is_default": True,
            "stages": [
                {"name": "Discovery", "code": "discovery", "probability": 20},
                {
                    "name": "Won",
                    "code": "won",
                    "probability": 100,
                    "stage_type": "won",
                    "required_fields": ["amount"],
                },
            ],
        },
    )
    assert created.status_code == 201, created.text
    pipeline = created.json()
    assert pipeline["version"] == 1
    assert pipeline["is_default"] is True

    won_stage = pipeline["stages"][1]
    moved = automation_api["client"].patch(
        f"/sales/deals/{automation_api['deal'].id}/move",
        headers=_headers(automation_api),
        json={"version": 1, "stage_id": won_stage["id"]},
    )
    assert moved.status_code == 200, moved.text
    assert moved.json()["status"] == "won"
    assert moved.json()["probability"] == 100


def test_new_communication_updates_next_action(automation_api):
    _workflow(
        automation_api,
        {
            "name": "Inbound follow-up",
            "trigger_type": "communication.created",
            "conditions": [{"field": "direction", "operator": "eq", "value": "inbound"}],
            "actions": [
                {
                    "type": "update_next_action",
                    "config": {
                        "title": "Ответить: {{subject}}",
                        "assignee": "owner",
                        "due_in_days": 1,
                    },
                }
            ],
        },
    )
    response = automation_api["client"].post(
        "/communication/events",
        headers=_headers(automation_api),
        json={
            "channel": "email",
            "direction": "inbound",
            "sender": "buyer@example.com",
            "subject": "Новый вопрос",
            "company_id": str(automation_api["company"].id),
            "deal_id": str(automation_api["deal"].id),
        },
    )

    assert response.status_code == 201
    next_action = automation_api["db"].query(NextAction).one()
    assert next_action.title == "Ответить: Новый вопрос"
    assert next_action.assigned_to_id == automation_api["users"]["rep"].id


def test_workflow_creates_personal_notification(automation_api):
    _workflow(
        automation_api,
        {
            "name": "Notify deal owner",
            "trigger_type": "deal.updated",
            "conditions": [],
            "actions": [
                {
                    "type": "notify_user",
                    "config": {
                        "assignee": "owner",
                        "title": "Проверьте {{title}}",
                        "body": "Сумма сделки изменилась",
                        "priority": "high",
                    },
                }
            ],
        },
    )
    response = automation_api["client"].patch(
        f"/sales/deals/{automation_api['deal'].id}",
        headers=_headers(automation_api),
        json={"version": 1, "amount": 120000},
    )
    assert response.status_code == 200, response.text

    notification = automation_api["db"].query(Notification).one()
    assert notification.recipient_id == automation_api["users"]["rep"].id
    assert notification.title == "Проверьте Automation Deal"
    assert notification.priority == "high"
    assert notification.link == f"/deals?deal={automation_api['deal'].id}"

    inbox = automation_api["client"].get(
        "/notifications", headers=_headers(automation_api, "rep")
    )
    assert inbox.status_code == 200
    assert inbox.json()[0]["category"] == "automation"


def test_sales_rep_cannot_manage_workflows_and_cross_tenant_template_is_hidden(automation_api):
    denied = automation_api["client"].post(
        "/automations/workflows",
        headers=_headers(automation_api, "rep"),
        json={
            "name": "Denied",
            "trigger_type": "lead.created",
            "actions": [{"type": "assign_owner", "config": {"assignee": "owner"}}],
        },
    )
    foreign_template_id = uuid4()
    foreign_user = User(
        email=f"foreign-automation-{uuid4()}@example.com",
        full_name="Foreign",
        password_hash=hash_password("password123"),
    )
    automation_api["db"].add(foreign_user)
    automation_api["db"].flush()
    automation_api["db"].add(
        Membership(
            tenant_id=automation_api["other_tenant"].id,
            user_id=foreign_user.id,
            role=Role.OWNER,
        )
    )
    automation_api["db"].add(
        MessageTemplate(
            id=foreign_template_id,
            tenant_id=automation_api["other_tenant"].id,
            name="Foreign",
            subject="Foreign",
            body="Foreign",
            created_by_id=foreign_user.id,
        )
    )
    automation_api["db"].commit()
    cross_tenant = automation_api["client"].post(
        "/automations/workflows",
        headers=_headers(automation_api),
        json={
            "name": "Cross tenant",
            "trigger_type": "deal.stage_changed",
            "actions": [
                {"type": "send_template", "config": {"template_id": str(foreign_template_id)}}
            ],
        },
    )

    assert denied.status_code == 403
    assert cross_tenant.status_code == 404
