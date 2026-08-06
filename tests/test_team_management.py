from collections.abc import Generator
from uuid import UUID, uuid4

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
from app.modules.sales.models import Company


@pytest.fixture
def team_api() -> Generator[dict, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    tenant = Tenant(name="Team Tenant", slug=f"team-{uuid4()}")
    other_tenant = Tenant(name="Other Tenant", slug=f"other-{uuid4()}")
    db.add_all([tenant, other_tenant])
    db.flush()

    users: dict[str, User] = {}
    memberships: dict[str, Membership] = {}
    for name, role in (
        ("owner", Role.OWNER),
        ("manager", Role.SALES_MANAGER),
        ("rep_one", Role.SALES_REP),
        ("rep_two", Role.SALES_REP),
    ):
        user = User(
            email=f"{name}-{uuid4()}@example.com",
            full_name=name,
            password_hash=hash_password("password123"),
        )
        db.add(user)
        db.flush()
        membership = Membership(tenant_id=tenant.id, user_id=user.id, role=role)
        db.add(membership)
        users[name] = user
        memberships[name] = membership

    foreign_user = User(
        email=f"foreign-{uuid4()}@example.com",
        full_name="foreign",
        password_hash=hash_password("password123"),
    )
    db.add(foreign_user)
    db.flush()
    foreign_membership = Membership(
        tenant_id=other_tenant.id,
        user_id=foreign_user.id,
        role=Role.SALES_MANAGER,
    )
    db.add(foreign_membership)
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
            "foreign_membership": foreign_membership,
        }
    finally:
        app.dependency_overrides.clear()
        db.close()


def _headers(data: dict, name: str = "owner") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {create_access_token(data['users'][name].id)}",
        "X-Tenant-Id": str(data["tenant"].id),
    }


def test_invitation_is_one_time_and_creates_active_membership(team_api):
    invitation = team_api["client"].post(
        "/accounts/invitations",
        headers=_headers(team_api),
        json={"email": "new.rep@example.com", "role": "sales_rep"},
    )
    assert invitation.status_code == 201
    assert invitation.json()["token"]

    accepted = team_api["client"].post(
        "/auth/invitations/accept",
        json={
            "token": invitation.json()["token"],
            "full_name": "New Rep",
            "password": "Invitation-Password-2026!",
        },
    )
    repeated = team_api["client"].post(
        "/auth/invitations/accept",
        json={
            "token": invitation.json()["token"],
            "full_name": "New Rep",
            "password": "Invitation-Password-2026!",
        },
    )

    assert accepted.status_code == 200
    assert repeated.status_code == 404
    membership = (
        team_api["db"]
        .query(Membership)
        .filter(Membership.user_id == UUID(accepted.json()["user_id"]))
        .one()
    )
    assert membership.role == "sales_rep"
    assert membership.is_active is True


def test_deactivation_requires_and_applies_ownership_reassignment(team_api):
    rep = team_api["users"]["rep_one"]
    replacement = team_api["users"]["rep_two"]
    company = Company(tenant_id=team_api["tenant"].id, name="Owned", owner_id=rep.id)
    team_api["db"].add(company)
    team_api["db"].commit()
    membership = team_api["memberships"]["rep_one"]

    blocked = team_api["client"].patch(
        f"/accounts/members/{membership.id}/status",
        headers=_headers(team_api),
        json={"is_active": False},
    )
    changed = team_api["client"].patch(
        f"/accounts/members/{membership.id}/status",
        headers=_headers(team_api),
        json={"is_active": False, "reassign_to_user_id": str(replacement.id)},
    )

    assert blocked.status_code == 409
    assert changed.status_code == 200
    assert changed.json()["is_active"] is False
    team_api["db"].refresh(company)
    assert company.owner_id == replacement.id
    denied = team_api["client"].get("/sales/companies", headers=_headers(team_api, "rep_one"))
    assert denied.status_code == 403


def test_team_hierarchy_rejects_cycles_and_cross_tenant_members(team_api):
    team = team_api["client"].post(
        "/accounts/teams",
        headers=_headers(team_api, "manager"),
        json={"name": "Enterprise", "manager_membership_id": str(team_api["memberships"]["manager"].id)},
    )
    assert team.status_code == 201

    rep_one = team_api["memberships"]["rep_one"]
    rep_two = team_api["memberships"]["rep_two"]
    first = team_api["client"].patch(
        f"/accounts/members/{rep_one.id}/structure",
        headers=_headers(team_api),
        json={"team_id": team.json()["id"], "manager_membership_id": str(rep_two.id)},
    )
    second = team_api["client"].patch(
        f"/accounts/members/{rep_two.id}/structure",
        headers=_headers(team_api),
        json={"team_id": team.json()["id"], "manager_membership_id": str(rep_one.id)},
    )
    foreign = team_api["client"].patch(
        f"/accounts/members/{rep_two.id}/structure",
        headers=_headers(team_api),
        json={"manager_membership_id": str(team_api["foreign_membership"].id)},
    )

    assert first.status_code == 200
    assert second.status_code == 409
    assert foreign.status_code == 404


def test_lead_queue_round_robin_assignment_rule(team_api):
    member_ids = [
        str(team_api["memberships"]["rep_one"].id),
        str(team_api["memberships"]["rep_two"].id),
    ]
    queue = team_api["client"].post(
        "/accounts/queues",
        headers=_headers(team_api, "manager"),
        json={"name": "Inbound", "strategy": "round_robin", "membership_ids": member_ids},
    )
    assert queue.status_code == 201
    rule = team_api["client"].post(
        "/accounts/assignment-rules",
        headers=_headers(team_api, "manager"),
        json={
            "name": "Website inbound",
            "entity_type": "lead",
            "criteria": {"source": "website"},
            "target_type": "queue",
            "target_id": queue.json()["id"],
            "priority": 10,
        },
    )
    assert rule.status_code == 201
    company = team_api["client"].post(
        "/sales/companies",
        headers=_headers(team_api),
        json={"name": "Inbound account"},
    )
    leads = [
        team_api["client"].post(
            "/sales/leads",
            headers=_headers(team_api),
            json={"company_id": company.json()["id"], "title": f"Lead {index}", "source": "website"},
        )
        for index in range(2)
    ]

    assert all(response.status_code == 201 for response in leads)
    assert {response.json()["owner_id"] for response in leads} == {
        str(team_api["users"]["rep_one"].id),
        str(team_api["users"]["rep_two"].id),
    }
    assert all(response.json()["queue_id"] == queue.json()["id"] for response in leads)


def test_territory_assigns_matching_company_and_rejects_foreign_owner(team_api):
    territory = team_api["client"].post(
        "/accounts/territories",
        headers=_headers(team_api, "manager"),
        json={
            "name": "RU SaaS",
            "country_code": "ru",
            "industry": "SaaS",
            "owner_membership_id": str(team_api["memberships"]["manager"].id),
        },
    )
    assert territory.status_code == 201
    company = team_api["client"].post(
        "/sales/companies",
        headers=_headers(team_api),
        json={"name": "Territory account", "country_code": "ru", "industry": "saas"},
    )
    foreign = team_api["client"].post(
        "/accounts/territories",
        headers=_headers(team_api, "manager"),
        json={
            "name": "Foreign",
            "owner_membership_id": str(team_api["foreign_membership"].id),
        },
    )

    assert company.status_code == 201
    assert company.json()["territory_id"] == territory.json()["id"]
    assert company.json()["owner"]["id"] == str(team_api["users"]["manager"].id)
    assert foreign.status_code == 404
