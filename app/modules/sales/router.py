import json
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import CurrentTenant, get_current_tenant
from app.core.rbac import (
    Permission,
    deny_access,
    has_permission,
    require_allowed_fields,
    require_object_owner,
    require_permission,
)
from app.modules.activity.service import ActivityService
from app.modules.automation.service import AutomationEngine
from app.modules.connectors.jobs import publish_webhook_event
from app.modules.accounts.models import User
from app.modules.accounts.assignment import assign_company, assign_lead
from app.modules.knowledge.models import KnowledgeDocument
from app.modules.sales.lifecycle import add_history, commit_versioned, ensure_member, require_version
from app.modules.sales.models import (
    Company,
    CompanyFile,
    Contact,
    CustomerInsight,
    Deal,
    Lead,
    NextAction,
    Note,
    Pipeline,
    PipelineStage,
    Task,
)
from app.modules.sales.querying import apply_list_contract
from app.modules.sales.scoring import ScoringService
from app.modules.sales.stages import stage_label_ru
from app.modules.sales.schemas import (
    CompanyCreate,
    CompanyFileCreate,
    CompanyFileResponse,
    CompanyResponse,
    CompanyUpdate,
    CompanyWorkspaceResponse,
    ContactCreate,
    ContactResponse,
    CustomerInsightResponse,
    CustomerInsightUpsert,
    DealCreate,
    DealMoveRequest,
    DealResponse,
    LeadCreate,
    LeadResponse,
    NextActionCreate,
    NextActionDoneRequest,
    NextActionResponse,
    NoteCreate,
    NoteResponse,
    PipelineCreate,
    PipelineResponse,
    PipelineStageInput,
    PipelineStageResponse,
    PipelineUpdate,
    TaskCreate,
    TaskDoneRequest,
    TaskResponse,
    OwnerResponse,
)


router = APIRouter()


