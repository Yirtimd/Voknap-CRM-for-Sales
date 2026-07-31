import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

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
from app.modules.analytics.service import AnalyticsService
from app.modules.automation.models import AutomationRun, AutomationWorkflow
from app.modules.sales.models import (
    Company,
    Contact,
    Deal,
    Lead,
    Pipeline,
    PipelineStage,
    ScoreSnapshot,
    Task,
)
from app.modules.sales.scoring import ScoringService


def _workspace() -> tuple[Session, dict]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    tenant = Tenant(name="Scoring Tenant", slug=f"scoring-{uuid4()}")
    user = User(
        email=f"scoring-{uuid4()}@example.com",
        full_name="Scoring Owner",
        password_hash=hash_password("password123"),
    )
    db.add_all([tenant, user])
    db.flush()
    db.add(Membership(tenant_id=tenant.id, user_id=user.id, role=Role.OWNER))
    company = Company(
        tenant_id=tenant.id,
        name="Complete Company",
        website="https://example.com",
        industry="Software",
        owner_id=user.id,
    )
    pipeline = Pipeline(tenant_id=tenant.id, name="Sales")
    db.add_all([company, pipeline])
    db.flush()
    stage = PipelineStage(
        tenant_id=tenant.id,
        pipeline_id=pipeline.id,
        name="Discovery",
        probability=40,
    )
    contact = Contact(
        tenant_id=tenant.id,
        company_id=company.id,
        name="Buyer",
        email="buyer@example.com",
        phone="+79990000000",
        owner_id=user.id,
    )
    db.add_all([stage, contact])
    db.flush()
    lead = Lead(
        tenant_id=tenant.id,
        company_id=company.id,
        contact_id=contact.id,
        title="Referral lead",
        source="referral",
        status="new",
        owner_id=user.id,
    )
    db.add(lead)
    db.flush()
    deal = Deal(
        tenant_id=tenant.id,
        company_id=company.id,
        lead_id=lead.id,
        stage_id=stage.id,
        title="Scored deal",
        amount=500000,
        discount_percent=5,
        probability=40,
        expected_close_date=datetime.now(timezone.utc) + timedelta(days=30),
        next_step="Demo",
        risk_level="low",
        owner_id=user.id,
    )
    db.add(deal)
    db.flush()
    db.add(
        Activity(
            tenant_id=tenant.id,
            company_id=company.id,
            deal_id=deal.id,
            type="MEETING",
            title="Discovery call",
            created_by=user.id,
        )
    )
    db.commit()
    return db, {
        "tenant": tenant,
        "user": user,
        "lead": lead,
        "deal": deal,
    }


def test_explainable_scoring_persists_factors_and_drives_forecast():
    db, data = _workspace()
    try:
        service = ScoringService(db)
        lead_result = service.recalculate_lead(
            data["lead"], actor_id=data["user"].id, reason="test"
        )
        deal_result = service.recalculate_deal(
            data["deal"], actor_id=data["user"].id, reason="test"
        )
        db.commit()

        assert lead_result.score == 80
        assert lead_result.grade == "hot"
        assert deal_result.score == 82
        assert deal_result.forecast_probability == 59
        assert len(data["deal"].score_factors) == 9
        assert db.query(ScoreSnapshot).count() == 2

        forecast = AnalyticsService._forecast(
            datetime.now(timezone.utc), [data["deal"]], 90
        )
        assert forecast.weighted_revenue == 295000
        assert forecast.scoring_coverage_rate == 100
    finally:
        db.close()


def test_score_change_can_trigger_automation_and_history_api_is_tenant_safe():
    db, data = _workspace()
    workflow = AutomationWorkflow(
        tenant_id=data["tenant"].id,
        name="Prioritize hot opportunity",
        trigger_type="deal.score_changed",
        conditions_json=json.dumps(
            [{"field": "new_score", "operator": "gte", "value": 75}]
        ),
        actions_json=json.dumps(
            [
                {
                    "type": "create_task",
                    "config": {
                        "assignee": "owner",
                        "title": "Review hot opportunity",
                        "due_in_days": 1,
                        "priority": "high",
                    },
                }
            ]
        ),
        created_by_id=data["user"].id,
        updated_by_id=data["user"].id,
    )
    db.add(workflow)
    ScoringService(db).recalculate_lead(
        data["lead"], actor_id=data["user"].id, reason="test_dependency"
    )
    db.commit()

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    headers = {
        "Authorization": f"Bearer {create_access_token(data['user'].id)}",
        "X-Tenant-Id": str(data["tenant"].id),
    }
    try:
        response = TestClient(app).post(
            f"/sales/scoring/deal/{data['deal'].id}/recalculate",
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["score"] == 82
        assert db.query(AutomationRun).one().trigger_type == "deal.score_changed"
        assert db.query(Task).one().title == "Review hot opportunity"

        history = TestClient(app).get(
            f"/sales/scoring/deal/{data['deal'].id}/history",
            headers=headers,
        )
        assert history.status_code == 200
        assert history.json()[0]["factors"][0]["key"] == "stage"

        foreign_id = uuid4()
        missing = TestClient(app).get(
            f"/sales/scoring/deal/{foreign_id}/history",
            headers=headers,
        )
        assert missing.status_code == 404
    finally:
        app.dependency_overrides.clear()
        db.close()
