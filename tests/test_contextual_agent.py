from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.main  # noqa: F401
from app.core.database import Base, get_db
from app.core.dependencies import CurrentTenant, get_current_tenant
from app.core.rbac import Role
from app.main import app
from app.modules.accounts.models import Membership, Tenant, User
from app.modules.knowledge.service import KnowledgeService


def test_document_chat_shares_sources_history_and_feedback(monkeypatch):
    monkeypatch.setattr("app.modules.knowledge.service.settings.embedding_provider", "local")
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    tenant = Tenant(name="Context Tenant", slug=f"context-{uuid4()}")
    user = User(
        email=f"context-{uuid4()}@example.com",
        full_name="Context Owner",
        password_hash="unused",
    )
    db.add_all([tenant, user])
    db.flush()
    db.add(Membership(tenant_id=tenant.id, user_id=user.id, role="owner"))
    db.commit()
    document = KnowledgeService(db).create_document(
        tenant.id,
        "Commercial policy",
        "Оплата производится в течение десяти рабочих дней после подписания акта.",
    )

    def override_db():
        yield db

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_tenant] = lambda: CurrentTenant(
        id=tenant.id,
        user_id=user.id,
        role=Role.OWNER,
    )
    try:
        client = TestClient(app)
        chat = client.post(
            "/ai-agent/chat",
            json={
                "message": "Когда производится оплата?",
                "context_type": "document",
                "document_id": str(document.id),
            },
        )

        assert chat.status_code == 200, chat.text
        payload = chat.json()
        assert payload["query_id"]
        assert payload["context"]["type"] == "document"
        assert payload["sources"][0]["document_id"] == str(document.id)

        history = client.get("/ai-agent/history")
        assert history.status_code == 200
        assistant = history.json()[0]
        assert assistant["query_id"] == payload["query_id"]
        assert assistant["sources"][0]["document_title"] == "Commercial policy"

        feedback = client.post(
            f"/knowledge/queries/{payload['query_id']}/feedback",
            json={"rating": "up"},
        )
        assert feedback.status_code == 200
        assert feedback.json()["rating"] == "up"
    finally:
        app.dependency_overrides.clear()
        db.close()
