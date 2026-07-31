import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import CurrentTenant
from app.core.rbac import Permission, deny_access, has_permission, require_permission
from app.modules.activity.models import Activity
from app.modules.activity.service import ActivityService
from app.modules.automation.service import AutomationEngine
from app.modules.communication.models import CommunicationEvent
from app.modules.knowledge.models import KnowledgeChunk, KnowledgeDocument, KnowledgeQuery
from app.modules.sales.authorization import require_company_write_access
from app.modules.sales.deduplication import scan_duplicates
from app.modules.sales.lifecycle import (
    OWNER_FIELDS,
    EntityType,
    add_history,
    apply_update,
    commit_versioned,
    ensure_member,
    get_entity,
    require_entity_write_access,
    require_version,
    restore_deleted,
    set_archived,
    soft_delete,
    utc_now,
)
from app.modules.sales.lifecycle_schemas import (
    ArchiveRequest,
    BulkActionRequest,
    BulkActionResponse,
    ContactUpdate,
    DealUpdate,
    DuplicateCandidateResponse,
    DuplicateDismissRequest,
    DuplicateScanRequest,
    FieldChangeResponse,
    LeadConversionRequest,
    LeadConversionResponse,
    LeadQualificationRequest,
    LeadUpdate,
    MergeRequest,
    MergeResponse,
    NoteUpdate,
    ReassignRequest,
    RestoreRequest,
    TaskUpdate,
)
from app.modules.sales.models import (
    CompanyFile,
    Contact,
    Deal,
    DuplicateCandidate,
    FieldChange,
    Lead,
    NextAction,
    Note,
    PipelineStage,
    Task,
)
from app.modules.sales.scoring import ScoringService
from app.modules.sales.schemas import (
    ContactResponse,
    DealResponse,
    LeadResponse,
    NoteResponse,
    TaskResponse,
)


router = APIRouter()


@router.post("/dedup/scan", response_model=dict)
def scan_duplicate_candidates(
    payload: DuplicateScanRequest,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.SALES_MANAGE)),
) -> dict:
    detected = scan_duplicates(
        db,
        tenant.id,
        payload.entity_type,
        tenant.user_id,
        payload.minimum_score,
        payload.limit,
    )
    return {"entity_type": payload.entity_type, "detected": detected}


@router.get("/dedup/candidates", response_model=list[DuplicateCandidateResponse])
def list_duplicate_candidates(
    entity_type: str | None = None,
    candidate_status: str = Query(default="open", alias="status"),
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_READ)),
) -> list[DuplicateCandidateResponse]:
    query = db.query(DuplicateCandidate).filter(
        DuplicateCandidate.tenant_id == tenant.id,
        DuplicateCandidate.status == candidate_status,
    )
    if entity_type:
        query = query.filter(DuplicateCandidate.entity_type == entity_type)
    return [_duplicate_response(row) for row in query.order_by(DuplicateCandidate.score.desc())]


@router.post("/dedup/candidates/{candidate_id}/dismiss", response_model=DuplicateCandidateResponse)
def dismiss_duplicate_candidate(
    candidate_id: UUID,
    payload: DuplicateDismissRequest,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.SALES_MANAGE)),
) -> DuplicateCandidateResponse:
    candidate = (
        db.query(DuplicateCandidate)
        .filter(DuplicateCandidate.tenant_id == tenant.id, DuplicateCandidate.id == candidate_id)
        .one_or_none()
    )
    if candidate is None:
        raise HTTPException(status_code=404, detail="Duplicate candidate not found")
    require_version(candidate, payload.version)
    if candidate.status != "open":
        raise HTTPException(status_code=409, detail="Duplicate candidate is already resolved")
    candidate.status = "dismissed"
    candidate.resolved_by_id = tenant.user_id
    candidate.resolution_comment = payload.comment
    candidate.resolved_at = utc_now()
    commit_versioned(db, candidate)
    return _duplicate_response(candidate)


@router.get("/contacts/{entity_id}", response_model=ContactResponse)
def get_contact(
    entity_id: UUID,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_READ)),
) -> Contact:
    return get_entity(db, tenant.id, "contacts", entity_id)


@router.patch("/contacts/{entity_id}", response_model=ContactResponse)
def update_contact(
    entity_id: UUID,
    payload: ContactUpdate,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> Contact:
    return _update_entity(db, tenant, "contacts", entity_id, payload)


@router.get("/leads/{entity_id}/record", response_model=LeadResponse)
def get_lead_record(
    entity_id: UUID,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_READ)),
) -> Lead:
    return get_entity(db, tenant.id, "leads", entity_id)


