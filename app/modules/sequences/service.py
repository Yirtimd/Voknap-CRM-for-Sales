from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.modules.accounts.models import Membership
from app.modules.activity.service import ActivityService
from app.modules.communication.models import CommunicationEvent
from app.modules.communication.service import CommunicationService
from app.modules.connectors.jobs import IntegrationJobService
from app.modules.connectors.models import ConnectorAccount, IntegrationJob
from app.modules.sales.models import Company, Contact, Deal, Task
from app.modules.sequences.models import (
    Cadence,
    CadenceEnrollment,
    CadenceExecution,
    CadenceStep,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CadenceService:
    def __init__(self, db: Session):
        self.db = db

    def enroll(
        self,
        *,
        tenant_id: UUID,
        cadence_id: UUID,
        contact_id: UUID,
        deal_id: UUID | None,
        connector_account_id: UUID | None,
        actor_id: UUID,
    ) -> CadenceEnrollment:
        cadence = self._cadence(tenant_id, cadence_id)
        if not cadence.is_active:
            raise HTTPException(status_code=409, detail="Cadence is inactive")
        steps = self._steps(tenant_id, cadence.id)
        if not steps:
            raise HTTPException(status_code=409, detail="Cadence has no steps")
        contact = self._contact(tenant_id, contact_id)
        company = self._company(tenant_id, contact.company_id)
        deal = self._deal(tenant_id, deal_id) if deal_id else None
        if deal and deal.company_id != company.id:
            raise HTTPException(status_code=422, detail="Deal does not belong to contact company")
        owner_id = contact.owner_id or company.owner_id or actor_id
        self._active_member(tenant_id, owner_id)
        connector = self._connector(tenant_id, connector_account_id) if connector_account_id else None
        if any(step.step_type == "automatic_email" for step in steps):
            if connector is None:
                raise HTTPException(
                    status_code=422,
                    detail="Automatic email steps require a connected email account",
                )
            if not contact.email:
                raise HTTPException(
                    status_code=422,
                    detail="Contact email is required for automatic email steps",
                )
        existing = (
            self.db.query(CadenceEnrollment)
            .filter(
                CadenceEnrollment.tenant_id == tenant_id,
                CadenceEnrollment.cadence_id == cadence.id,
                CadenceEnrollment.contact_id == contact.id,
                CadenceEnrollment.status.in_(("active", "paused")),
            )
            .one_or_none()
        )
        if existing:
            raise HTTPException(status_code=409, detail="Contact is already enrolled")
        enrollment = CadenceEnrollment(
            tenant_id=tenant_id,
            cadence_id=cadence.id,
            contact_id=contact.id,
            company_id=company.id,
            deal_id=deal.id if deal else None,
            connector_account_id=connector.id if connector else None,
            owner_id=owner_id,
            enrolled_by_id=actor_id,
            next_run_at=utc_now() + timedelta(minutes=steps[0].delay_minutes),
        )
        self.db.add(enrollment)
        self.db.flush()
        ActivityService(self.db).create(
            tenant_id=tenant_id,
            company_id=company.id,
            contact_id=contact.id,
            deal_id=deal.id if deal else None,
            created_by=actor_id,
            activity_type="CADENCE",
            title=f"Контакт добавлен в sequence «{cadence.name}»",
            description=f"Первый шаг: {steps[0].title}",
            metadata={"cadence_id": str(cadence.id), "enrollment_id": str(enrollment.id)},
            commit=False,
        )
        self.db.commit()
        self.db.refresh(enrollment)
        return enrollment

    def pause(self, enrollment: CadenceEnrollment, actor_id: UUID, reason: str | None) -> None:
        if enrollment.status != "active":
            raise HTTPException(status_code=409, detail="Only active enrollment can be paused")
        enrollment.status = "paused"
        enrollment.stop_reason = reason
        enrollment.next_run_at = None
        self._activity(enrollment, actor_id, "Sequence приостановлена", reason)
        self.db.commit()

    def resume(self, enrollment: CadenceEnrollment, actor_id: UUID) -> None:
        if enrollment.status != "paused":
            raise HTTPException(status_code=409, detail="Only paused enrollment can be resumed")
        enrollment.status = "active"
        enrollment.stop_reason = None
        enrollment.next_run_at = utc_now()
        self._activity(enrollment, actor_id, "Sequence возобновлена")
        self.db.commit()

    def stop(self, enrollment: CadenceEnrollment, actor_id: UUID, reason: str | None) -> None:
        if enrollment.status not in {"active", "paused"}:
            raise HTTPException(status_code=409, detail="Enrollment is already final")
        enrollment.status = "stopped"
        enrollment.stop_reason = reason or "Остановлено пользователем"
        enrollment.stopped_by_id = actor_id
        enrollment.next_run_at = None
        self._activity(enrollment, actor_id, "Sequence остановлена", enrollment.stop_reason)
        self.db.commit()

    def process_due(self, tenant_id: UUID, limit: int = 100) -> tuple[int, int]:
        self._sync_email_jobs(tenant_id)
        now = utc_now()
        rows = (
            self.db.query(CadenceEnrollment)
            .filter(
                CadenceEnrollment.tenant_id == tenant_id,
                CadenceEnrollment.status == "active",
                CadenceEnrollment.next_run_at.is_not(None),
                CadenceEnrollment.next_run_at <= now,
            )
            .order_by(CadenceEnrollment.next_run_at, CadenceEnrollment.created_at)
            .limit(limit)
            .all()
        )
        executed = 0
        for enrollment in rows:
            if self._execute_next(enrollment):
                executed += 1
        return len(rows), executed

    def handle_reply(
        self,
        *,
        tenant_id: UUID,
        contact_id: UUID,
        event_id: UUID,
        actor_id: UUID | None,
    ) -> int:
        rows = (
            self.db.query(CadenceEnrollment)
            .filter(
                CadenceEnrollment.tenant_id == tenant_id,
                CadenceEnrollment.contact_id == contact_id,
                CadenceEnrollment.status.in_(("active", "paused")),
            )
            .all()
        )
        for enrollment in rows:
            enrollment.status = "replied"
            enrollment.next_run_at = None
            enrollment.stop_reason = "Получен входящий ответ"
            self._activity(
                enrollment,
                actor_id,
                "Sequence завершена: получен ответ",
                metadata={"communication_event_id": str(event_id)},
            )
        if rows:
            self.db.commit()
        return len(rows)

    def _execute_next(self, enrollment: CadenceEnrollment) -> bool:
        steps = self._steps(enrollment.tenant_id, enrollment.cadence_id)
        if enrollment.current_step >= len(steps):
            self._complete(enrollment)
            return False
        step = steps[enrollment.current_step]
        existing = (
            self.db.query(CadenceExecution)
            .filter(
                CadenceExecution.tenant_id == enrollment.tenant_id,
                CadenceExecution.enrollment_id == enrollment.id,
                CadenceExecution.step_id == step.id,
            )
            .one_or_none()
        )
        if existing:
            self._advance(enrollment, steps)
            self.db.commit()
            return False
        execution = CadenceExecution(
            tenant_id=enrollment.tenant_id,
            enrollment_id=enrollment.id,
            step_id=step.id,
            status="queued" if step.step_type == "automatic_email" else "succeeded",
            scheduled_at=enrollment.next_run_at or utc_now(),
        )
        self.db.add(execution)
        try:
            if step.step_type == "automatic_email":
                self._queue_email(enrollment, step, execution)
            else:
                task = self._create_task(enrollment, step)
                execution.task_id = task.id
                execution.executed_at = utc_now()
            enrollment.last_executed_at = utc_now()
            self._advance(enrollment, steps)
            self.db.commit()
            return True
        except Exception as error:
            self.db.rollback()
            enrollment = self.db.get(CadenceEnrollment, enrollment.id)
            step = self.db.get(CadenceStep, step.id)
            if enrollment and step:
                failure = CadenceExecution(
                    tenant_id=enrollment.tenant_id,
                    enrollment_id=enrollment.id,
                    step_id=step.id,
                    status="failed",
                    error=str(error)[:2000],
                    scheduled_at=enrollment.next_run_at or utc_now(),
                    executed_at=utc_now(),
                )
                self.db.add(failure)
                enrollment.status = "failed"
                enrollment.next_run_at = None
                enrollment.stop_reason = str(error)[:2000]
                self._activity(enrollment, None, "Ошибка выполнения sequence", str(error))
                self.db.commit()
            return False

    def _create_task(self, enrollment: CadenceEnrollment, step: CadenceStep) -> Task:
        contact = self._contact(enrollment.tenant_id, enrollment.contact_id)
        prefixes = {"call": "Позвонить", "manual_email": "Написать", "task": "Выполнить"}
        task = Task(
            tenant_id=enrollment.tenant_id,
            company_id=enrollment.company_id,
            deal_id=enrollment.deal_id,
            assigned_to_id=enrollment.owner_id,
            title=f"{prefixes[step.step_type]}: {self._render(step.title, contact)}",
            description=self._render(step.body, contact),
            priority=step.task_priority,
            due_at=utc_now(),
        )
        self.db.add(task)
        self.db.flush()
        self._activity(
            enrollment,
            enrollment.owner_id,
            f"Cadence создала задачу: {task.title}",
            task.description,
            {"task_id": str(task.id), "step_id": str(step.id), "step_type": step.step_type},
        )
        return task

    def _queue_email(
        self,
        enrollment: CadenceEnrollment,
        step: CadenceStep,
        execution: CadenceExecution,
    ) -> None:
        contact = self._contact(enrollment.tenant_id, enrollment.contact_id)
        if not contact.email or not enrollment.connector_account_id:
            raise ValueError("Automatic email requires contact email and connector account")
        job = IntegrationJobService(self.db).enqueue(
            tenant_id=enrollment.tenant_id,
            account_id=enrollment.connector_account_id,
            job_type="email.send",
            idempotency_key=f"cadence:{enrollment.id}:{step.id}",
            payload={
                "recipient": contact.email,
                "subject": self._render(step.title, contact),
                "body": self._render(step.body, contact) or "",
                "company_id": str(enrollment.company_id),
                "contact_id": str(enrollment.contact_id),
                "deal_id": str(enrollment.deal_id) if enrollment.deal_id else None,
                "cadence_enrollment_id": str(enrollment.id),
            },
            created_by_id=enrollment.owner_id,
        )
        execution.integration_job_id = job.id

    def _sync_email_jobs(self, tenant_id: UUID) -> None:
        queued = (
            self.db.query(CadenceExecution, IntegrationJob)
            .join(IntegrationJob, IntegrationJob.id == CadenceExecution.integration_job_id)
            .filter(
                CadenceExecution.tenant_id == tenant_id,
                CadenceExecution.status == "queued",
                IntegrationJob.status.in_(("succeeded", "dead")),
            )
            .all()
        )
        for execution, job in queued:
            enrollment = self.db.get(CadenceEnrollment, execution.enrollment_id)
            if job.status == "dead":
                execution.status = "failed"
                execution.error = job.last_error or "Email delivery failed"
                execution.executed_at = utc_now()
                if enrollment and enrollment.status in {"active", "completed"}:
                    enrollment.status = "failed"
                    enrollment.stop_reason = execution.error
                    enrollment.next_run_at = None
                    self._activity(enrollment, None, "Email sequence не отправлен", execution.error)
                continue
            result = json.loads(job.result_json or "{}")
            event_id = result.get("communication_event_id")
            if event_id:
                event = self.db.get(CommunicationEvent, UUID(event_id))
                if event:
                    CommunicationService(self.db).create_activity(tenant_id, event.id, job.created_by_id)
                    execution.communication_event_id = event.id
            execution.status = "succeeded"
            execution.executed_at = utc_now()
        if queued:
            self.db.commit()

    def _advance(self, enrollment: CadenceEnrollment, steps: list[CadenceStep]) -> None:
        enrollment.current_step += 1
        if enrollment.current_step >= len(steps):
            self._complete(enrollment)
            return
        next_step = steps[enrollment.current_step]
        enrollment.next_run_at = utc_now() + timedelta(minutes=next_step.delay_minutes)

    def _complete(self, enrollment: CadenceEnrollment) -> None:
        enrollment.status = "completed"
        enrollment.next_run_at = None
        enrollment.stop_reason = None
        self._activity(enrollment, None, "Sequence завершена")

    def _activity(
        self,
        enrollment: CadenceEnrollment,
        actor_id: UUID | None,
        title: str,
        description: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        ActivityService(self.db).create(
            tenant_id=enrollment.tenant_id,
            company_id=enrollment.company_id,
            contact_id=enrollment.contact_id,
            deal_id=enrollment.deal_id,
            created_by=actor_id,
            activity_type="CADENCE",
            title=title,
            description=description,
            metadata={
                "cadence_id": str(enrollment.cadence_id),
                "enrollment_id": str(enrollment.id),
                **(metadata or {}),
            },
            commit=False,
        )

    def _render(self, value: str | None, contact: Contact) -> str | None:
        if value is None:
            return None
        company = self._company(contact.tenant_id, contact.company_id)
        replacements = {
            "{{contact.name}}": contact.name,
            "{{contact.email}}": contact.email or "",
            "{{company.name}}": company.name,
        }
        for key, replacement in replacements.items():
            value = value.replace(key, replacement)
        return value

    def _steps(self, tenant_id: UUID, cadence_id: UUID) -> list[CadenceStep]:
        return (
            self.db.query(CadenceStep)
            .filter(CadenceStep.tenant_id == tenant_id, CadenceStep.cadence_id == cadence_id)
            .order_by(CadenceStep.position)
            .all()
        )

    def _cadence(self, tenant_id: UUID, cadence_id: UUID) -> Cadence:
        row = self.db.query(Cadence).filter(Cadence.tenant_id == tenant_id, Cadence.id == cadence_id).one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Cadence not found")
        return row

    def _contact(self, tenant_id: UUID, contact_id: UUID) -> Contact:
        row = self.db.query(Contact).filter(Contact.tenant_id == tenant_id, Contact.id == contact_id).one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Contact not found")
        return row

    def _company(self, tenant_id: UUID, company_id: UUID) -> Company:
        row = self.db.query(Company).filter(Company.tenant_id == tenant_id, Company.id == company_id).one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Company not found")
        return row

    def _deal(self, tenant_id: UUID, deal_id: UUID) -> Deal:
        row = self.db.query(Deal).filter(Deal.tenant_id == tenant_id, Deal.id == deal_id).one_or_none()
        if row is None:
            raise HTTPException(status_code=404, detail="Deal not found")
        return row

    def _connector(self, tenant_id: UUID, account_id: UUID) -> ConnectorAccount:
        row = (
            self.db.query(ConnectorAccount)
            .filter(
                ConnectorAccount.tenant_id == tenant_id,
                ConnectorAccount.id == account_id,
                ConnectorAccount.connector_code == "email",
                ConnectorAccount.status == "connected",
            )
            .one_or_none()
        )
        if row is None:
            raise HTTPException(status_code=422, detail="Connected email account not found")
        return row

    def _active_member(self, tenant_id: UUID, user_id: UUID) -> None:
        exists = (
            self.db.query(Membership.id)
            .filter(
                Membership.tenant_id == tenant_id,
                Membership.user_id == user_id,
                Membership.is_active.is_(True),
            )
            .first()
        )
        if not exists:
            raise HTTPException(status_code=422, detail="Enrollment owner must be active member")
