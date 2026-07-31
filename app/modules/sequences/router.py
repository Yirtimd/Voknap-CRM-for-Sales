from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import CurrentTenant
from app.core.rbac import Permission, require_object_owner, require_permission
from app.modules.sales.models import Company, Contact
from app.modules.sequences.models import (
    Cadence,
    CadenceEnrollment,
    CadenceExecution,
    CadenceStep,
)
from app.modules.sequences.schemas import (
    CadenceCreate,
    CadenceResponse,
    CadenceStepResponse,
    CadenceUpdate,
    EnrollmentAction,
    EnrollmentCreate,
    EnrollmentResponse,
    EmailAccountOption,
    ExecutionResponse,
    RunDueResponse,
)
from app.modules.sequences.service import CadenceService
from app.modules.connectors.models import ConnectorAccount


router = APIRouter()


@router.get("/email-accounts", response_model=list[EmailAccountOption])
def list_email_accounts(
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_READ)),
) -> list[EmailAccountOption]:
    rows = (
        db.query(ConnectorAccount)
        .filter(
            ConnectorAccount.tenant_id == tenant.id,
            ConnectorAccount.connector_code == "email",
            ConnectorAccount.status == "connected",
        )
        .order_by(ConnectorAccount.title)
        .all()
    )
    return [EmailAccountOption(id=row.id, title=row.title, status=row.status) for row in rows]


@router.get("", response_model=list[CadenceResponse])
def list_cadences(
    include_inactive: bool = False,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_READ)),
) -> list[CadenceResponse]:
    query = db.query(Cadence).filter(Cadence.tenant_id == tenant.id)
    if not include_inactive:
        query = query.filter(Cadence.is_active.is_(True))
    return [_cadence_response(db, tenant.id, row) for row in query.order_by(Cadence.name)]


@router.post("", response_model=CadenceResponse, status_code=status.HTTP_201_CREATED)
def create_cadence(
    payload: CadenceCreate,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.SALES_MANAGE)),
) -> CadenceResponse:
    row = Cadence(
        tenant_id=tenant.id,
        name=payload.name,
        description=payload.description,
        is_active=payload.is_active,
        created_by_id=tenant.user_id,
        updated_by_id=tenant.user_id,
    )
    db.add(row)
    db.flush()
    _replace_steps(db, tenant.id, row.id, payload.steps)
    db.commit()
    db.refresh(row)
    return _cadence_response(db, tenant.id, row)


@router.patch("/{cadence_id}", response_model=CadenceResponse)
def update_cadence(
    cadence_id: UUID,
    payload: CadenceUpdate,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.SALES_MANAGE)),
) -> CadenceResponse:
    row = _get(db, Cadence, tenant.id, cadence_id, "Cadence")
    if row.version != payload.version:
        raise HTTPException(
            status_code=409,
            detail={"message": "Version conflict", "current_version": row.version},
        )
    if payload.steps is not None:
        existing_enrollment = (
            db.query(CadenceEnrollment.id)
            .filter(
                CadenceEnrollment.tenant_id == tenant.id,
                CadenceEnrollment.cadence_id == row.id,
            )
            .first()
        )
        if existing_enrollment:
            raise HTTPException(
                status_code=409,
                detail="Cadence with enrollment history is immutable; duplicate it to change steps",
            )
        _replace_steps(db, tenant.id, row.id, payload.steps)
    for field, value in payload.model_dump(
        exclude={"version", "steps"}, exclude_unset=True
    ).items():
        setattr(row, field, value)
    row.updated_by_id = tenant.user_id
    db.commit()
    db.refresh(row)
    return _cadence_response(db, tenant.id, row)


@router.get("/enrollments", response_model=list[EnrollmentResponse])
def list_enrollments(
    contact_id: UUID | None = None,
    company_id: UUID | None = None,
    enrollment_status: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_READ)),
) -> list[EnrollmentResponse]:
    query = db.query(CadenceEnrollment).filter(CadenceEnrollment.tenant_id == tenant.id)
    if contact_id:
        query = query.filter(CadenceEnrollment.contact_id == contact_id)
    if company_id:
        query = query.filter(CadenceEnrollment.company_id == company_id)
    if enrollment_status:
        allowed = {"active", "paused", "completed", "stopped", "replied", "failed"}
        if enrollment_status not in allowed:
            raise HTTPException(status_code=422, detail="Unsupported enrollment status")
        query = query.filter(CadenceEnrollment.status == enrollment_status)
    return [
        _enrollment_response(db, tenant.id, row)
        for row in query.order_by(CadenceEnrollment.created_at.desc()).limit(500)
    ]


