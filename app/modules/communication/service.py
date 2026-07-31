from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.modules.activity.service import ActivityService
from app.modules.automation.service import AutomationEngine
from app.modules.communication.models import CommunicationEvent
from app.modules.communication.schemas import CommunicationEventCreate, CommunicationEventLink
from app.modules.sales.models import Company, Contact, Deal
from app.modules.sales.scoring import ScoringService


class CommunicationService:
    def __init__(self, db: Session):
        self.db = db

    def list(
        self,
        tenant_id: UUID,
        channel: str | None = None,
        status: str | None = None,
        company_id: UUID | None = None,
        limit: int = 100,
    ) -> list[CommunicationEvent]:
        query = self.db.query(CommunicationEvent).filter(CommunicationEvent.tenant_id == tenant_id)
        if channel:
            query = query.filter(CommunicationEvent.channel == channel)
        if status:
            query = query.filter(CommunicationEvent.status == status)
        if company_id:
            query = query.filter(CommunicationEvent.company_id == company_id)
        return query.order_by(CommunicationEvent.occurred_at.desc(), CommunicationEvent.created_at.desc()).limit(limit).all()

    def create(self, tenant_id: UUID, created_by: UUID | None, payload: CommunicationEventCreate) -> CommunicationEvent:
        existing = None
        if payload.external_id:
            existing = (
                self.db.query(CommunicationEvent)
                .filter(
                    CommunicationEvent.tenant_id == tenant_id,
                    CommunicationEvent.channel == payload.channel,
                    CommunicationEvent.external_id == payload.external_id,
                )
                .one_or_none()
            )
        if existing:
            return existing

        company_id, contact_id, deal_id = self._resolve_links(
            tenant_id=tenant_id,
            company_id=payload.company_id,
            contact_id=payload.contact_id,
            deal_id=payload.deal_id,
            sender=payload.sender,
            body=payload.body,
            subject=payload.subject,
        )
        event = CommunicationEvent(
            tenant_id=tenant_id,
            company_id=company_id,
            contact_id=contact_id,
            deal_id=deal_id,
            connector_account_id=payload.connector_account_id,
            channel=payload.channel,
            direction=payload.direction,
            status="linked" if company_id else "new",
            external_id=payload.external_id,
            sender=payload.sender,
            recipient=payload.recipient,
            occurred_at=payload.occurred_at or datetime.now(timezone.utc),
            subject=payload.subject,
            body=payload.body,
            ai_summary=None,
            metadata_json=json.dumps(payload.metadata or {}, ensure_ascii=False),
            created_by=created_by,
        )
        self.db.add(event)
        self.db.flush()
        if event.direction == "inbound" and event.contact_id:
            from app.modules.sequences.service import CadenceService

            CadenceService(self.db).handle_reply(
                tenant_id=tenant_id,
                contact_id=event.contact_id,
                event_id=event.id,
                actor_id=created_by,
            )
        AutomationEngine(self.db).emit(
            tenant_id=tenant_id,
            trigger_type="communication.created",
            entity_type="communication",
            entity_id=event.id,
            event_key=f"communication.created:{event.id}",
            context={
                "channel": event.channel,
                "direction": event.direction,
                "status": event.status,
                "sender": event.sender,
                "recipient": event.recipient,
                "company_id": str(event.company_id) if event.company_id else None,
                "contact_id": str(event.contact_id) if event.contact_id else None,
                "deal_id": str(event.deal_id) if event.deal_id else None,
                "subject": event.subject,
            },
            actor_id=created_by,
        )
        self.db.commit()
        self.db.refresh(event)
        return event

    def ingest(
        self,
        tenant_id: UUID,
        created_by: UUID | None,
        channel: str,
        messages: list[CommunicationEventCreate],
    ) -> list[CommunicationEvent]:
        events = []
        for message in messages:
            normalized = message.model_copy(update={"channel": message.channel or channel})
            events.append(self.create(tenant_id=tenant_id, created_by=created_by, payload=normalized))
        return events

    def link(self, tenant_id: UUID, event_id: UUID, payload: CommunicationEventLink) -> CommunicationEvent | None:
        event = self._get_event(tenant_id, event_id)
        if not event:
            return None

        company = None
        if payload.company_id:
            company = self.db.query(Company).filter(Company.tenant_id == tenant_id, Company.id == payload.company_id).one_or_none()
            if company is None:
                raise ValueError("Company does not belong to current workspace")

        contact = None
        if payload.contact_id:
            contact = self.db.query(Contact).filter(Contact.tenant_id == tenant_id, Contact.id == payload.contact_id).one_or_none()
            if contact is None:
                raise ValueError("Contact does not belong to current workspace")
            if company and contact.company_id != company.id:
                raise ValueError("Contact does not belong to selected company")
            if company is None:
                company = self.db.query(Company).filter(Company.tenant_id == tenant_id, Company.id == contact.company_id).one()

        deal = None
        if payload.deal_id:
            deal = self.db.query(Deal).filter(Deal.tenant_id == tenant_id, Deal.id == payload.deal_id).one_or_none()
            if deal is None:
                raise ValueError("Deal does not belong to current workspace")
            if company and deal.company_id != company.id:
                raise ValueError("Deal does not belong to selected company")
            if company is None:
                company = self.db.query(Company).filter(Company.tenant_id == tenant_id, Company.id == deal.company_id).one()

        event.company_id = company.id if company else None
        event.contact_id = contact.id if contact else None
        event.deal_id = deal.id if deal else None
        event.status = "linked" if company else "new"
        event.updated_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(event)
        return event

    def create_activity(self, tenant_id: UUID, event_id: UUID, created_by: UUID | None) -> CommunicationEvent | None:
        event = self._get_event(tenant_id, event_id)
        if not event:
            return None
        if not event.company_id:
            return event
        if event.activity_id:
            event.status = "activity_created"
            self.db.commit()
            self.db.refresh(event)
            return event

        activity_type = self._activity_type(event.channel)
        activity = ActivityService(self.db).create(
            tenant_id=tenant_id,
            company_id=event.company_id,
            contact_id=event.contact_id,
            deal_id=event.deal_id,
            created_by=created_by,
            activity_type=activity_type,
            channel=event.channel,
            title=event.subject,
            description=event.body,
            metadata={
                "source": "communication_hub",
                "communication_event_id": str(event.id),
                "sender": event.sender,
                "recipient": event.recipient,
                "external_id": event.external_id,
            },
        )
        event.activity_id = activity.id
        event.status = "activity_created"
        event.updated_at = datetime.now(timezone.utc)
        if event.deal_id:
            deal = self.db.query(Deal).filter(
                Deal.tenant_id == tenant_id,
                Deal.id == event.deal_id,
            ).one()
            ScoringService(self.db).recalculate_deal(
                deal,
                actor_id=created_by,
                reason="communication_activity_created",
            )
        self.db.commit()
        self.db.refresh(event)
        return event

    def _get_event(self, tenant_id: UUID, event_id: UUID) -> CommunicationEvent | None:
        return (
            self.db.query(CommunicationEvent)
            .filter(CommunicationEvent.tenant_id == tenant_id, CommunicationEvent.id == event_id)
            .one_or_none()
        )

    def _resolve_links(
        self,
        tenant_id: UUID,
        company_id: UUID | None,
        contact_id: UUID | None,
        deal_id: UUID | None,
        sender: str | None,
        body: str | None,
        subject: str,
    ) -> tuple[UUID | None, UUID | None, UUID | None]:
        contact = None
        if contact_id:
            contact = self.db.query(Contact).filter(Contact.tenant_id == tenant_id, Contact.id == contact_id).one_or_none()
        if not contact and sender:
            contact = self._find_contact_by_sender(tenant_id, sender)

        company = None
        if company_id:
            company = self.db.query(Company).filter(Company.tenant_id == tenant_id, Company.id == company_id).one_or_none()
        if not company and contact:
            company = self.db.query(Company).filter(Company.tenant_id == tenant_id, Company.id == contact.company_id).one_or_none()
        if not company:
            company = self._find_company_by_text(tenant_id, f"{subject} {body or ''}")

        deal = None
        if deal_id:
            deal = self.db.query(Deal).filter(Deal.tenant_id == tenant_id, Deal.id == deal_id).one_or_none()
        if not deal and company:
            deal = (
                self.db.query(Deal)
                .filter(Deal.tenant_id == tenant_id, Deal.company_id == company.id, Deal.status == "open")
                .order_by(Deal.created_at.desc())
                .first()
            )

        return company.id if company else None, contact.id if contact else None, deal.id if deal else None

    def _find_contact_by_sender(self, tenant_id: UUID, sender: str) -> Contact | None:
        email = self._extract_email(sender)
        phone = self._normalize_phone(sender)
        query = self.db.query(Contact).filter(Contact.tenant_id == tenant_id)
        if email and phone:
            return query.filter(or_(Contact.email == email, Contact.phone.like(f"%{phone[-7:]}%"))).first()
        if email:
            return query.filter(Contact.email == email).first()
        if phone:
            return query.filter(Contact.phone.like(f"%{phone[-7:]}%")).first()
        return None

    def _find_company_by_text(self, tenant_id: UUID, text: str) -> Company | None:
        companies = self.db.query(Company).filter(Company.tenant_id == tenant_id).limit(200).all()
        lowered = text.lower()
        for company in companies:
            if company.name.lower() in lowered:
                return company
        return None

    def _activity_type(self, channel: str) -> str:
        return {
            "email": "EMAIL",
            "call": "CALL",
            "calendar": "MEETING",
            "meeting": "MEETING",
            "telegram": "COMMENT",
            "whatsapp": "COMMENT",
        }.get(channel, "COMMENT")

    def _extract_email(self, value: str) -> str | None:
        match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", value.lower())
        return match.group(0) if match else None

    def _normalize_phone(self, value: str) -> str | None:
        digits = re.sub(r"\D", "", value)
        return digits if len(digits) >= 7 else None
