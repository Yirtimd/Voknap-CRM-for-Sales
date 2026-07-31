import json
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.accounts.models import Membership
from app.modules.notifications.models import Notification


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class NotificationService:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        tenant_id: UUID,
        recipient_id: UUID | None,
        event_key: str,
        category: str,
        title: str,
        body: str | None = None,
        priority: str = "normal",
        link: str | None = None,
        source_type: str | None = None,
        source_id: UUID | None = None,
        metadata: dict | None = None,
    ) -> Notification | None:
        if recipient_id is None:
            return None
        member = (
            self.db.query(Membership.id)
            .filter(
                Membership.tenant_id == tenant_id,
                Membership.user_id == recipient_id,
                Membership.is_active.is_(True),
            )
            .first()
        )
        if member is None:
            return None
        existing = (
            self.db.query(Notification)
            .filter(
                Notification.tenant_id == tenant_id,
                Notification.recipient_id == recipient_id,
                Notification.event_key == event_key[:255],
            )
            .one_or_none()
        )
        if existing is not None:
            return existing
        row = Notification(
            tenant_id=tenant_id,
            recipient_id=recipient_id,
            event_key=event_key[:255],
            category=category,
            priority=priority,
            title=title[:255],
            body=body,
            link=_safe_link(link),
            source_type=source_type,
            source_id=source_id,
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
        )
        self.db.add(row)
        self.db.flush()
        return row

    def mark_read(self, row: Notification, read: bool) -> Notification:
        row.read_at = utc_now() if read else None
        self.db.commit()
        self.db.refresh(row)
        return row

    def mark_all_read(self, tenant_id: UUID, recipient_id: UUID) -> int:
        updated = (
            self.db.query(Notification)
            .filter(
                Notification.tenant_id == tenant_id,
                Notification.recipient_id == recipient_id,
                Notification.read_at.is_(None),
            )
            .update({Notification.read_at: utc_now()}, synchronize_session=False)
        )
        self.db.commit()
        return updated


def _safe_link(link: str | None) -> str | None:
    if not link:
        return None
    if not link.startswith("/") or link.startswith("//"):
        return None
    return link[:500]
