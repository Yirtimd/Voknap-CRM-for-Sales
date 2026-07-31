import hashlib
import hmac
import ipaddress
import json
import socket
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse
from uuid import UUID

import httpx
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.modules.communication.models import CommunicationEvent
from app.modules.communication.schemas import CommunicationEventCreate
from app.modules.communication.service import CommunicationService
from app.modules.connectors.models import (
    ConnectorAccount,
    IntegrationJob,
    WebhookEndpoint,
)
from app.modules.connectors.providers import (
    create_calendar_event,
    fetch_calendar_events,
    refresh_access_token,
    send_smtp_email,
)
from app.modules.sales.models import Company, Contact, Lead


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IntegrationJobService:
    def __init__(self, db: Session):
        self.db = db

    def enqueue(
        self,
        *,
        tenant_id: UUID,
        job_type: str,
        idempotency_key: str,
        payload: dict,
        account_id: UUID | None = None,
        created_by_id: UUID | None = None,
        max_attempts: int | None = None,
    ) -> IntegrationJob:
        existing = (
            self.db.query(IntegrationJob)
            .filter(
                IntegrationJob.tenant_id == tenant_id,
                IntegrationJob.idempotency_key == idempotency_key,
            )
            .one_or_none()
        )
        if existing:
            return existing
        job = IntegrationJob(
            tenant_id=tenant_id,
            account_id=account_id,
            job_type=job_type,
            idempotency_key=idempotency_key,
            payload_json=json.dumps(payload),
            max_attempts=max_attempts or settings.integration_job_max_attempts,
            created_by_id=created_by_id,
        )
        try:
            with self.db.begin_nested():
                self.db.add(job)
                self.db.flush()
        except IntegrityError:
            existing = (
                self.db.query(IntegrationJob)
                .filter(
                    IntegrationJob.tenant_id == tenant_id,
                    IntegrationJob.idempotency_key == idempotency_key,
                )
                .one()
            )
            return existing
        self.db.commit()
        self.db.refresh(job)
        return job

    def list_jobs(self, tenant_id: UUID, status: str | None = None) -> list[IntegrationJob]:
        query = self.db.query(IntegrationJob).filter(IntegrationJob.tenant_id == tenant_id)
        if status:
            query = query.filter(IntegrationJob.status == status)
        return query.order_by(IntegrationJob.created_at.desc()).limit(100).all()

    def replay(self, tenant_id: UUID, job_id: UUID) -> IntegrationJob | None:
        job = (
            self.db.query(IntegrationJob)
            .filter(IntegrationJob.tenant_id == tenant_id, IntegrationJob.id == job_id)
            .one_or_none()
        )
        if not job:
            return None
        if job.status != "dead":
            return job
        job.status = "pending"
        job.attempt = 0
        job.available_at = utc_now()
        job.locked_at = None
        job.completed_at = None
        job.last_error = None
        job.updated_at = utc_now()
        self.db.commit()
        self.db.refresh(job)
        return job

    def process_available(self, limit: int | None = None) -> int:
        self._recover_stale_jobs()
        processed = 0
        batch_size = limit or settings.integration_worker_batch_size
        while processed < batch_size:
            job = self._claim_one()
            if job is None:
                break
            self._execute(job)
            processed += 1
        return processed

    def _recover_stale_jobs(self) -> None:
        stale_before = utc_now() - timedelta(minutes=15)
        stale = (
            self.db.query(IntegrationJob)
            .filter(
                IntegrationJob.status == "running",
                IntegrationJob.locked_at < stale_before,
            )
            .all()
        )
        for job in stale:
            job.status = "retry"
            job.available_at = utc_now()
            job.locked_at = None
            job.last_error = "Worker lease expired; job returned to retry queue"
            job.updated_at = utc_now()
        if stale:
            self.db.commit()

    def _claim_one(self) -> IntegrationJob | None:
        job = (
            self.db.query(IntegrationJob)
            .filter(
                IntegrationJob.status.in_(("pending", "retry")),
                IntegrationJob.available_at <= utc_now(),
            )
            .order_by(IntegrationJob.available_at, IntegrationJob.created_at)
            .with_for_update(skip_locked=True)
            .first()
        )
        if not job:
            return None
        job.status = "running"
        job.attempt += 1
        job.locked_at = utc_now()
        job.updated_at = utc_now()
        self.db.commit()
        self.db.refresh(job)
        return job

    def _execute(self, job: IntegrationJob) -> None:
        try:
            result = self._dispatch(job)
            job.status = "succeeded"
            job.result_json = json.dumps(result)
            job.completed_at = utc_now()
            job.last_error = None
        except Exception as error:
            logs = json.loads(job.error_log_json or "[]")
            logs.append(
                {
                    "attempt": job.attempt,
                    "at": utc_now().isoformat(),
                    "type": error.__class__.__name__,
                    "message": str(error)[:2000],
                }
            )
            job.error_log_json = json.dumps(logs)
            job.last_error = str(error)[:4000]
            if job.attempt >= job.max_attempts:
                job.status = "dead"
                job.completed_at = utc_now()
            else:
                job.status = "retry"
                delay_minutes = min(2 ** max(job.attempt - 1, 0), 60)
                job.available_at = utc_now() + timedelta(minutes=delay_minutes)
        job.locked_at = None
        job.updated_at = utc_now()
        self.db.commit()

    def _dispatch(self, job: IntegrationJob) -> dict:
        payload = json.loads(job.payload_json or "{}")
        if job.job_type == "email.sync":
            return self._sync_calendar_or_email(job, email=True)
        if job.job_type == "email.send":
            return self._send_email(job, payload)
        if job.job_type == "calendar.sync":
            return self._sync_calendar_or_email(job, email=False)
        if job.job_type == "calendar.create":
            return self._create_calendar_event(job, payload)
        if job.job_type == "webhook.deliver":
            return self._deliver_webhook(payload)
        if job.job_type == "contacts.import":
            return self._import_contacts(job.tenant_id, payload)
        raise ValueError(f"Unknown integration job type: {job.job_type}")

    def _sync_calendar_or_email(self, job: IntegrationJob, *, email: bool) -> dict:
        if not job.account_id:
            raise ValueError("Connector account is required")
        account = self.db.get(ConnectorAccount, job.account_id)
        if not account or account.tenant_id != job.tenant_id:
            raise ValueError("Connector account not found")
        if email:
            from app.modules.connectors.service import ConnectorService

            run = ConnectorService(self.db).sync_account(job.tenant_id, account.id, {})
            if run.status in {"failed", "retry_scheduled"}:
                raise RuntimeError(run.message or "Email sync failed")
            return {"run_id": str(run.id), "created": run.created_count}
        return self._sync_calendar(job.tenant_id, account)

    def _sync_calendar(self, tenant_id: UUID, account: ConnectorAccount) -> dict:
        from app.modules.connectors.service import ConnectorService

        connector_service = ConnectorService(self.db)
        credentials = connector_service._decrypt_credentials(account.credentials_json)
        credentials = refresh_access_token(account.connector_code, credentials)
        account.credentials_json = connector_service._encrypt_credentials(credentials)
        events, cursor = fetch_calendar_events(
            account.connector_code,
            credentials,
            account.sync_cursor,
        )
        created = 0
        updated = 0
        for item in events:
            provider_id = str(item.get("id") or "")
            if not provider_id:
                continue
            external_id = f"{account.id}:{provider_id}"
            existing = (
                self.db.query(CommunicationEvent)
                .filter(
                    CommunicationEvent.tenant_id == tenant_id,
                    CommunicationEvent.channel == "calendar",
                    CommunicationEvent.external_id == external_id,
                )
                .one_or_none()
            )
            if item.get("deleted"):
                if existing:
                    existing.status = "cancelled"
                    existing.updated_at = utc_now()
                    updated += 1
                continue
            metadata = {
                "starts_at": item.get("starts_at"),
                "ends_at": item.get("ends_at"),
                "attendees": item.get("attendees") or [],
                "html_link": item.get("html_link"),
                "provider": account.connector_code,
            }
            if existing:
                existing.subject = item["title"]
                existing.body = item.get("description")
                existing.sender = item.get("organizer")
                existing.metadata_json = json.dumps(metadata)
                existing.updated_at = utc_now()
                updated += 1
            else:
                CommunicationService(self.db).create(
                    tenant_id=tenant_id,
                    created_by=None,
                    payload=CommunicationEventCreate(
                        channel="calendar",
                        direction="inbound",
                        external_id=external_id,
                        sender=item.get("organizer"),
                        recipient=", ".join(item.get("attendees") or []) or None,
                        subject=item["title"],
                        body=item.get("description"),
                        connector_account_id=account.id,
                        metadata=metadata,
                    ),
                )
                created += 1
        account.sync_cursor = cursor
        account.last_sync_at = utc_now()
        self.db.commit()
        return {"created": created, "updated": updated, "cursor_saved": True}

    def _send_email(self, job: IntegrationJob, payload: dict) -> dict:
        if not job.account_id:
            raise ValueError("Email account is required")
        account = self.db.get(ConnectorAccount, job.account_id)
        if not account or account.tenant_id != job.tenant_id or account.connector_code != "email":
            raise ValueError("Email account not found")
        from app.modules.connectors.service import ConnectorService

        service = ConnectorService(self.db)
        credentials = service._decrypt_credentials(account.credentials_json)
        account_settings = json.loads(account.settings_json or "{}")
        external_id = send_smtp_email(credentials, account_settings, payload)
        event = CommunicationService(self.db).create(
            tenant_id=job.tenant_id,
            created_by=job.created_by_id,
            payload=CommunicationEventCreate(
                channel="email",
                direction="outbound",
                external_id=external_id or f"job:{job.id}",
                sender=account_settings.get("from_email") or credentials.get("username"),
                recipient=payload["recipient"],
                subject=payload["subject"],
                body=payload.get("body"),
                company_id=UUID(payload["company_id"]) if payload.get("company_id") else None,
                contact_id=UUID(payload["contact_id"]) if payload.get("contact_id") else None,
                deal_id=UUID(payload["deal_id"]) if payload.get("deal_id") else None,
                connector_account_id=account.id,
                metadata={
                    "integration_job_id": str(job.id),
                    "cadence_enrollment_id": payload.get("cadence_enrollment_id"),
                },
            ),
        )
        return {"communication_event_id": str(event.id)}

    def _create_calendar_event(self, job: IntegrationJob, payload: dict) -> dict:
        if not job.account_id:
            raise ValueError("Calendar account is required")
        account = self.db.get(ConnectorAccount, job.account_id)
        if not account or account.tenant_id != job.tenant_id:
            raise ValueError("Calendar account not found")
        from app.modules.connectors.service import ConnectorService

        service = ConnectorService(self.db)
        credentials = service._decrypt_credentials(account.credentials_json)
        credentials = refresh_access_token(account.connector_code, credentials)
        account.credentials_json = service._encrypt_credentials(credentials)
        event_data = create_calendar_event(account.connector_code, credentials, payload)
        event = CommunicationService(self.db).create(
            tenant_id=job.tenant_id,
            created_by=job.created_by_id,
            payload=CommunicationEventCreate(
                channel="calendar",
                direction="outbound",
                external_id=f"{account.id}:{event_data['id']}",
                recipient=", ".join(event_data.get("attendees") or []) or None,
                subject=event_data["title"],
                body=event_data.get("description"),
                connector_account_id=account.id,
                metadata={
                    "starts_at": event_data.get("starts_at"),
                    "ends_at": event_data.get("ends_at"),
                    "integration_job_id": str(job.id),
                },
            ),
        )
        return {"communication_event_id": str(event.id), "provider_event_id": event_data["id"]}

    def _deliver_webhook(self, payload: dict) -> dict:
        endpoint = self.db.get(WebhookEndpoint, UUID(payload["endpoint_id"]))
        if not endpoint or not endpoint.is_active:
            raise ValueError("Webhook endpoint is inactive or missing")
        validate_webhook_url(endpoint.url)
        from app.modules.connectors.service import ConnectorService

        secret = ConnectorService(self.db)._decrypt_secret(endpoint.secret_encrypted)
        body = json.dumps(payload["event"], separators=(",", ":"), sort_keys=True).encode()
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        response = httpx.post(
            endpoint.url,
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Voknap-Event": payload["event"]["type"],
                "X-Voknap-Delivery": payload["event"]["id"],
                "X-Voknap-Signature-256": f"sha256={signature}",
            },
            timeout=15.0,
            follow_redirects=False,
        )
        response.raise_for_status()
        return {"status_code": response.status_code}

    def _import_contacts(self, tenant_id: UUID, payload: dict) -> dict:
        created = 0
        failed = 0
        for item in payload.get("rows", []):
            try:
                company_name = item.get("company_name") or "Imported company"
                company = (
                    self.db.query(Company)
                    .filter(Company.tenant_id == tenant_id, Company.name == company_name)
                    .one_or_none()
                )
                if not company:
                    company = Company(tenant_id=tenant_id, name=company_name)
                    self.db.add(company)
                    self.db.flush()
                contact = Contact(
                    tenant_id=tenant_id,
                    company_id=company.id,
                    name=item.get("name") or item.get("email"),
                    phone=item.get("phone") or None,
                    email=item.get("email") or None,
                    company_name=company.name,
                )
                self.db.add(contact)
                self.db.flush()
                self.db.add(
                    Lead(
                        tenant_id=tenant_id,
                        company_id=company.id,
                        contact_id=contact.id,
                        title=item.get("lead_title") or f"Лид: {contact.name}",
                        source=item.get("source") or "import",
                        status="new",
                    )
                )
                created += 1
            except Exception:
                failed += 1
        self.db.commit()
        return {"created": created, "failed": failed}


