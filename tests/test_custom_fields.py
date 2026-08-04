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
from app.modules.sales.models import Company


@pytest.fixture
def custom_fields_api() -> Generator[dict, None, None]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    tenant = Tenant(name="Custom fields", slug=f"fields-{uuid4()}")
    other = Tenant(name="Other", slug=f"fields-other-{uuid4()}")
    owner = User(
        email=f"fields-owner-{uuid4()}@example.com",
        full_name="Owner",
        password_hash=hash_password("password123"),
    )
    rep = User(
        email=f"fields-rep-{uuid4()}@example.com",
        full_name="Rep",
        password_hash=hash_password("password123"),
    )
    db.add_all([tenant, other, owner, rep])
    db.flush()
    db.add_all(
        [
            Membership(tenant_id=tenant.id, user_id=owner.id, role="owner"),
            Membership(tenant_id=tenant.id, user_id=rep.id, role="sales_rep"),
        ]
    )
    db.flush()
    own_company = Company(tenant_id=tenant.id, name="Owned", owner_id=rep.id)
    foreign_company = Company(tenant_id=other.id, name="Foreign")
    db.add_all([own_company, foreign_company])
    db.commit()

    def override_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        yield {
            "client": TestClient(app),
            "db": db,
            "tenant": tenant,
            "other": other,
            "owner": owner,
            "rep": rep,
            "company": own_company,
            "foreign_company": foreign_company,
        }
    finally:
        app.dependency_overrides.clear()
        db.close()


def _headers(data: dict, user: str = "owner", tenant: str = "tenant") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {create_access_token(data[user].id)}",
        "X-Tenant-Id": str(data[tenant].id),
    }


def _definition(data: dict, **changes) -> dict:
    payload = {
        "entity_type": "companies",
        "code": "customer_segment",
        "label": "Сегмент клиента",
        "field_type": "select",
        "options": ["Enterprise", "SMB"],
        "is_required": True,
    }
    payload.update(changes)
    response = data["client"].post(
        "/custom-fields/definitions", headers=_headers(data), json=payload
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_definition_rbac_values_filter_and_report(custom_fields_api):
    data = custom_fields_api
    denied = data["client"].post(
        "/custom-fields/definitions",
        headers=_headers(data, "rep"),
        json={
            "entity_type": "companies",
            "code": "denied_field",
            "label": "Denied",
            "field_type": "text",
        },
    )
    assert denied.status_code == 403

    field = _definition(data)
    saved = data["client"].put(
        f"/custom-fields/values/companies/{data['company'].id}",
        headers=_headers(data, "rep"),
        json={"values": [{"field_id": field["id"], "value": "Enterprise", "version": 0}]},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()[0]["value"] == "Enterprise"
    assert saved.json()[0]["version"] == 1

    conflict = data["client"].put(
        f"/custom-fields/values/companies/{data['company'].id}",
        headers=_headers(data, "rep"),
        json={"values": [{"field_id": field["id"], "value": "SMB", "version": 0}]},
    )
    assert conflict.status_code == 409

    search = data["client"].post(
        "/custom-fields/search/companies",
        headers=_headers(data),
        json={"filters": [{"field_id": field["id"], "operator": "eq", "value": "Enterprise"}]},
    )
    assert search.status_code == 200
    assert search.json()["entity_ids"] == [str(data["company"].id)]

    report = data["client"].get(
        f"/custom-fields/reports/companies/{field['id']}", headers=_headers(data)
    )
    assert report.status_code == 200
    assert report.json()["buckets"] == [{"label": "Enterprise", "value": 1.0, "count": 1}]


def test_cross_tenant_objects_and_invalid_options_are_rejected(custom_fields_api):
    data = custom_fields_api
    field = _definition(data)
    invalid = data["client"].put(
        f"/custom-fields/values/companies/{data['company'].id}",
        headers=_headers(data, "rep"),
        json={"values": [{"field_id": field["id"], "value": "Unknown", "version": 0}]},
    )
    assert invalid.status_code == 422

    hidden = data["client"].get(
        f"/custom-fields/values/companies/{data['foreign_company'].id}",
        headers=_headers(data),
    )
    assert hidden.status_code == 404

    hidden_field = data["client"].get(
        "/custom-fields/definitions?entity_type=companies",
        headers=_headers(data, tenant="other"),
    )
    assert hidden_field.status_code == 403