@router.post("/companies", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
def create_company(
    payload: CompanyCreate,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> CompanyResponse:
    restricted_fields = {"owner_id", "health_score", "client_since"}
    require_allowed_fields(tenant.role, payload.model_fields_set, restricted_fields)
    company_data = payload.model_dump()
    if company_data["country_code"] is not None:
        company_data["country_code"] = company_data["country_code"].upper()
    if tenant.role.value == "sales_rep":
        company_data["owner_id"] = tenant.user_id
    elif company_data["owner_id"] is not None:
        ensure_member(db, tenant.id, company_data["owner_id"])
    else:
        assignment = assign_company(db, tenant.id, company_data)
        company_data["owner_id"] = assignment.owner_id
        company_data["territory_id"] = assignment.territory_id
    company = Company(tenant_id=tenant.id, **company_data)
    db.add(company)
    db.flush()
    ActivityService(db).create(
        tenant_id=tenant.id,
        created_by=tenant.user_id,
        company_id=company.id,
        activity_type="SYSTEM",
        title="Company created",
        description=company.name,
        metadata={"company_id": str(company.id)},
        commit=False,
    )
    db.commit()
    db.refresh(company)
    owner = db.query(User).filter(User.id == company.owner_id).one_or_none() if company.owner_id else None
    return _company_response(company, owner, _company_source(company, db, tenant.id))


@router.get("/companies", response_model=list[CompanyResponse])
def list_companies(
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(get_current_tenant),
) -> list[Company]:
    return db.query(Company).filter(Company.tenant_id == tenant.id).order_by(Company.created_at.desc()).all()


@router.patch("/companies/{company_id}", response_model=CompanyResponse)
def update_company(
    company_id: UUID,
    payload: CompanyUpdate,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> CompanyResponse:
    company = _get_for_tenant(db, Company, tenant.id, company_id)
    require_object_owner(tenant.role, tenant.user_id, company.owner_id)
    changes = []
    update_data = payload.model_dump(exclude_unset=True)
    require_allowed_fields(
        tenant.role,
        set(update_data),
        {"owner_id", "health_score", "client_since"},
    )
    for field_name, new_value in update_data.items():
        old_value = getattr(company, field_name)
        if old_value == new_value:
            continue
        setattr(company, field_name, new_value)
        changes.append({
            "field": field_name,
            "old": _metadata_value(old_value),
            "new": _metadata_value(new_value),
        })

    if changes:
        ActivityService(db).create(
            tenant_id=tenant.id,
            created_by=tenant.user_id,
            company_id=company.id,
            activity_type="SYSTEM",
            channel="CRM",
            title="Company fields changed",
            description=", ".join(change["field"] for change in changes),
            metadata={"changes": changes},
            commit=False,
        )

    db.commit()
    db.refresh(company)
    owner = db.query(User).filter(User.id == company.owner_id).one_or_none() if company.owner_id else None
    return _company_response(company, owner, _company_source(company, db, tenant.id))


@router.get("/companies/{company_id}", response_model=CompanyWorkspaceResponse)
def company_workspace(
    company_id: UUID,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(get_current_tenant),
) -> CompanyWorkspaceResponse:
    company = _get_for_tenant(db, Company, tenant.id, company_id)
    contacts = (
        db.query(Contact)
        .filter(Contact.tenant_id == tenant.id, Contact.company_id == company.id)
        .order_by(Contact.created_at.desc())
        .all()
    )
    deals = db.query(Deal).filter(Deal.tenant_id == tenant.id, Deal.company_id == company.id).all()
    tasks = db.query(Task).filter(Task.tenant_id == tenant.id, Task.company_id == company.id).all()
    files = (
        db.query(CompanyFile)
        .filter(CompanyFile.tenant_id == tenant.id, CompanyFile.company_id == company.id)
        .order_by(CompanyFile.created_at.desc())
        .all()
    )
    knowledge_documents = (
        db.query(KnowledgeDocument)
        .filter(KnowledgeDocument.tenant_id == tenant.id, KnowledgeDocument.company_id == company.id)
        .order_by(KnowledgeDocument.created_at.desc())
        .all()
    )
    insight = (
        db.query(CustomerInsight)
        .filter(CustomerInsight.tenant_id == tenant.id, CustomerInsight.company_id == company.id)
        .one_or_none()
    )
    next_action = _resolve_company_next_action(db, tenant.id, company)
    owner = db.query(User).filter(User.id == company.owner_id).one_or_none() if company.owner_id else None
    related_activities = ActivityService(db).list(tenant_id=tenant.id, company_id=company.id, limit=80)
    author_ids = [activity.created_by for activity in related_activities if activity.created_by]
    authors = {
        user.id: user
        for user in db.query(User).filter(User.id.in_(author_ids)).all()
    } if author_ids else {}
    open_tasks = [task for task in tasks if task.done_at is None]
    total_amount = sum(float(deal.amount or 0) for deal in deals)
    activity_rows = [
        _activity_workspace_response(activity, authors.get(activity.created_by))
        for activity in related_activities
    ]
    contact_activities = [
        row for row in activity_rows
        if row["activity_type"] in {"call", "email", "meeting", "message"}
    ]
    last_contact = contact_activities[0] if contact_activities else None
    channel_summary = _channel_summary(activity_rows)
    company_source = _company_source(company, db, tenant.id)
    ai_summary = (
        f"{company.name}: контактов {len(contacts)}, сделок {len(deals)}, "
        f"открытых задач {len(open_tasks)}, пайплайн {total_amount:,.0f} руб."
    )
    ai_insights = []
    if not contacts:
        ai_insights.append("Добавить ключевых контактов компании.")
    if deals and not open_tasks:
        ai_insights.append("Создать follow-up задачу по активным сделкам.")
    if not deals:
        ai_insights.append("Создать первую сделку или связать лид с компанией.")

    return CompanyWorkspaceResponse(
        company=_company_response(company, owner, company_source),
        overview={
            "contacts_count": len(contacts),
            "deals_count": len(deals),
            "open_tasks_count": len(open_tasks),
            "pipeline_amount": total_amount,
            "last_contact_at": last_contact["created_at"] if last_contact else None,
            "last_contact_person": last_contact["author_name"] if last_contact else None,
            "channel_summary": channel_summary,
        },
        health=_health_response(insight, contacts, deals),
        next_action=_next_action_dict(next_action) if next_action else None,
        contacts=[_contact_response(contact) for contact in contacts],
        deals=[_deal_response(deal) for deal in deals],
        tasks=tasks,
        activities=activity_rows,
        files=[_file_response(file) for file in files],
        knowledge_documents=[_knowledge_document_response(document) for document in knowledge_documents],
        ai_summary=ai_summary,
        ai_insights=ai_insights,
    )


@router.get("/companies/{company_id}/files", response_model=list[CompanyFileResponse])
def list_company_files(
    company_id: UUID,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(get_current_tenant),
) -> list[CompanyFileResponse]:
    _get_for_tenant(db, Company, tenant.id, company_id)
    files = (
        db.query(CompanyFile)
        .filter(CompanyFile.tenant_id == tenant.id, CompanyFile.company_id == company_id)
        .order_by(CompanyFile.created_at.desc())
        .all()
    )
    return [_company_file_response(file) for file in files]


@router.post("/companies/{company_id}/files", response_model=CompanyFileResponse, status_code=status.HTTP_201_CREATED)
def create_company_file(
    company_id: UUID,
    payload: CompanyFileCreate,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> CompanyFileResponse:
    company = _get_for_tenant(db, Company, tenant.id, company_id)
    require_object_owner(tenant.role, tenant.user_id, company.owner_id)
    if payload.company_id != company_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="company_id does not match path")
    if payload.deal_id is not None:
        deal = _get_for_tenant(db, Deal, tenant.id, payload.deal_id)
        if deal.company_id != company_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Deal belongs to another company")
    if payload.contact_id is not None:
        contact = _get_for_tenant(db, Contact, tenant.id, payload.contact_id)
        if contact.company_id != company_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contact belongs to another company")

    file = CompanyFile(
        tenant_id=tenant.id,
        uploaded_by_id=tenant.user_id,
        **payload.model_dump(),
    )
    db.add(file)
    db.flush()
    ActivityService(db).create(
        tenant_id=tenant.id,
        created_by=tenant.user_id,
        company_id=company_id,
        deal_id=payload.deal_id,
        contact_id=payload.contact_id,
        activity_type="FILE_UPLOADED",
        channel="File",
        title="File uploaded",
        description=payload.name,
        metadata={"file_id": str(file.id), "file_type": payload.file_type},
        commit=False,
    )
    db.commit()
    db.refresh(file)
    return _company_file_response(file)


@router.get("/companies/{company_id}/insight", response_model=CustomerInsightResponse)
def get_customer_insight(
    company_id: UUID,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(get_current_tenant),
) -> CustomerInsightResponse:
    _get_for_tenant(db, Company, tenant.id, company_id)
    insight = (
        db.query(CustomerInsight)
        .filter(CustomerInsight.tenant_id == tenant.id, CustomerInsight.company_id == company_id)
        .one_or_none()
    )
    if insight is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="CustomerInsight not found")
    return _customer_insight_response(insight)


@router.put("/companies/{company_id}/insight", response_model=CustomerInsightResponse)
def upsert_customer_insight(
    company_id: UUID,
    payload: CustomerInsightUpsert,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.SALES_MANAGE)),
) -> CustomerInsightResponse:
    _get_for_tenant(db, Company, tenant.id, company_id)
    insight = (
        db.query(CustomerInsight)
        .filter(CustomerInsight.tenant_id == tenant.id, CustomerInsight.company_id == company_id)
        .one_or_none()
    )
    if insight is None:
        insight = CustomerInsight(tenant_id=tenant.id, company_id=company_id)
        db.add(insight)

    insight.health_score = payload.health_score
    insight.health_label = payload.health_label
    insight.health_trend = payload.health_trend
    insight.risk_level = payload.risk_level
    insight.success_chance = payload.success_chance
    insight.success_chance_delta = payload.success_chance_delta
    insight.ai_recommendations_json = json.dumps(payload.ai_recommendations, ensure_ascii=False)
    insight.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(insight)
    return _customer_insight_response(insight)


