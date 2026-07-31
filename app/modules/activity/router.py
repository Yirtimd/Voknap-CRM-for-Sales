import json
from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import CurrentTenant, get_current_tenant
from app.core.rbac import Permission, require_permission
from app.modules.activity.models import Activity
from app.modules.activity.schemas import ActivityCreate, ActivityResponse
from app.modules.activity.service import ActivityService
from app.modules.sales.authorization import require_company_write_access
from app.modules.sales.models import Deal
from app.modules.sales.scoring import ScoringService


router = APIRouter()


@router.get("", response_model=list[ActivityResponse])
def list_activities(
    company_id: UUID | None = None,
    contact_id: UUID | None = None,
    deal_id: UUID | None = None,
    activity_type: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(get_current_tenant),
) -> list[ActivityResponse]:
    service = ActivityService(db)
    return [
        _activity_response(activity)
        for activity in service.list(
            tenant_id=tenant.id,
            company_id=company_id,
            contact_id=contact_id,
            deal_id=deal_id,
            activity_type=activity_type,
            limit=limit,
        )
    ]


@router.post("", response_model=ActivityResponse)
def create_activity(
    payload: ActivityCreate,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> ActivityResponse:
    require_company_write_access(db, tenant, payload.company_id)
    service = ActivityService(db)
    activity = service.create(
        tenant_id=tenant.id,
        created_by=tenant.user_id,
        company_id=payload.company_id,
        activity_type=payload.type,
        channel=payload.channel,
        title=payload.title,
        description=payload.description,
        contact_id=payload.contact_id,
        deal_id=payload.deal_id,
        metadata=payload.metadata,
    )
    if activity.deal_id:
        deal = db.query(Deal).filter(
            Deal.tenant_id == tenant.id,
            Deal.id == activity.deal_id,
        ).one()
        ScoringService(db).recalculate_deal(
            deal,
            actor_id=tenant.user_id,
            reason="activity_created",
        )
        db.commit()
    return _activity_response(activity)


def _activity_response(activity: Activity) -> ActivityResponse:
    return ActivityResponse(
        id=activity.id,
        tenant_id=activity.tenant_id,
        company_id=activity.company_id,
        contact_id=activity.contact_id,
        deal_id=activity.deal_id,
        type=activity.type,
        channel=activity.channel,
        title=activity.title,
        description=activity.description,
        created_by=activity.created_by,
        created_at=activity.created_at,
        metadata=json.loads(activity.metadata_json),
    )
