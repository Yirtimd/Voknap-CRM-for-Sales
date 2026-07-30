from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import app.main  # noqa: F401 - registers every model in shared metadata
from app.core.database import Base
from app.modules.knowledge.schemas import AskRequest
from app.modules.knowledge.service import KnowledgeService
from app.modules.sales.models import Company, Deal, Pipeline, PipelineStage


@pytest.fixture(autouse=True)
def local_embeddings(monkeypatch):
    monkeypatch.setattr("app.modules.knowledge.service.settings.embedding_provider", "local")


@pytest.fixture
def scoped_knowledge():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    tenant_id = uuid4()
    with Session(engine) as db:
        company_a = Company(tenant_id=tenant_id, name="Company A")
        company_b = Company(tenant_id=tenant_id, name="Company B")
        pipeline = Pipeline(tenant_id=tenant_id, name="Sales")
        db.add_all([company_a, company_b, pipeline])
        db.flush()
        stage = PipelineStage(tenant_id=tenant_id, pipeline_id=pipeline.id, name="Open")
        db.add(stage)
        db.flush()
        deal_a = Deal(
            tenant_id=tenant_id,
            company_id=company_a.id,
            stage_id=stage.id,
            title="Deal A",
        )
        db.add(deal_a)
        db.commit()

        service = KnowledgeService(db)
        global_document = service.create_document(
            tenant_id,
            "Global playbook",
            "pricing policy general workspace knowledge",
            visibility="global",
        )
        company_a_document = service.create_document(
            tenant_id,
            "Company A profile",
            "pricing policy company alpha knowledge",
            company_id=company_a.id,
            visibility="company",
        )
        company_b_document = service.create_document(
            tenant_id,
            "Company B profile",
            "pricing policy company beta knowledge",
            company_id=company_b.id,
            visibility="company",
        )
        deal_a_document = service.create_document(
            tenant_id,
            "Deal A proposal",
            "pricing policy deal proposal knowledge",
            company_id=company_a.id,
            deal_id=deal_a.id,
            visibility="deal",
        )

        yield {
            "service": service,
            "tenant_id": tenant_id,
            "company_a": company_a,
            "company_b": company_b,
            "deal_a": deal_a,
            "global": global_document,
            "company_a_document": company_a_document,
            "company_b_document": company_b_document,
            "deal_a_document": deal_a_document,
        }


def document_ids(results):
    return {item.document.id for item in results}


def test_global_scope_never_reads_company_documents(scoped_knowledge):
    data = scoped_knowledge
    results = data["service"].search(data["tenant_id"], "pricing policy", scope="global", limit=20)

    assert document_ids(results) == {data["global"].id}
    listed_documents = data["service"].list_documents(data["tenant_id"], scope="global")
    assert {document.id for document in listed_documents} == {data["global"].id}


def test_company_scope_is_strict_and_global_is_opt_in(scoped_knowledge):
    data = scoped_knowledge
    strict_results = data["service"].search(
        data["tenant_id"],
        "pricing policy",
        scope="company",
        company_id=data["company_a"].id,
        limit=20,
    )
    layered_results = data["service"].search(
        data["tenant_id"],
        "pricing policy",
        scope="company",
        company_id=data["company_a"].id,
        include_global=True,
        limit=20,
    )

    assert document_ids(strict_results) == {data["company_a_document"].id}
    assert document_ids(layered_results) == {data["company_a_document"].id, data["global"].id}


def test_deal_scope_reads_deal_and_base_company_only(scoped_knowledge):
    data = scoped_knowledge
    results = data["service"].search(
        data["tenant_id"],
        "pricing policy",
        scope="deal",
        company_id=data["company_a"].id,
        deal_id=data["deal_a"].id,
        limit=20,
    )

    assert document_ids(results) == {data["company_a_document"].id, data["deal_a_document"].id}


def test_document_filter_is_strict_and_context_aware(scoped_knowledge):
    data = scoped_knowledge
    results = data["service"].search(
        data["tenant_id"],
        "pricing policy",
        scope="company",
        company_id=data["company_a"].id,
        document_id=data["company_a_document"].id,
        limit=20,
    )

    assert document_ids(results) == {data["company_a_document"].id}
    with pytest.raises(ValueError, match="selected knowledge context"):
        data["service"].search(
            data["tenant_id"],
            "pricing policy",
            scope="company",
            company_id=data["company_a"].id,
            document_id=data["company_b_document"].id,
        )


def test_answer_is_audited_and_accepts_owner_feedback(scoped_knowledge):
    data = scoped_knowledge
    user_id = uuid4()

    result = data["service"].answer(
        data["tenant_id"],
        user_id,
        "pricing policy",
        scope="global",
        document_id=data["global"].id,
    )
    feedback = data["service"].save_feedback(
        data["tenant_id"],
        user_id,
        result.query.id,
        "up",
        "Источник подтверждает ответ",
    )

    assert result.query.document_id == data["global"].id
    assert result.query.retrieval_mode == "hybrid"
    assert result.query.sources_json != "[]"
    assert feedback is not None
    assert feedback.feedback_rating == "up"


def test_request_rejects_implicit_or_conflicting_scope():
    company_id = uuid4()

    with pytest.raises(ValidationError):
        AskRequest(question="pricing", company_id=company_id)
    with pytest.raises(ValidationError):
        AskRequest(question="pricing", scope="company")
    with pytest.raises(ValidationError):
        AskRequest(question="pricing", scope="global", company_id=company_id)


def test_reindex_updates_embedding_metadata(scoped_knowledge, monkeypatch):
    data = scoped_knowledge
    service = data["service"]
    monkeypatch.setattr("app.modules.knowledge.service.settings.embedding_version", "2")

    before = service.search(data["tenant_id"], "pricing policy", scope="global", limit=20)
    count = service.reindex_all(data["tenant_id"], batch_size=2)
    after = service.search(data["tenant_id"], "pricing policy", scope="global", limit=20)

    assert before == []
    assert count == 4
    assert document_ids(after) == {data["global"].id}
    assert all(chunk.embedding_version == "2" for chunk in data["global"].chunks)
    assert all(chunk.embedding_dimensions == 1536 for chunk in data["global"].chunks)
