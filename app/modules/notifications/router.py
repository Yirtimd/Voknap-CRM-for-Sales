from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import CurrentTenant, get_current_tenant
from app.modules.notifications.models import Notification
from app.modules.notifications.schemas import (
    NotificationReadUpdate,
    NotificationResponse,
    NotificationSummary,
)
from app.modules.notifications.service import NotificationService


router = APIRouter()


@router.get("", response_model=list[NotificationResponse])
def list_notifications(
    response: Response,
    unread_only: bool = False,
    category: str | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(get_current_tenant),
) -> list[NotificationResponse]:
    query = db.query(Notification).filter(
        Notification.tenant_id == tenant.id,
        Notification.recipient_id == tenant.user_id,
    )
    if unread_only:
        query = query.filter(Notification.read_at.is_(None))
    if category:
        query = query.filter(Notification.category == category)
    total = query.count()
    rows = (
        query.order_by(Notification.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    response.headers["X-Total-Count"] = str(total)
    response.headers["X-Page"] = str(page)
    response.headers["X-Page-Size"] = str(page_size)
    response.headers["X-Total-Pages"] = str(max(1, (total + page_size - 1) // page_size))
    return [_response(row) for row in rows]


@router.get("/summary", response_model=NotificationSummary)
def notification_summary(
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(get_current_tenant),
) -> NotificationSummary:
    unread_count, critical_count = (
        db.query(
            func.count(Notification.id),
            func.count(Notification.id).filter(Notification.priority == "critical"),
        )
        .filter(
            Notification.tenant_id == tenant.id,
            Notification.recipient_id == tenant.user_id,
            Notification.read_at.is_(None),
        )
        .one()
    )
    return NotificationSummary(
        unread_count=int(unread_count or 0),
        critical_count=int(critical_count or 0),
    )


@router.patch("/{notification_id}/read", response_model=NotificationResponse)
def update_notification_read(
    notification_id: UUID,
    payload: NotificationReadUpdate,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(get_current_tenant),
) -> NotificationResponse:
    row = _get(db, tenant, notification_id)
    NotificationService(db).mark_read(row, payload.read)
    return _response(row)


@router.post("/read-all", status_code=204)
def read_all_notifications(
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(get_current_tenant),
) -> None:
    NotificationService(db).mark_all_read(tenant.id, tenant.user_id)


def _get(db: Session, tenant: CurrentTenant, notification_id: UUID) -> Notification:
    row = (
        db.query(Notification)
        .filter(
            Notification.tenant_id == tenant.id,
            Notification.recipient_id == tenant.user_id,
            Notification.id == notification_id,
        )
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    return row


def _response(row: Notification) -> NotificationResponse:
    return NotificationResponse(
        id=row.id,
        category=row.category,
        priority=row.priority,
        title=row.title,
        body=row.body,
        link=row.link,
        source_type=row.source_type,
        source_id=row.source_id,
        metadata=row.metadata_payload,
        read_at=row.read_at,
        created_at=row.created_at,
    )