@router.post(
    "/enrollments", response_model=EnrollmentResponse, status_code=status.HTTP_201_CREATED
)
def create_enrollment(
    payload: EnrollmentCreate,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> EnrollmentResponse:
    contact = _get(db, Contact, tenant.id, payload.contact_id, "Contact")
    company = _get(db, Company, tenant.id, contact.company_id, "Company")
    require_object_owner(tenant.role, tenant.user_id, contact.owner_id or company.owner_id)
    row = CadenceService(db).enroll(
        tenant_id=tenant.id,
        cadence_id=payload.cadence_id,
        contact_id=payload.contact_id,
        deal_id=payload.deal_id,
        connector_account_id=payload.connector_account_id,
        actor_id=tenant.user_id,
    )
    return _enrollment_response(db, tenant.id, row)


@router.post("/enrollments/{enrollment_id}/pause", response_model=EnrollmentResponse)
def pause_enrollment(
    enrollment_id: UUID,
    payload: EnrollmentAction,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> EnrollmentResponse:
    row = _owned_enrollment(db, tenant, enrollment_id, payload.version)
    CadenceService(db).pause(row, tenant.user_id, payload.reason)
    db.refresh(row)
    return _enrollment_response(db, tenant.id, row)


@router.post("/enrollments/{enrollment_id}/resume", response_model=EnrollmentResponse)
def resume_enrollment(
    enrollment_id: UUID,
    payload: EnrollmentAction,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> EnrollmentResponse:
    row = _owned_enrollment(db, tenant, enrollment_id, payload.version)
    CadenceService(db).resume(row, tenant.user_id)
    db.refresh(row)
    return _enrollment_response(db, tenant.id, row)


@router.post("/enrollments/{enrollment_id}/stop", response_model=EnrollmentResponse)
def stop_enrollment(
    enrollment_id: UUID,
    payload: EnrollmentAction,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> EnrollmentResponse:
    row = _owned_enrollment(db, tenant, enrollment_id, payload.version)
    CadenceService(db).stop(row, tenant.user_id, payload.reason)
    db.refresh(row)
    return _enrollment_response(db, tenant.id, row)


@router.get("/enrollments/{enrollment_id}/executions", response_model=list[ExecutionResponse])
def list_executions(
    enrollment_id: UUID,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_READ)),
) -> list[ExecutionResponse]:
    _get(db, CadenceEnrollment, tenant.id, enrollment_id, "Enrollment")
    rows = (
        db.query(CadenceExecution)
        .filter(
            CadenceExecution.tenant_id == tenant.id,
            CadenceExecution.enrollment_id == enrollment_id,
        )
        .order_by(CadenceExecution.scheduled_at)
        .all()
    )
    return [_execution_response(db, tenant.id, row) for row in rows]


@router.post("/run-due", response_model=RunDueResponse)
def run_due(
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.SALES_MANAGE)),
) -> RunDueResponse:
    evaluated, executed = CadenceService(db).process_due(tenant.id)
    return RunDueResponse(evaluated=evaluated, executed=executed)


def _owned_enrollment(
    db: Session, tenant: CurrentTenant, enrollment_id: UUID, version: int
) -> CadenceEnrollment:
    row = _get(db, CadenceEnrollment, tenant.id, enrollment_id, "Enrollment")
    if row.version != version:
        raise HTTPException(
            status_code=409,
            detail={"message": "Version conflict", "current_version": row.version},
        )
    require_object_owner(tenant.role, tenant.user_id, row.owner_id)
    return row


def _replace_steps(db: Session, tenant_id: UUID, cadence_id: UUID, steps) -> None:
    db.query(CadenceStep).filter(
        CadenceStep.tenant_id == tenant_id, CadenceStep.cadence_id == cadence_id
    ).delete(synchronize_session=False)
    for position, step in enumerate(steps):
        db.add(
            CadenceStep(
                tenant_id=tenant_id,
                cadence_id=cadence_id,
                position=position,
                **step.model_dump(),
            )
        )


def _cadence_response(db: Session, tenant_id: UUID, row: Cadence) -> CadenceResponse:
    steps = (
        db.query(CadenceStep)
        .filter(CadenceStep.tenant_id == tenant_id, CadenceStep.cadence_id == row.id)
        .order_by(CadenceStep.position)
        .all()
    )
    return CadenceResponse(
        id=row.id,
        name=row.name,
        description=row.description,
        is_active=row.is_active,
        steps=[
            CadenceStepResponse(
                id=step.id,
                position=step.position,
                step_type=step.step_type,
                delay_minutes=step.delay_minutes,
                title=step.title,
                body=step.body,
                task_priority=step.task_priority,
            )
            for step in steps
        ],
        version=row.version,
        created_by_id=row.created_by_id,
        updated_by_id=row.updated_by_id,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _enrollment_response(
    db: Session, tenant_id: UUID, row: CadenceEnrollment
) -> EnrollmentResponse:
    cadence = _get(db, Cadence, tenant_id, row.cadence_id, "Cadence")
    contact = _get(db, Contact, tenant_id, row.contact_id, "Contact")
    step_count = (
        db.query(CadenceStep.id)
        .filter(CadenceStep.tenant_id == tenant_id, CadenceStep.cadence_id == cadence.id)
        .count()
    )
    return EnrollmentResponse(
        id=row.id,
        cadence_id=row.cadence_id,
        cadence_name=cadence.name,
        contact_id=row.contact_id,
        contact_name=contact.name,
        company_id=row.company_id,
        deal_id=row.deal_id,
        connector_account_id=row.connector_account_id,
        owner_id=row.owner_id,
        status=row.status,
        current_step=row.current_step,
        step_count=step_count,
        next_run_at=row.next_run_at,
        last_executed_at=row.last_executed_at,
        stop_reason=row.stop_reason,
        version=row.version,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _execution_response(
    db: Session, tenant_id: UUID, row: CadenceExecution
) -> ExecutionResponse:
    step = _get(db, CadenceStep, tenant_id, row.step_id, "Cadence step")
    return ExecutionResponse(
        id=row.id,
        enrollment_id=row.enrollment_id,
        step_id=row.step_id,
        step_position=step.position,
        step_type=step.step_type,
        title=step.title,
        status=row.status,
        task_id=row.task_id,
        communication_event_id=row.communication_event_id,
        integration_job_id=row.integration_job_id,
        error=row.error,
        scheduled_at=row.scheduled_at,
        executed_at=row.executed_at,
    )


def _get(db: Session, model, tenant_id: UUID, object_id: UUID, label: str):
    row = db.query(model).filter(model.tenant_id == tenant_id, model.id == object_id).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"{label} not found")
    return row