@router.patch("/leads/{entity_id}", response_model=LeadResponse)
def update_lead(
    entity_id: UUID,
    payload: LeadUpdate,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> Lead:
    if payload.status in {"qualified", "disqualified", "converted"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Use qualification or conversion endpoint for this status",
        )
    return _update_entity(db, tenant, "leads", entity_id, payload)


@router.get("/deals/{entity_id}", response_model=DealResponse)
def get_deal(
    entity_id: UUID,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_READ)),
) -> Deal:
    return get_entity(db, tenant.id, "deals", entity_id)


@router.patch("/deals/{entity_id}", response_model=DealResponse)
def update_deal(
    entity_id: UUID,
    payload: DealUpdate,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> Deal:
    return _update_entity(db, tenant, "deals", entity_id, payload)


@router.get("/tasks/{entity_id}", response_model=TaskResponse)
def get_task(
    entity_id: UUID,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_READ)),
) -> Task:
    return get_entity(db, tenant.id, "tasks", entity_id)


@router.patch("/tasks/{entity_id}", response_model=TaskResponse)
def update_task(
    entity_id: UUID,
    payload: TaskUpdate,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> Task:
    return _update_entity(db, tenant, "tasks", entity_id, payload)


@router.get("/notes/{entity_id}", response_model=NoteResponse)
def get_note(
    entity_id: UUID,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_READ)),
) -> Note:
    return get_entity(db, tenant.id, "notes", entity_id)


@router.patch("/notes/{entity_id}", response_model=NoteResponse)
def update_note(
    entity_id: UUID,
    payload: NoteUpdate,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> Note:
    return _update_entity(db, tenant, "notes", entity_id, payload)


@router.patch("/{entity_type}/{entity_id}/archive")
def archive_entity(
    entity_type: EntityType,
    entity_id: UUID,
    payload: ArchiveRequest,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> dict:
    entity = get_entity(db, tenant.id, entity_type, entity_id, include_archived=True)
    require_entity_write_access(tenant, entity_type, entity)
    require_version(entity, payload.version)
    set_archived(db, tenant, entity_type, entity, payload.is_archived)
    commit_versioned(db, entity)
    return _lifecycle_result(entity)


@router.delete("/{entity_type}/{entity_id}")
def delete_entity(
    entity_type: EntityType,
    entity_id: UUID,
    version: int = Query(ge=1),
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> dict:
    entity = get_entity(db, tenant.id, entity_type, entity_id, include_archived=True)
    require_entity_write_access(tenant, entity_type, entity)
    require_version(entity, version)
    soft_delete(db, tenant, entity_type, entity)
    commit_versioned(db, entity)
    return _lifecycle_result(entity)


@router.post("/{entity_type}/{entity_id}/restore")
def restore_entity(
    entity_type: EntityType,
    entity_id: UUID,
    payload: RestoreRequest,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> dict:
    entity = get_entity(
        db,
        tenant.id,
        entity_type,
        entity_id,
        include_deleted=True,
        include_archived=True,
    )
    require_entity_write_access(tenant, entity_type, entity)
    require_version(entity, payload.version)
    restore_deleted(db, tenant, entity_type, entity)
    commit_versioned(db, entity)
    return _lifecycle_result(entity)


@router.patch("/{entity_type}/{entity_id}/owner")
def reassign_entity(
    entity_type: EntityType,
    entity_id: UUID,
    payload: ReassignRequest,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.ASSIGNMENTS_MANAGE)),
) -> dict:
    if entity_type == "notes":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Note authorship cannot be reassigned",
        )
    entity = get_entity(db, tenant.id, entity_type, entity_id, include_archived=True)
    require_version(entity, payload.version)
    ensure_member(db, tenant.id, payload.owner_id)
    apply_update(
        db,
        tenant,
        entity_type,
        entity,
        {OWNER_FIELDS[entity_type]: payload.owner_id},
    )
    commit_versioned(db, entity)
    return _lifecycle_result(entity)


@router.get("/{entity_type}/{entity_id}/history", response_model=list[FieldChangeResponse])
def entity_history(
    entity_type: EntityType,
    entity_id: UUID,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_READ)),
) -> list[FieldChangeResponse]:
    get_entity(
        db,
        tenant.id,
        entity_type,
        entity_id,
        include_deleted=True,
        include_archived=True,
    )
    rows = (
        db.query(FieldChange)
        .filter(
            FieldChange.tenant_id == tenant.id,
            FieldChange.entity_type == entity_type,
            FieldChange.entity_id == entity_id,
        )
        .order_by(FieldChange.created_at.desc())
        .all()
    )
    return [
        FieldChangeResponse(
            id=row.id,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            field_name=row.field_name,
            old_value=json.loads(row.old_value_json) if row.old_value_json is not None else None,
            new_value=json.loads(row.new_value_json) if row.new_value_json is not None else None,
            changed_by_id=row.changed_by_id,
            entity_version=row.entity_version,
            created_at=row.created_at,
        )
        for row in rows
    ]