@router.post("/contacts", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
def create_contact(
    payload: ContactCreate,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> Contact:
    company = _get_for_tenant(db, Company, tenant.id, payload.company_id)
    require_object_owner(tenant.role, tenant.user_id, company.owner_id)
    require_allowed_fields(tenant.role, payload.model_fields_set, {"owner_id"})
    contact_data = payload.model_dump()
    if tenant.role.value == "sales_rep":
        contact_data["owner_id"] = tenant.user_id
    elif contact_data["owner_id"] is not None:
        ensure_member(db, tenant.id, contact_data["owner_id"])
    contact = Contact(tenant_id=tenant.id, **contact_data)
    db.add(contact)
    db.flush()
    ActivityService(db).create(
        tenant_id=tenant.id,
        created_by=tenant.user_id,
        company_id=contact.company_id,
        contact_id=contact.id,
        activity_type="SYSTEM",
        title="Contact created",
        description=contact.name,
        metadata={"contact_id": str(contact.id)},
        commit=False,
    )
    db.commit()
    db.refresh(contact)
    return contact


@router.get("/contacts", response_model=list[ContactResponse])
def list_contacts(
    response: Response,
    search: str | None = None,
    company_id: UUID | None = None,
    owner_id: UUID | None = None,
    include_archived: bool = False,
    include_deleted: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    sort: str = "created_at",
    order: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(get_current_tenant),
) -> list[Contact]:
    _require_deleted_access(tenant, include_deleted)
    return apply_list_contract(
        db.query(Contact).filter(Contact.tenant_id == tenant.id),
        Contact,
        response,
        search=search,
        search_fields=("name", "email", "phone", "company_name", "role"),
        filters={"company_id": company_id, "owner_id": owner_id},
        include_archived=include_archived,
        include_deleted=include_deleted,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
        sortable_fields={"name", "created_at", "updated_at"},
    )


@router.post("/leads", response_model=LeadResponse, status_code=status.HTTP_201_CREATED)
def create_lead(
    payload: LeadCreate,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> Lead:
    company = _get_for_tenant(db, Company, tenant.id, payload.company_id)
    require_object_owner(tenant.role, tenant.user_id, company.owner_id)
    if payload.contact_id is not None:
        contact = _get_for_tenant(db, Contact, tenant.id, payload.contact_id)
        if contact.company_id != payload.company_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contact belongs to another company")

    require_allowed_fields(tenant.role, payload.model_fields_set, {"owner_id"})
    lead_data = payload.model_dump()
    if tenant.role.value == "sales_rep":
        lead_data["owner_id"] = tenant.user_id
    elif lead_data["owner_id"] is not None:
        ensure_member(db, tenant.id, lead_data["owner_id"])
    else:
        assignment = assign_lead(db, tenant.id, lead_data, company)
        lead_data["owner_id"] = assignment.owner_id
        lead_data["queue_id"] = assignment.queue_id
    lead = Lead(tenant_id=tenant.id, **lead_data)
    db.add(lead)
    db.flush()
    ActivityService(db).create(
        tenant_id=tenant.id,
        created_by=tenant.user_id,
        company_id=lead.company_id,
        contact_id=lead.contact_id,
        activity_type="SYSTEM",
        title="Lead created",
        description=lead.title,
        metadata={"lead_id": str(lead.id), "source": lead.source},
        commit=False,
    )
    ScoringService(db).recalculate_lead(
        lead,
        actor_id=tenant.user_id,
        reason="lead_created",
    )
    AutomationEngine(db).emit(
        tenant_id=tenant.id,
        trigger_type="lead.created",
        entity_type="lead",
        entity_id=lead.id,
        event_key=f"lead.created:{lead.id}",
        context={
            "source": lead.source,
            "status": lead.status,
            "owner_id": str(lead.owner_id) if lead.owner_id else None,
            "company_id": str(lead.company_id),
            "title": lead.title,
            "score": lead.score,
            "score_grade": lead.score_grade,
        },
        actor_id=tenant.user_id,
    )
    publish_webhook_event(
        db,
        tenant_id=tenant.id,
        event_type="lead.created",
        data={
            "id": str(lead.id),
            "company_id": str(lead.company_id),
            "title": lead.title,
            "source": lead.source,
            "status": lead.status,
        },
        actor_id=tenant.user_id,
    )
    db.commit()
    db.refresh(lead)
    return lead


@router.get("/leads", response_model=list[LeadResponse])
def list_leads(
    response: Response,
    search: str | None = None,
    company_id: UUID | None = None,
    contact_id: UUID | None = None,
    owner_id: UUID | None = None,
    status_filter: str | None = None,
    source: str | None = None,
    include_archived: bool = False,
    include_deleted: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    sort: str = "created_at",
    order: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(get_current_tenant),
) -> list[Lead]:
    _require_deleted_access(tenant, include_deleted)
    return apply_list_contract(
        db.query(Lead).filter(Lead.tenant_id == tenant.id),
        Lead,
        response,
        search=search,
        search_fields=("title", "source", "status", "disqualification_reason"),
        filters={
            "company_id": company_id,
            "contact_id": contact_id,
            "owner_id": owner_id,
            "status": status_filter,
            "source": source,
        },
        include_archived=include_archived,
        include_deleted=include_deleted,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
        sortable_fields={"title", "status", "created_at", "updated_at", "qualified_at"},
    )


@router.get("/leads/{lead_id}", response_model=LeadResponse)
def get_lead(
    lead_id: UUID,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(get_current_tenant),
) -> Lead:
    lead = _get_for_tenant(db, Lead, tenant.id, lead_id)
    if lead.deleted_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Lead not found")
    return lead


@router.post("/pipelines", response_model=PipelineResponse, status_code=status.HTTP_201_CREATED)
def create_pipeline(
    payload: PipelineCreate,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.SALES_MANAGE)),
) -> Pipeline:
    if payload.is_default:
        db.query(Pipeline).filter(Pipeline.tenant_id == tenant.id).update(
            {Pipeline.is_default: False}, synchronize_session=False
        )
    pipeline = Pipeline(
        tenant_id=tenant.id,
        name=payload.name,
        description=payload.description,
        is_default=payload.is_default,
    )
    db.add(pipeline)
    db.flush()

    for index, stage_value in enumerate(payload.stages):
        stage = _pipeline_stage_input(stage_value, index, len(payload.stages))
        db.add(
            PipelineStage(
                tenant_id=tenant.id,
                pipeline_id=pipeline.id,
                name=stage.name,
                code=stage.code or _stage_code(stage.name, index),
                sort_order=index,
                probability=stage.probability,
                stage_type=stage.stage_type,
                required_fields_json=json.dumps(stage.required_fields),
            )
        )

    db.commit()
    db.refresh(pipeline)
    return _pipeline_response(pipeline)


@router.get("/pipelines", response_model=list[PipelineResponse])
def list_pipelines(
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(get_current_tenant),
) -> list[PipelineResponse]:
    rows = (
        db.query(Pipeline)
        .filter(Pipeline.tenant_id == tenant.id)
        .order_by(Pipeline.is_default.desc(), Pipeline.created_at.desc())
        .all()
    )
    return [_pipeline_response(row) for row in rows]


@router.patch("/pipelines/{pipeline_id}", response_model=PipelineResponse)
def update_pipeline(
    pipeline_id: UUID,
    payload: PipelineUpdate,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.SALES_MANAGE)),
) -> PipelineResponse:
    pipeline = _get_for_tenant(db, Pipeline, tenant.id, pipeline_id)
    require_version(pipeline, payload.version)
    if payload.is_active is False:
        active_deal = (
            db.query(Deal.id)
            .join(PipelineStage, Deal.stage_id == PipelineStage.id)
            .filter(
                Deal.tenant_id == tenant.id,
                PipelineStage.pipeline_id == pipeline.id,
                Deal.status == "open",
                Deal.deleted_at.is_(None),
            )
            .first()
        )
        if active_deal:
            raise HTTPException(status_code=409, detail="Pipeline has open deals")
    if payload.is_default:
        db.query(Pipeline).filter(
            Pipeline.tenant_id == tenant.id, Pipeline.id != pipeline.id
        ).update({Pipeline.is_default: False}, synchronize_session=False)
    for field_name in ("name", "description", "is_active", "is_default"):
        value = getattr(payload, field_name)
        if value is not None:
            setattr(pipeline, field_name, value)
    if payload.stages is not None:
        _replace_pipeline_stages(db, tenant.id, pipeline, payload.stages)
    commit_versioned(db, pipeline)
    return _pipeline_response(pipeline)


