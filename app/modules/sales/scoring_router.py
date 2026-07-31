from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import CurrentTenant
from app.core.rbac import Permission, require_permission
from app.modules.sales.models import Deal, Lead, ScoreSnapshot
from app.modules.sales.schemas import ScoreSnapshotResponse
from app.modules.sales.scoring import ScoringService
from app.modules.sales.lifecycle import require_entity_write_access


router = APIRouter()


def _entity(db: Session, tenant_id: UUID, entity_type: str, entity_id: UUID) -> Lead | Deal:
    model = Lead if entity_type == "lead" else Deal
    entity = db.query(model).filter(model.tenant_id == tenant_id, model.id == entity_id).one_or_none()
    if entity is None or entity.deleted_at is not None:
        raise HTTPException(status_code=404, detail=f"{entity_type.title()} not found")
    return entity


@router.post(
    "/scoring/{entity_type}/{entity_id}/recalculate",
    response_model=ScoreSnapshotResponse,
)
def recalculate_score(
    entity_type: Literal["lead", "deal"],
    entity_id: UUID,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> ScoreSnapshot:
    entity = _entity(db, tenant.id, entity_type, entity_id)
    require_entity_write_access(
        tenant,
        "leads" if entity_type == "lead" else "deals",
        entity,
    )
    service = ScoringService(db)
    if entity_type == "lead":
        service.recalculate_lead(entity, actor_id=tenant.user_id, reason="manual_recalculation")
    else:
        service.recalculate_deal(entity, actor_id=tenant.user_id, reason="manual_recalculation")
    db.commit()
    return service.history(tenant.id, entity_type, entity_id, 1)[0]


@router.get(
    "/scoring/{entity_type}/{entity_id}/history",
    response_model=list[ScoreSnapshotResponse],
)
def score_history(
    entity_type: Literal["lead", "deal"],
    entity_id: UUID,
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_READ)),
) -> list[ScoreSnapshot]:
    _entity(db, tenant.id, entity_type, entity_id)
    return ScoringService(db).history(tenant.id, entity_type, entity_id, limit)


@router.post("/scoring/recalculate", response_model=dict)
def recalculate_all_scores(
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.SALES_MANAGE)),
) -> dict:
    service = ScoringService(db)
    leads = db.query(Lead).filter(
        Lead.tenant_id == tenant.id,
        Lead.deleted_at.is_(None),
        Lead.is_archived.is_(False),
    ).all()
    for lead in leads:
        service.recalculate_lead(lead, actor_id=tenant.user_id, reason="bulk_recalculation")
    deals = db.query(Deal).filter(
        Deal.tenant_id == tenant.id,
        Deal.deleted_at.is_(None),
        Deal.is_archived.is_(False),
    ).all()
    for deal in deals:
        service.recalculate_deal(deal, actor_id=tenant.user_id, reason="bulk_recalculation")
    db.commit()
    return {"leads": len(leads), "deals": len(deals), "model_version": "rules-v1"}