@router.post("/{entity_type}/bulk", response_model=BulkActionResponse)
def bulk_action(
    entity_type: EntityType,
    payload: BulkActionRequest,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> BulkActionResponse:
    if payload.action == "reassign":
        if not has_permission(tenant.role, Permission.ASSIGNMENTS_MANAGE):
            deny_access()
        if entity_type == "notes":
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Note authorship cannot be reassigned",
            )
        ensure_member(db, tenant.id, payload.owner_id)

    entities = []
    for item in payload.items:
        entity = get_entity(
            db,
            tenant.id,
            entity_type,
            item.id,
            include_deleted=payload.action == "restore",
            include_archived=payload.action in {"unarchive", "delete", "restore"},
        )
        require_entity_write_access(tenant, entity_type, entity)
        require_version(entity, item.version)
        if payload.action == "archive":
            set_archived(db, tenant, entity_type, entity, True)
        elif payload.action == "unarchive":
            set_archived(db, tenant, entity_type, entity, False)
        elif payload.action == "delete":
            soft_delete(db, tenant, entity_type, entity)
        elif payload.action == "restore":
            restore_deleted(db, tenant, entity_type, entity)
        else:
            apply_update(
                db,
                tenant,
                entity_type,
                entity,
                {OWNER_FIELDS[entity_type]: payload.owner_id},
            )
        entities.append(entity)

    commit_versioned(db, entities[0])
    return BulkActionResponse(affected=len(entities), action=payload.action)


@router.post("/{entity_type}/{target_id}/merge", response_model=MergeResponse)
def merge_entities(
    entity_type: EntityType,
    target_id: UUID,
    payload: MergeRequest,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> MergeResponse:
    if entity_type not in {"contacts", "leads", "deals"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Merge is supported for contacts, leads, and deals",
        )
    target = get_entity(db, tenant.id, entity_type, target_id)
    require_entity_write_access(tenant, entity_type, target)
    require_version(target, payload.target_version)
    source_ids = []
    for source_item in payload.sources:
        if source_item.id == target_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Target cannot be a merge source",
            )
        source = get_entity(db, tenant.id, entity_type, source_item.id)
        require_entity_write_access(tenant, entity_type, source)
        require_version(source, source_item.version)
        if source.company_id != target.company_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Merge records must belong to the same company",
            )
        _rewire_merge_references(db, tenant.id, entity_type, source.id, target.id)
        soft_delete(db, tenant, entity_type, source)
        _resolve_duplicate_pair(db, tenant.id, entity_type, source.id, target.id, tenant.user_id)
        source_ids.append(source.id)

    add_history(
        db,
        tenant,
        entity_type,
        target.id,
        "merged_ids",
        [],
        source_ids,
        target.version + 1,
    )
    target.updated_at = utc_now()
    ActivityService(db).create(
        tenant_id=tenant.id,
        created_by=tenant.user_id,
        company_id=target.company_id,
        activity_type="RECORDS_MERGED",
        title=f"{entity_type} merged",
        metadata={"target_id": str(target.id), "source_ids": [str(item) for item in source_ids]},
        commit=False,
    )
    commit_versioned(db, target)
    return MergeResponse(target_id=target.id, merged_ids=source_ids, version=target.version)


