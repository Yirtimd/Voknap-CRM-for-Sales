from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel


class NotificationResponse(BaseModel):
    id: UUID
    category: str
    priority: str
    title: str
    body: str | None
    link: str | None
    source_type: str | None
    source_id: UUID | None
    metadata: dict[str, Any]
    read_at: datetime | None
    created_at: datetime


class NotificationSummary(BaseModel):
    unread_count: int
    critical_count: int


class NotificationReadUpdate(BaseModel):
    read: bool = True


NotificationCategory = Literal["automation", "approval", "task", "communication", "system"]