def publish_webhook_event(
    db: Session,
    *,
    tenant_id: UUID,
    event_type: str,
    data: dict,
    actor_id: UUID | None,
) -> int:
    endpoints = (
        db.query(WebhookEndpoint)
        .filter(WebhookEndpoint.tenant_id == tenant_id, WebhookEndpoint.is_active.is_(True))
        .all()
    )
    event_id = hashlib.sha256(
        f"{tenant_id}:{event_type}:{json.dumps(data, sort_keys=True)}".encode()
    ).hexdigest()[:32]
    event = {
        "id": event_id,
        "type": event_type,
        "created_at": utc_now().isoformat(),
        "tenant_id": str(tenant_id),
        "data": data,
    }
    queued = 0
    service = IntegrationJobService(db)
    for endpoint in endpoints:
        if event_type not in json.loads(endpoint.event_types_json or "[]"):
            continue
        service.enqueue(
            tenant_id=tenant_id,
            job_type="webhook.deliver",
            idempotency_key=f"webhook:{endpoint.id}:{event_id}",
            payload={"endpoint_id": str(endpoint.id), "event": event},
            created_by_id=actor_id,
        )
        queued += 1
    return queued


def validate_webhook_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError("Webhook URL must use HTTPS")
    if settings.webhook_allow_private_networks:
        return
    try:
        addresses = {
            item[4][0]
            for item in socket.getaddrinfo(parsed.hostname, parsed.port or 443, type=socket.SOCK_STREAM)
        }
    except socket.gaierror as error:
        raise ValueError("Webhook hostname cannot be resolved") from error
    for value in addresses:
        address = ipaddress.ip_address(value)
        if not address.is_global:
            raise ValueError("Webhook URL cannot target a private or local network")