@router.post("/leads/{lead_id}/qualify", response_model=LeadResponse)
def qualify_lead(
    lead_id: UUID,
    payload: LeadQualificationRequest,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> Lead:
    lead = get_entity(db, tenant.id, "leads", lead_id)
    require_entity_write_access(tenant, "leads", lead)
    require_version(lead, payload.version)
    if lead.converted_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Converted lead cannot be requalified")
    values = {
        "status": "qualified" if payload.qualified else "disqualified",
        "qualified_at": utc_now() if payload.qualified else None,
        "qualified_by_id": tenant.user_id if payload.qualified else None,
        "disqualification_reason": None if payload.qualified else payload.reason,
    }
    apply_update(db, tenant, "leads", lead, values)
    ActivityService(db).create(
        tenant_id=tenant.id,
        created_by=tenant.user_id,
        company_id=lead.company_id,
        contact_id=lead.contact_id,
        activity_type="LEAD_QUALIFIED" if payload.qualified else "LEAD_DISQUALIFIED",
        title="Lead qualified" if payload.qualified else "Lead disqualified",
        description=payload.reason,
        metadata={"lead_id": str(lead.id)},
        commit=False,
    )
    ScoringService(db).recalculate_lead(
        lead,
        actor_id=tenant.user_id,
        reason="lead_qualified" if payload.qualified else "lead_disqualified",
    )
    commit_versioned(db, lead)
    return lead


@router.post("/leads/{lead_id}/convert", response_model=LeadConversionResponse)
def convert_lead(
    lead_id: UUID,
    payload: LeadConversionRequest,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> LeadConversionResponse:
    lead = get_entity(db, tenant.id, "leads", lead_id)
    require_entity_write_access(tenant, "leads", lead)
    require_version(lead, payload.version)
    if lead.status != "qualified" or lead.qualified_at is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Lead must be qualified first")
    if lead.converted_at is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Lead already converted")
    stage = (
        db.query(PipelineStage)
        .filter(PipelineStage.id == payload.stage_id, PipelineStage.tenant_id == tenant.id)
        .one_or_none()
    )
    if stage is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline stage not found")

    owner_id = payload.owner_id or lead.owner_id or tenant.user_id
    if owner_id != tenant.user_id and not has_permission(tenant.role, Permission.ASSIGNMENTS_MANAGE):
        deny_access("Only a manager can assign conversion ownership")
    ensure_member(db, tenant.id, owner_id)
    deal = Deal(
        tenant_id=tenant.id,
        company_id=lead.company_id,
        lead_id=lead.id,
        stage_id=stage.id,
        title=payload.title or lead.title,
        amount=payload.amount,
        owner_id=owner_id,
        status="open",
    )
    db.add(deal)
    db.flush()
    apply_update(
        db,
        tenant,
        "leads",
        lead,
        {
            "status": "converted",
            "converted_at": utc_now(),
            "converted_by_id": tenant.user_id,
            "converted_deal_id": deal.id,
        },
    )
    ActivityService(db).create(
        tenant_id=tenant.id,
        created_by=tenant.user_id,
        company_id=lead.company_id,
        contact_id=lead.contact_id,
        deal_id=deal.id,
        activity_type="LEAD_CONVERTED",
        title="Lead converted to deal",
        description=deal.title,
        metadata={"lead_id": str(lead.id), "deal_id": str(deal.id)},
        commit=False,
    )
    scoring = ScoringService(db)
    scoring.recalculate_lead(
        lead,
        actor_id=tenant.user_id,
        reason="lead_converted",
    )
    scoring.recalculate_deal(
        deal,
        actor_id=tenant.user_id,
        reason="lead_conversion",
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
    commit_versioned(db, lead)
    db.refresh(deal)
    return LeadConversionResponse(
        lead=LeadResponse.model_validate(lead),
        deal=DealResponse.model_validate(deal),
    )


def _update_entity(
    db: Session,
    tenant: CurrentTenant,
    entity_type: EntityType,
    entity_id: UUID,
    payload,
):
    entity = get_entity(db, tenant.id, entity_type, entity_id)
    require_entity_write_access(tenant, entity_type, entity)
    require_version(entity, payload.version)
    update_data = payload.model_dump(exclude={"version"}, exclude_unset=True)
    _validate_relations(db, tenant, entity_type, entity, update_data)
    old_stage_id = entity.stage_id if entity_type == "deals" else None
    changed_fields = apply_update(db, tenant, entity_type, entity, update_data)
    if changed_fields and entity_type == "leads":
        ScoringService(db).recalculate_lead(
            entity,
            actor_id=tenant.user_id,
            reason="lead_updated",
        )
    elif changed_fields and entity_type == "deals":
        ScoringService(db).recalculate_deal(
            entity,
            actor_id=tenant.user_id,
            reason="deal_updated",
        )
    elif changed_fields and entity_type == "tasks" and entity.deal_id:
        deal = get_entity(db, tenant.id, "deals", entity.deal_id)
        ScoringService(db).recalculate_deal(
            deal,
            actor_id=tenant.user_id,
            reason="task_updated",
        )
    if entity_type == "deals" and changed_fields:
        automation = AutomationEngine(db)
        context = automation.deal_context(entity)
        context["changed_fields"] = changed_fields
        automation.emit(
            tenant_id=tenant.id,
            trigger_type="deal.updated",
            entity_type="deal",
            entity_id=entity.id,
            event_key=f"deal.updated:{entity.id}:{entity.version + 1}",
            context=context,
            actor_id=tenant.user_id,
        )
        if "stage_id" in changed_fields:
            context["old_stage_id"] = str(old_stage_id)
            automation.emit(
                tenant_id=tenant.id,
                trigger_type="deal.stage_changed",
                entity_type="deal",
                entity_id=entity.id,
                event_key=f"deal.stage_changed:{entity.id}:{entity.version + 1}",
                context=context,
                actor_id=tenant.user_id,
            )
    commit_versioned(db, entity)
    return entity


def _validate_relations(
    db: Session,
    tenant: CurrentTenant,
    entity_type: EntityType,
    entity,
    values: dict,
) -> None:
    company_id = values.get("company_id", getattr(entity, "company_id", None))
    if "company_id" in values:
        require_company_write_access(db, tenant, values["company_id"])
    if entity_type == "leads" and values.get("contact_id") is not None:
        contact = get_entity(db, tenant.id, "contacts", values["contact_id"])
        if contact.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Contact belongs to another company",
            )
    if entity_type == "deals":
        if values.get("stage_id") is not None:
            stage = (
                db.query(PipelineStage)
                .filter(PipelineStage.id == values["stage_id"], PipelineStage.tenant_id == tenant.id)
                .one_or_none()
            )
            if stage is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pipeline stage not found")
        if values.get("lead_id") is not None:
            lead = get_entity(db, tenant.id, "leads", values["lead_id"])
            if lead.company_id != company_id:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="Lead belongs to another company",
                )
    if entity_type == "tasks" and values.get("deal_id") is not None:
        deal = get_entity(db, tenant.id, "deals", values["deal_id"])
        if deal.company_id != company_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Deal belongs to another company",
            )