@router.post("/deals", response_model=DealResponse, status_code=status.HTTP_201_CREATED)
def create_deal(
    payload: DealCreate,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> Deal:
    company = _get_for_tenant(db, Company, tenant.id, payload.company_id)
    require_object_owner(tenant.role, tenant.user_id, company.owner_id)
    require_allowed_fields(
        tenant.role,
        payload.model_fields_set,
        {"owner_id", "probability", "risk_level", "forecast_category"},
    )
    stage = _get_for_tenant(db, PipelineStage, tenant.id, payload.stage_id)
    if not stage.is_active or not stage.pipeline.is_active:
        raise HTTPException(status_code=422, detail="Deal stage is inactive")
    if payload.lead_id is not None:
        lead = _get_for_tenant(db, Lead, tenant.id, payload.lead_id)
        if lead.company_id != payload.company_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Lead belongs to another company")

    deal_data = payload.model_dump()
    if deal_data["probability"] is None:
        deal_data["probability"] = stage.probability
    if stage.stage_type in {"won", "lost"}:
        deal_data["status"] = stage.stage_type
    if tenant.role.value == "sales_rep":
        deal_data["owner_id"] = tenant.user_id
    deal = Deal(tenant_id=tenant.id, **deal_data)
    db.add(deal)
    db.flush()
    ActivityService(db).create(
        tenant_id=tenant.id,
        created_by=tenant.user_id,
        company_id=deal.company_id,
        deal_id=deal.id,
        activity_type="SYSTEM",
        title="Deal created",
        description=deal.title,
        metadata={"deal_id": str(deal.id), "amount": float(deal.amount or 0)},
        commit=False,
    )
    ScoringService(db).recalculate_deal(
        deal,
        actor_id=tenant.user_id,
        reason="deal_created",
    )
    automation = AutomationEngine(db)
    automation.emit(
        tenant_id=tenant.id,
        trigger_type="deal.created",
        entity_type="deal",
        entity_id=deal.id,
        event_key=f"deal.created:{deal.id}",
        context=automation.deal_context(deal),
        actor_id=tenant.user_id,
    )
    db.commit()
    db.refresh(deal)
    return deal


@router.get("/deals", response_model=list[DealResponse])
def list_deals(
    response: Response,
    search: str | None = None,
    company_id: UUID | None = None,
    lead_id: UUID | None = None,
    stage_id: UUID | None = None,
    owner_id: UUID | None = None,
    status_filter: str | None = None,
    risk_level: str | None = None,
    include_archived: bool = False,
    include_deleted: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    sort: str = "created_at",
    order: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(get_current_tenant),
) -> list[Deal]:
    _require_deleted_access(tenant, include_deleted)
    return apply_list_contract(
        db.query(Deal).filter(Deal.tenant_id == tenant.id),
        Deal,
        response,
        search=search,
        search_fields=("title", "status", "risk_level", "forecast_category", "next_step"),
        filters={
            "company_id": company_id,
            "lead_id": lead_id,
            "stage_id": stage_id,
            "owner_id": owner_id,
            "status": status_filter,
            "risk_level": risk_level,
        },
        include_archived=include_archived,
        include_deleted=include_deleted,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
        sortable_fields={"title", "amount", "status", "created_at", "updated_at", "expected_close_date"},
    )


@router.post("/next-actions", response_model=NextActionResponse, status_code=status.HTTP_201_CREATED)
def create_next_action(
    payload: NextActionCreate,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> NextAction:
    company = _get_for_tenant(db, Company, tenant.id, payload.company_id)
    require_object_owner(tenant.role, tenant.user_id, company.owner_id)
    if payload.assigned_to_id not in {None, tenant.user_id}:
        require_allowed_fields(tenant.role, {"assigned_to_id"}, {"assigned_to_id"})
    if payload.deal_id is not None:
        deal = _get_for_tenant(db, Deal, tenant.id, payload.deal_id)
        if deal.company_id != payload.company_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Deal belongs to another company")
    if payload.contact_id is not None:
        contact = _get_for_tenant(db, Contact, tenant.id, payload.contact_id)
        if contact.company_id != payload.company_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Contact belongs to another company")

    next_action = NextAction(
        tenant_id=tenant.id,
        assigned_to_id=payload.assigned_to_id or tenant.user_id,
        **payload.model_dump(exclude={"assigned_to_id"}),
    )
    db.add(next_action)
    db.flush()

    company.next_action_id = next_action.id
    if next_action.deal_id:
        deal = _get_for_tenant(db, Deal, tenant.id, next_action.deal_id)
        deal.next_action_id = next_action.id
        deal.next_step = next_action.title

    ActivityService(db).create(
        tenant_id=tenant.id,
        created_by=tenant.user_id,
        company_id=next_action.company_id,
        deal_id=next_action.deal_id,
        contact_id=next_action.contact_id,
        activity_type="AI_ACTION" if next_action.source == "ai" else "TASK",
        title="Next action created",
        description=next_action.title,
        metadata={"next_action_id": str(next_action.id), "priority": next_action.priority},
        commit=False,
    )
    if next_action.deal_id:
        ScoringService(db).recalculate_deal(
            deal,
            actor_id=tenant.user_id,
            reason="next_action_created",
        )
    db.commit()
    db.refresh(next_action)
    return next_action


@router.get("/next-actions", response_model=list[NextActionResponse])
def list_next_actions(
    company_id: UUID | None = None,
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(get_current_tenant),
) -> list[NextAction]:
    query = db.query(NextAction).filter(NextAction.tenant_id == tenant.id)
    if company_id is not None:
        query = query.filter(NextAction.company_id == company_id)
    if status_filter is not None:
        query = query.filter(NextAction.status == status_filter)
    return query.order_by(NextAction.created_at.desc()).all()


@router.patch("/next-actions/{next_action_id}/done", response_model=NextActionResponse)
def set_next_action_done(
    next_action_id: UUID,
    payload: NextActionDoneRequest,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> NextAction:
    next_action = _get_for_tenant(db, NextAction, tenant.id, next_action_id)
    require_object_owner(tenant.role, tenant.user_id, next_action.assigned_to_id)
    next_action.status = "done" if payload.is_done else "open"
    next_action.completed_at = datetime.now(timezone.utc) if payload.is_done else None
    company = _get_for_tenant(db, Company, tenant.id, next_action.company_id)
    deal = (
        _get_for_tenant(db, Deal, tenant.id, next_action.deal_id)
        if next_action.deal_id
        else None
    )
    if payload.is_done:
        if company.next_action_id == next_action.id:
            company.next_action_id = None
        if deal and deal.next_action_id == next_action.id:
            deal.next_action_id = None
    else:
        company.next_action_id = next_action.id
        if deal:
            deal.next_action_id = next_action.id
            deal.next_step = next_action.title
    ActivityService(db).create(
        tenant_id=tenant.id,
        created_by=tenant.user_id,
        company_id=next_action.company_id,
        deal_id=next_action.deal_id,
        contact_id=next_action.contact_id,
        activity_type="TASK",
        title="Next action completed" if payload.is_done else "Next action reopened",
        description=next_action.title,
        metadata={"next_action_id": str(next_action.id), "done": payload.is_done},
        commit=False,
    )
    if deal:
        ScoringService(db).recalculate_deal(
            deal,
            actor_id=tenant.user_id,
            reason="next_action_completed" if payload.is_done else "next_action_reopened",
        )
    db.commit()
    db.refresh(next_action)
    return next_action


@router.patch("/deals/{deal_id}/move", response_model=DealResponse)
def move_deal(
    deal_id: UUID,
    payload: DealMoveRequest,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> Deal:
    deal = _get_for_tenant(db, Deal, tenant.id, deal_id)
    require_object_owner(tenant.role, tenant.user_id, deal.owner_id)
    require_version(deal, payload.version)
    old_stage_id = deal.stage_id
    new_stage = _get_for_tenant(db, PipelineStage, tenant.id, payload.stage_id)
    if not new_stage.is_active or not new_stage.pipeline.is_active:
        raise HTTPException(status_code=422, detail="Deal stage is inactive")
    _require_stage_fields(deal, new_stage)

    deal.stage_id = payload.stage_id
    deal.probability = new_stage.probability
    if new_stage.stage_type in {"won", "lost"}:
        deal.status = new_stage.stage_type
    add_history(
        db,
        tenant,
        "deals",
        deal.id,
        "stage_id",
        old_stage_id,
        payload.stage_id,
        deal.version + 1,
    )
    ActivityService(db).create(
        tenant_id=tenant.id,
        created_by=tenant.user_id,
        company_id=deal.company_id,
        deal_id=deal.id,
        activity_type="DEAL_STAGE_CHANGED",
        title="Этап сделки изменён",
        description=f"{deal.title}: новый этап — {stage_label_ru(new_stage.name)}",
        metadata={"old_stage_id": str(old_stage_id), "new_stage_id": str(payload.stage_id)},
        commit=False,
    )
    ScoringService(db).recalculate_deal(
        deal,
        actor_id=tenant.user_id,
        reason="stage_changed",
    )
    automation = AutomationEngine(db)
    context = automation.deal_context(deal)
    context["old_stage_id"] = str(old_stage_id)
    automation.emit(
        tenant_id=tenant.id,
        trigger_type="deal.stage_changed",
        entity_type="deal",
        entity_id=deal.id,
        event_key=f"deal.stage_changed:{deal.id}:{deal.version + 1}",
        context=context,
        actor_id=tenant.user_id,
    )
    commit_versioned(db, deal)
    return deal


@router.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(
    payload: TaskCreate,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> Task:
    company = _get_for_tenant(db, Company, tenant.id, payload.company_id)
    require_object_owner(tenant.role, tenant.user_id, company.owner_id)
    if payload.deal_id is not None:
        deal = _get_for_tenant(db, Deal, tenant.id, payload.deal_id)
        if deal.company_id != payload.company_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Deal belongs to another company")

    require_allowed_fields(tenant.role, payload.model_fields_set, {"assigned_to_id"})
    task_data = payload.model_dump(exclude={"assigned_to_id"})
    assigned_to_id = payload.assigned_to_id or tenant.user_id
    if assigned_to_id != tenant.user_id:
        ensure_member(db, tenant.id, assigned_to_id)
    task = Task(
        tenant_id=tenant.id,
        assigned_to_id=assigned_to_id,
        **task_data,
    )
    db.add(task)
    db.flush()
    ActivityService(db).create(
        tenant_id=tenant.id,
        created_by=tenant.user_id,
        company_id=task.company_id,
        deal_id=task.deal_id,
        activity_type="TASK",
        title="Task created",
        description=task.title,
        metadata={"task_id": str(task.id)},
        commit=False,
    )
    if task.deal_id:
        ScoringService(db).recalculate_deal(
            deal,
            actor_id=tenant.user_id,
            reason="task_created",
        )
    db.commit()
    db.refresh(task)
    return task


@router.get("/tasks", response_model=list[TaskResponse])
def list_tasks(
    response: Response,
    search: str | None = None,
    company_id: UUID | None = None,
    deal_id: UUID | None = None,
    assigned_to_id: UUID | None = None,
    status_filter: str | None = None,
    priority: str | None = None,
    include_archived: bool = False,
    include_deleted: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    sort: str = "created_at",
    order: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(get_current_tenant),
) -> list[Task]:
    _require_deleted_access(tenant, include_deleted)
    return apply_list_contract(
        db.query(Task).filter(Task.tenant_id == tenant.id),
        Task,
        response,
        search=search,
        search_fields=("title", "description", "status", "priority"),
        filters={
            "company_id": company_id,
            "deal_id": deal_id,
            "assigned_to_id": assigned_to_id,
            "status": status_filter,
            "priority": priority,
        },
        include_archived=include_archived,
        include_deleted=include_deleted,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
        sortable_fields={"title", "status", "priority", "due_at", "created_at", "updated_at"},
    )


@router.patch("/tasks/{task_id}/done", response_model=TaskResponse)
def set_task_done(
    task_id: UUID,
    payload: TaskDoneRequest,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> Task:
    task = _get_for_tenant(db, Task, tenant.id, task_id)
    require_object_owner(tenant.role, tenant.user_id, task.assigned_to_id)
    require_version(task, payload.version)
    new_done_at = datetime.now(timezone.utc) if payload.is_done else None
    new_status = "done" if payload.is_done else "open"
    if task.status != new_status:
        add_history(
            db,
            tenant,
            "tasks",
            task.id,
            "status",
            task.status,
            new_status,
            task.version + 1,
        )
    if task.done_at != new_done_at:
        add_history(
            db,
            tenant,
            "tasks",
            task.id,
            "done_at",
            task.done_at,
            new_done_at,
            task.version + 1,
        )
    task.done_at = new_done_at
    task.status = new_status
    ActivityService(db).create(
        tenant_id=tenant.id,
        created_by=tenant.user_id,
        company_id=task.company_id,
        deal_id=task.deal_id,
        activity_type="TASK",
        title="Task completed" if payload.is_done else "Task reopened",
        description=task.title,
        metadata={"task_id": str(task.id), "done": payload.is_done},
        commit=False,
    )
    if task.deal_id:
        deal = _get_for_tenant(db, Deal, tenant.id, task.deal_id)
        ScoringService(db).recalculate_deal(
            deal,
            actor_id=tenant.user_id,
            reason="task_completed" if payload.is_done else "task_reopened",
        )
    commit_versioned(db, task)
    return task


@router.post("/notes", response_model=NoteResponse, status_code=status.HTTP_201_CREATED)
def create_note(
    payload: NoteCreate,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> Note:
    company = _get_for_tenant(db, Company, tenant.id, payload.company_id)
    require_object_owner(tenant.role, tenant.user_id, company.owner_id)
    if payload.lead_id is not None:
        lead = _get_for_tenant(db, Lead, tenant.id, payload.lead_id)
        if lead.company_id != payload.company_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Lead belongs to another company")
    if payload.deal_id is not None:
        deal = _get_for_tenant(db, Deal, tenant.id, payload.deal_id)
        if deal.company_id != payload.company_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Deal belongs to another company")

    note = Note(tenant_id=tenant.id, author_id=tenant.user_id, **payload.model_dump())
    db.add(note)
    db.flush()
    ActivityService(db).create(
        tenant_id=tenant.id,
        created_by=tenant.user_id,
        company_id=note.company_id,
        deal_id=note.deal_id,
        activity_type="NOTE",
        title="Note added",
        description=note.text,
        metadata={"note_id": str(note.id), "lead_id": str(note.lead_id) if note.lead_id else None},
        commit=False,
    )
    db.commit()
    db.refresh(note)
    return note


@router.get("/notes", response_model=list[NoteResponse])
def list_notes(
    response: Response,
    search: str | None = None,
    company_id: UUID | None = None,
    lead_id: UUID | None = None,
    deal_id: UUID | None = None,
    author_id: UUID | None = None,
    include_archived: bool = False,
    include_deleted: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=100, ge=1, le=200),
    sort: str = "created_at",
    order: Literal["asc", "desc"] = "desc",
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(get_current_tenant),
) -> list[Note]:
    _require_deleted_access(tenant, include_deleted)
    return apply_list_contract(
        db.query(Note).filter(Note.tenant_id == tenant.id),
        Note,
        response,
        search=search,
        search_fields=("text",),
        filters={
            "company_id": company_id,
            "lead_id": lead_id,
            "deal_id": deal_id,
            "author_id": author_id,
        },
        include_archived=include_archived,
        include_deleted=include_deleted,
        page=page,
        page_size=page_size,
        sort=sort,
        order=order,
        sortable_fields={"created_at", "updated_at"},
    )


def _company_response(company: Company, owner: User | None, source: str | None) -> CompanyResponse:
    return CompanyResponse(
        id=company.id,
        name=company.name,
        website=company.website,
        industry=company.industry,
        country_code=company.country_code,
        region=company.region,
        description=company.description,
        status=company.status,
        status_label=_status_label(company.status),
        company_type=company.company_type or company.industry,
        health_score=company.health_score,
        client_since=company.client_since or company.created_at,
        source=source,
        owner=_owner_response(owner),
        territory_id=company.territory_id,
        next_action_id=company.next_action_id,
        created_at=company.created_at,
    )


def _owner_response(owner: User | None) -> OwnerResponse | None:
    if owner is None:
        return None
    return OwnerResponse(
        id=owner.id,
        name=owner.full_name,
        avatar_url=owner.avatar_url,
        initials=_initials(owner.full_name),
    )


def _contact_response(contact: Contact) -> ContactResponse:
    return ContactResponse(
        id=contact.id,
        company_id=contact.company_id,
        name=contact.name,
        phone=contact.phone,
        email=contact.email,
        company_name=contact.company_name,
        role=contact.role,
        owner_id=contact.owner_id,
        actions={
            "call": bool(contact.can_call and contact.phone),
            "email": bool(contact.can_email and contact.email),
            "more": bool(contact.can_open_more),
        },
        is_archived=contact.is_archived,
        deleted_at=contact.deleted_at,
        version=contact.version,
        created_at=contact.created_at,
        updated_at=contact.updated_at,
    )


def _deal_response(deal: Deal) -> DealResponse:
    return DealResponse(
        id=deal.id,
        company_id=deal.company_id,
        title=deal.title,
        amount=float(deal.amount) if deal.amount is not None else None,
        discount_percent=(
            float(deal.discount_percent) if deal.discount_percent is not None else None
        ),
        status=deal.status,
        lead_id=deal.lead_id,
        stage_id=deal.stage_id,
        probability=deal.probability,
        expected_close_date=deal.expected_close_date,
        expected_next_event=deal.expected_next_event,
        next_step=deal.next_step,
        risk_level=deal.risk_level,
        forecast_category=deal.forecast_category,
        opportunity_score=deal.opportunity_score,
        score_grade=deal.score_grade,
        score_factors=deal.score_factors,
        forecast_probability=deal.forecast_probability,
        probability_source=deal.probability_source,
        score_model_version=deal.score_model_version,
        score_updated_at=deal.score_updated_at,
        owner_id=deal.owner_id,
        next_action_id=deal.next_action_id,
        age_days=_age_days(deal.created_at),
        is_archived=deal.is_archived,
        deleted_at=deal.deleted_at,
        version=deal.version,
        created_at=deal.created_at,
        updated_at=deal.updated_at,
    )


def _next_action_dict(next_action: NextAction) -> dict:
    return {
        "id": str(next_action.id),
        "company_id": str(next_action.company_id),
        "deal_id": str(next_action.deal_id) if next_action.deal_id else None,
        "contact_id": str(next_action.contact_id) if next_action.contact_id else None,
        "assigned_to_id": str(next_action.assigned_to_id) if next_action.assigned_to_id else None,
        "title": next_action.title,
        "description": next_action.description,
        "source": next_action.source,
        "status": next_action.status,
        "priority": next_action.priority,
        "due_at": next_action.due_at.isoformat() if next_action.due_at else None,
        "completed_at": next_action.completed_at.isoformat() if next_action.completed_at else None,
        "created_at": next_action.created_at.isoformat(),
    }


def _resolve_company_next_action(db: Session, tenant_id: UUID, company: Company) -> NextAction | None:
    if company.next_action_id:
        action = (
            db.query(NextAction)
            .filter(
                NextAction.id == company.next_action_id,
                NextAction.tenant_id == tenant_id,
                NextAction.status == "open",
            )
            .one_or_none()
        )
        if action is not None:
            return action
    return (
        db.query(NextAction)
        .filter(
            NextAction.tenant_id == tenant_id,
            NextAction.company_id == company.id,
            NextAction.status == "open",
        )
        .order_by(NextAction.due_at.asc().nullslast(), NextAction.created_at.desc())
        .first()
    )


def _activity_workspace_response(activity, author: User | None) -> dict:
    activity_type = _normalize_activity_type(activity.type, activity.channel)
    return {
        "id": str(activity.id),
        "type": activity.type,
        "activity_type": activity_type,
        "activity_icon": _activity_icon(activity_type),
        "channel": activity.channel or _channel_from_type(activity_type),
        "title": activity.title,
        "description": activity.description,
        "author_name": author.full_name if author else None,
        "created_at": activity.created_at.isoformat(),
        "metadata": json.loads(activity.metadata_json or "{}"),
    }


def _age_days(value: datetime) -> int:
    created_at = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return max(0, (datetime.now(timezone.utc) - created_at).days)


def _file_response(file: CompanyFile) -> dict:
    return {
        "id": str(file.id),
        "name": file.name,
        "file_type": file.file_type,
        "mime_type": file.mime_type,
        "file_size": file.file_size,
        "uploaded_at": file.created_at.isoformat(),
        "download_url": file.download_url or f"/files/{file.id}/download",
    }


def _knowledge_document_response(document: KnowledgeDocument) -> dict:
    return {
        "id": str(document.id),
        "title": document.title,
        "source_type": document.source_type,
        "visibility": document.visibility,
        "company_id": str(document.company_id) if document.company_id else None,
        "deal_id": str(document.deal_id) if document.deal_id else None,
        "file_id": str(document.file_id) if document.file_id else None,
        "created_at": document.created_at.isoformat(),
        "chunks_count": len(document.chunks),
        "download_url": f"/knowledge/documents/{document.id}/download" if document.file_id else None,
        "extraction_method": document.extraction_method,
        "source_pages": document.source_pages,
    }


def _company_file_response(file: CompanyFile) -> CompanyFileResponse:
    return CompanyFileResponse(
        id=file.id,
        company_id=file.company_id,
        deal_id=file.deal_id,
        contact_id=file.contact_id,
        activity_id=file.activity_id,
        uploaded_by_id=file.uploaded_by_id,
        name=file.name,
        file_type=file.file_type,
        mime_type=file.mime_type,
        file_size=file.file_size,
        storage_key=file.storage_key,
        download_url=file.download_url or f"/sales/files/{file.id}/download",
        created_at=file.created_at,
    )


def _customer_insight_response(insight: CustomerInsight) -> CustomerInsightResponse:
    return CustomerInsightResponse(
        id=insight.id,
        company_id=insight.company_id,
        health_score=insight.health_score,
        health_label=insight.health_label,
        health_trend=insight.health_trend,
        risk_level=insight.risk_level,
        success_chance=insight.success_chance,
        success_chance_delta=insight.success_chance_delta,
        ai_recommendations=json.loads(insight.ai_recommendations_json or "[]"),
        updated_at=insight.updated_at,
    )


def _health_response(insight: CustomerInsight | None, contacts: list[Contact], deals: list[Deal]) -> dict:
    fallback_score = min(98, 70 + len(contacts) * 4 + len(deals) * 6)
    if insight is None:
        return {
            "score": fallback_score,
            "label": "Хороший" if fallback_score >= 70 else "Средний",
            "trend": "up",
            "risk_level": None,
            "success_chance": None,
            "success_chance_delta": None,
            "ai_recommendations": [],
        }
    return {
        "score": insight.health_score if insight.health_score is not None else fallback_score,
        "label": insight.health_label,
        "trend": insight.health_trend,
        "risk_level": insight.risk_level,
        "success_chance": insight.success_chance,
        "success_chance_delta": insight.success_chance_delta,
        "ai_recommendations": json.loads(insight.ai_recommendations_json or "[]"),
    }


def _company_source(company: Company, db: Session, tenant_id: UUID) -> str | None:
    lead = (
        db.query(Lead)
        .filter(Lead.tenant_id == tenant_id, Lead.company_id == company.id, Lead.source.isnot(None))
        .order_by(Lead.created_at.asc())
        .first()
    )
    return lead.source if lead else None


def _metadata_value(value) -> str | int | float | bool | None:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _normalize_activity_type(activity_type: str, channel: str | None = None) -> str:
    value = (channel or activity_type or "").lower()
    if "call" in value or "phone" in value:
        return "call"
    if "email" in value or "mail" in value:
        return "email"
    if "meeting" in value or "meet" in value:
        return "meeting"
    if "message" in value or "comment" in value or "note" in value:
        return "message"
    if "task" in value:
        return "task"
    if "deal" in value:
        return "deal"
    return "system"


def _activity_icon(activity_type: str) -> str:
    return {
        "call": "phone",
        "email": "mail",
        "meeting": "calendar",
        "message": "message",
        "task": "task",
        "deal": "check",
    }.get(activity_type, "building")


def _channel_from_type(activity_type: str) -> str | None:
    return {
        "call": "Call",
        "email": "Email",
        "meeting": "Meeting",
        "message": "Message",
    }.get(activity_type)


def _channel_summary(activities: list[dict]) -> str | None:
    channels = []
    for activity in activities:
        channel = activity.get("channel")
        if channel and channel not in channels:
            channels.append(channel)
    return ", ".join(channels) if channels else None


def _status_label(status_value: str) -> str:
    return {
        "active": "Активный",
        "inactive": "Неактивный",
        "archived": "Архив",
    }.get(status_value, status_value)


def _pipeline_stage_input(
    value: str | PipelineStageInput,
    index: int,
    total: int,
) -> PipelineStageInput:
    if isinstance(value, PipelineStageInput):
        return value
    stage_type = "won" if index == total - 1 else "open"
    probability = 100 if stage_type == "won" else round(index * 100 / max(total, 1))
    return PipelineStageInput(
        name=value,
        code=f"stage_{index + 1}",
        probability=probability,
        stage_type=stage_type,
    )


def _stage_code(name: str, index: int) -> str:
    ascii_code = "".join(
        character if character.isascii() and character.isalnum() else "_"
        for character in name.lower()
    ).strip("_")
    return ascii_code[:70] or f"stage_{index + 1}"


def _replace_pipeline_stages(
    db: Session,
    tenant_id: UUID,
    pipeline: Pipeline,
    stages: list[PipelineStageInput],
) -> None:
    existing = {stage.id: stage for stage in pipeline.stages}
    retained: set[UUID] = set()
    codes: set[str] = set()
    for index, payload in enumerate(stages):
        code = payload.code or _stage_code(payload.name, index)
        if code in codes:
            raise HTTPException(status_code=422, detail=f"Duplicate stage code: {code}")
        codes.add(code)
        if payload.id is None:
            stage = PipelineStage(
                tenant_id=tenant_id,
                pipeline_id=pipeline.id,
                code=code,
            )
            db.add(stage)
        else:
            stage = existing.get(payload.id)
            if stage is None:
                raise HTTPException(status_code=422, detail="Stage does not belong to pipeline")
            retained.add(stage.id)
        stage.name = payload.name
        stage.code = code
        stage.sort_order = index
        stage.probability = payload.probability
        stage.stage_type = payload.stage_type
        stage.is_active = True
        stage.required_fields_json = json.dumps(payload.required_fields)

    for stage_id, stage in existing.items():
        if stage_id in retained:
            continue
        used = (
            db.query(Deal.id)
            .filter(
                Deal.tenant_id == tenant_id,
                Deal.stage_id == stage.id,
                Deal.deleted_at.is_(None),
            )
            .first()
        )
        if used:
            raise HTTPException(
                status_code=409,
                detail=f"Stage '{stage.name}' has deals and cannot be removed",
            )
        db.delete(stage)


def _pipeline_response(pipeline: Pipeline) -> PipelineResponse:
    return PipelineResponse(
        id=pipeline.id,
        name=pipeline.name,
        description=pipeline.description,
        is_active=pipeline.is_active,
        is_default=pipeline.is_default,
        version=pipeline.version,
        stages=[
            PipelineStageResponse(
                id=stage.id,
                name=stage.name,
                sort_order=stage.sort_order,
                code=stage.code,
                probability=stage.probability,
                stage_type=stage.stage_type,
                is_active=stage.is_active,
                required_fields=json.loads(stage.required_fields_json),
            )
            for stage in sorted(pipeline.stages, key=lambda item: item.sort_order)
        ],
        created_at=pipeline.created_at,
        updated_at=pipeline.updated_at,
    )


def _require_stage_fields(deal: Deal, stage: PipelineStage) -> None:
    allowed = {
        "amount",
        "expected_close_date",
        "next_step",
        "owner_id",
        "forecast_category",
    }
    required = json.loads(stage.required_fields_json)
    invalid = set(required) - allowed
    if invalid:
        raise HTTPException(status_code=422, detail=f"Unsupported required fields: {sorted(invalid)}")
    missing = [field for field in required if getattr(deal, field, None) in {None, ""}]
    if missing:
        raise HTTPException(status_code=422, detail={"message": "Required deal fields are missing", "fields": missing})


def _initials(name: str) -> str:
    parts = [part for part in name.split() if part]
    return "".join(part[0] for part in parts[:2]).upper()


def _get_for_tenant(db: Session, model, tenant_id: UUID, entity_id: UUID):
    entity = db.query(model).filter(model.id == entity_id, model.tenant_id == tenant_id).one_or_none()
    if entity is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"{model.__name__} not found")
    return entity


def _require_deleted_access(tenant: CurrentTenant, include_deleted: bool) -> None:
    if include_deleted and not has_permission(tenant.role, Permission.SALES_MANAGE):
        deny_access("Deleted records require manager permission")
