from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.main  # noqa: F401
from app.core.database import Base, get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.modules.accounts.models import Membership, Tenant, User
from app.modules.notifications.models import Notification
from app.modules.notifications.service import NotificationService


@pytest.fixture
def notification_api() -> Generator[dict, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    tenant = Tenant(name="Notifications", slug=f"notifications-{uuid4()}")
    other_tenant = Tenant(name="Other", slug=f"notifications-other-{uuid4()}")
    owner = User(
        email=f"notification-owner-{uuid4()}@example.com",
        full_name="Owner",
        password_hash=hash_password("password123"),
    )
    rep = User(
        email=f"notification-rep-{uuid4()}@example.com",
        full_name="Rep",
        password_hash=hash_password("password123"),
    )
    db.add_all([tenant, other_tenant, owner, rep])
    db.flush()
    db.add_all([
        Membership(tenant_id=tenant.id, user_id=owner.id, role="owner"),
        Membership(tenant_id=tenant.id, user_id=rep.id, role="sales_rep"),
    ])
    db.commit()

    def override_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        yield {"client": TestClient(app), "db": db, "tenant": tenant, "owner": owner, "rep": rep}
    finally:
        app.dependency_overrides.clear()
        db.close()


def _headers(data: dict, user: str = "owner") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {create_access_token(data[user].id)}",
        "X-Tenant-Id": str(data["tenant"].id),
    }


def test_notifications_are_personal_idempotent_and_safe(notification_api):
    service = NotificationService(notification_api["db"])
    first = service.create(
        tenant_id=notification_api["tenant"].id,
        recipient_id=notification_api["owner"].id,
        event_key="automation:deal:1",
        category="automation",
        priority="high",
        title="Проверить сделку",
        body="Сценарий обнаружил риск",
        link="https://evil.example/steal",
    )
    duplicate = service.create(
        tenant_id=notification_api["tenant"].id,
        recipient_id=notification_api["owner"].id,
        event_key="automation:deal:1",
        category="automation",
        title="Duplicate",
    )
    service.create(
        tenant_id=notification_api["tenant"].id,
        recipient_id=notification_api["rep"].id,
        event_key="task:rep:1",
        category="task",
        title="Rep only",
        link="/tasks",
    )
    notification_api["db"].commit()

    assert first is not None
    assert duplicate is not None and duplicate.id == first.id
    assert first.link is None
    response = notification_api["client"].get("/notifications", headers=_headers(notification_api))
    assert response.status_code == 200
    assert [row["title"] for row in response.json()] == ["Проверить сделку"]
    assert response.headers["X-Total-Count"] == "1"

    hidden = notification_api["client"].patch(
        f"/notifications/{first.id}/read",
        headers=_headers(notification_api, "rep"),
        json={"read": True},
    )
    assert hidden.status_code == 404


def test_read_lifecycle_and_summary(notification_api):
    service = NotificationService(notification_api["db"])
    normal = service.create(
        tenant_id=notification_api["tenant"].id,
        recipient_id=notification_api["owner"].id,
        event_key="normal:1",
        category="system",
        title="Normal",
    )
    service.create(
        tenant_id=notification_api["tenant"].id,
        recipient_id=notification_api["owner"].id,
        event_key="critical:1",
        category="automation",
        priority="critical",
        title="Critical",
    )
    notification_api["db"].commit()
    assert normal is not None

    summary = notification_api["client"].get(
        "/notifications/summary", headers=_headers(notification_api)
    )
    assert summary.json() == {"unread_count": 2, "critical_count": 1}

    read = notification_api["client"].patch(
        f"/notifications/{normal.id}/read",
        headers=_headers(notification_api),
        json={"read": True},
    )
    assert read.status_code == 200
    assert read.json()["read_at"] is not None
    unread = notification_api["client"].get(
        "/notifications?unread_only=true", headers=_headers(notification_api)
    )
    assert [row["title"] for row in unread.json()] == ["Critical"]

    all_read = notification_api["client"].post(
        "/notifications/read-all", headers=_headers(notification_api), json={}
    )
    assert all_read.status_code == 204
    assert notification_api["db"].query(Notification).filter(Notification.read_at.is_(None)).count() == 0