def _rewire_merge_references(
    db: Session,
    tenant_id: UUID,
    entity_type: EntityType,
    source_id: UUID,
    target_id: UUID,
) -> None:
    if entity_type == "contacts":
        references = (
            (Lead, Lead.contact_id),
            (NextAction, NextAction.contact_id),
            (Activity, Activity.contact_id),
            (CompanyFile, CompanyFile.contact_id),
            (CommunicationEvent, CommunicationEvent.contact_id),
        )
    elif entity_type == "leads":
        references = ((Deal, Deal.lead_id), (Note, Note.lead_id))
    else:
        references = (
            (Task, Task.deal_id),
            (Note, Note.deal_id),
            (NextAction, NextAction.deal_id),
            (Activity, Activity.deal_id),
            (CompanyFile, CompanyFile.deal_id),
            (CommunicationEvent, CommunicationEvent.deal_id),
            (KnowledgeDocument, KnowledgeDocument.deal_id),
            (KnowledgeChunk, KnowledgeChunk.deal_id),
            (KnowledgeQuery, KnowledgeQuery.deal_id),
            (Lead, Lead.converted_deal_id),
        )
    for model, column in references:
        db.query(model).filter(
            model.tenant_id == tenant_id,
            column == source_id,
        ).update({column: target_id}, synchronize_session=False)


def _lifecycle_result(entity) -> dict:
    return {
        "id": str(entity.id),
        "is_archived": entity.is_archived,
        "deleted_at": entity.deleted_at,
        "version": entity.version,
    }


def _duplicate_response(row: DuplicateCandidate) -> DuplicateCandidateResponse:
    return DuplicateCandidateResponse(
        id=row.id,
        entity_type=row.entity_type,
        record_a_id=row.record_a_id,
        record_b_id=row.record_b_id,
        score=row.score,
        matched_fields=json.loads(row.matched_fields_json),
        status=row.status,
        version=row.version,
        detected_at=row.detected_at,
        resolved_at=row.resolved_at,
    )


def _resolve_duplicate_pair(
    db: Session,
    tenant_id: UUID,
    entity_type: str,
    source_id: UUID,
    target_id: UUID,
    actor_id: UUID,
) -> None:
    a_id, b_id = sorted((source_id, target_id), key=str)
    candidate = (
        db.query(DuplicateCandidate)
        .filter(
            DuplicateCandidate.tenant_id == tenant_id,
            DuplicateCandidate.entity_type == entity_type,
            DuplicateCandidate.record_a_id == a_id,
            DuplicateCandidate.record_b_id == b_id,
            DuplicateCandidate.status == "open",
        )
        .one_or_none()
    )
    if candidate:
        candidate.status = "merged"
        candidate.resolved_by_id = actor_id
        candidate.resolution_comment = "Merged through CRM lifecycle"
        candidate.resolved_at = utc_now()
