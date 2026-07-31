import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.modules.activity.models import Activity
from app.modules.sales.models import (
    Company,
    Contact,
    Deal,
    Lead,
    NextAction,
    PipelineStage,
    ScoreSnapshot,
    Task,
)


MODEL_VERSION = "rules-v1"


@dataclass(frozen=True)
class ScoreResult:
    entity_type: str
    entity_id: UUID
    score: int
    previous_score: int | None
    grade: str
    factors: list[dict[str, Any]]
    forecast_probability: int | None
    model_version: str
    calculated_at: datetime

    @property
    def changed(self) -> bool:
        return self.previous_score != self.score


def _grade(score: int) -> str:
    if score >= 75:
        return "hot"
    if score >= 50:
        return "warm"
    return "cold"


def _factor(key: str, label: str, points: int, maximum: int, signal: str) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "points": points,
        "max_points": maximum,
        "signal": signal,
    }


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class ScoringService:
    def __init__(self, db: Session):
        self.db = db

    def recalculate_lead(
        self,
        lead: Lead,
        *,
        actor_id: UUID | None,
        reason: str,
        emit_automation: bool = True,
    ) -> ScoreResult:
        with self.db.no_autoflush:
            company = self.db.get(Company, lead.company_id)
            contact = self.db.get(Contact, lead.contact_id) if lead.contact_id else None
        factors: list[dict[str, Any]] = []

        source = str(lead.source or "").strip().lower()
        if source in {"referral", "recommendation", "demo", "inbound"}:
            source_points = 20
        elif source in {"website", "web", "form", "webinar", "event"}:
            source_points = 15
        elif source in {"outbound", "cold", "cold_call"}:
            source_points = 5
        else:
            source_points = 0
        factors.append(_factor("source", "Качество источника", source_points, 20, source or "не указан"))

        email_points = 12 if contact and contact.email else 0
        phone_points = 8 if contact and contact.phone else 0
        factors.append(_factor("contact_email", "Email контакта", email_points, 12, "есть" if email_points else "нет"))
        factors.append(_factor("contact_phone", "Телефон контакта", phone_points, 8, "есть" if phone_points else "нет"))

        website_points = 8 if company and company.website else 0
        industry_points = 7 if company and company.industry else 0
        factors.append(_factor("company_website", "Сайт компании", website_points, 8, "есть" if website_points else "нет"))
        factors.append(_factor("company_industry", "Отрасль компании", industry_points, 7, company.industry if company and company.industry else "не указана"))

        owner_points = 10 if lead.owner_id else 0
        factors.append(_factor("owner", "Ответственный назначен", owner_points, 10, "да" if owner_points else "нет"))

        status_points = {
            "qualified": 25,
            "converted": 25,
            "open": 10,
            "in_progress": 10,
            "new": 5,
            "disqualified": 0,
        }.get(str(lead.status or "").lower(), 5)
        factors.append(_factor("status", "Стадия квалификации", status_points, 25, lead.status))

        age_days = max(0, (datetime.now(timezone.utc) - (_utc(lead.created_at) or datetime.now(timezone.utc))).days)
        recency_points = 10 if age_days <= 7 else 5 if age_days <= 30 else 0
        factors.append(_factor("recency", "Актуальность лида", recency_points, 10, f"{age_days} дн."))

        score = max(0, min(100, sum(item["points"] for item in factors)))
        result = self._store(
            lead,
            entity_type="lead",
            score=score,
            factors=factors,
            forecast_probability=None,
            actor_id=actor_id,
            reason=reason,
        )
        if emit_automation and result.changed:
            self._emit_lead_change(lead, result, actor_id)
        return result

    def recalculate_deal(
        self,
        deal: Deal,
        *,
        actor_id: UUID | None,
        reason: str,
        emit_automation: bool = True,
    ) -> ScoreResult:
        now = datetime.now(timezone.utc)
        with self.db.no_autoflush:
            stage = self.db.get(PipelineStage, deal.stage_id)
            lead = self.db.get(Lead, deal.lead_id) if deal.lead_id else None
        factors: list[dict[str, Any]] = []

        stage_probability = max(0, min(100, int(deal.probability if deal.probability is not None else (stage.probability if stage else 0))))
        stage_points = round(stage_probability * 0.25)
        factors.append(_factor("stage", "Этап воронки", stage_points, 25, f"{stage_probability}%"))

        lead_score = int(lead.score or 0) if lead else 0
        qualification_points = round(lead_score * 0.15) if lead else 5
        factors.append(_factor("lead_quality", "Качество исходного лида", qualification_points, 15, f"{lead_score}%" if lead else "прямая сделка"))

        amount_points = 5 if deal.amount is not None and float(deal.amount) > 0 else 0
        factors.append(_factor("amount", "Сумма сделки", amount_points, 5, "указана" if amount_points else "не указана"))

        close_at = _utc(deal.expected_close_date)
        close_points = 10 if close_at and close_at >= now else 0
        close_signal = "не указана" if close_at is None else "актуальна" if close_points else "просрочена"
        factors.append(_factor("close_date", "Дата закрытия", close_points, 10, close_signal))

        with self.db.no_autoflush:
            has_open_action = bool(
                deal.next_action_id
                or deal.next_step
                or self.db.query(NextAction.id).filter(
                    NextAction.tenant_id == deal.tenant_id,
                    NextAction.deal_id == deal.id,
                    NextAction.status == "open",
                ).first()
                or self.db.query(Task.id).filter(
                    Task.tenant_id == deal.tenant_id,
                    Task.deal_id == deal.id,
                    Task.status.in_(("open", "in_progress")),
                    Task.deleted_at.is_(None),
                ).first()
            )
        action_points = 10 if has_open_action else 0
        factors.append(_factor("next_action", "Следующий шаг", action_points, 10, "есть" if has_open_action else "нет"))

        owner_points = 5 if deal.owner_id else 0
        factors.append(_factor("owner", "Ответственный назначен", owner_points, 5, "да" if owner_points else "нет"))

        with self.db.no_autoflush:
            last_activity = self.db.query(func.max(Activity.created_at)).filter(
                Activity.tenant_id == deal.tenant_id,
                Activity.deal_id == deal.id,
            ).scalar()
        last_activity_at = _utc(last_activity)
        inactive_days = (now - last_activity_at).days if last_activity_at else None
        activity_points = 15 if inactive_days is not None and inactive_days <= 7 else 8 if inactive_days is not None and inactive_days <= 30 else 0
        factors.append(_factor("activity", "Свежая активность", activity_points, 15, f"{inactive_days} дн. назад" if inactive_days is not None else "нет активности"))

        risk = str(deal.risk_level or "medium").lower()
        risk_points = {"low": 10, "medium": 5, "high": 0}.get(risk, 5)
        factors.append(_factor("risk", "Уровень риска", risk_points, 10, risk))

        discount = float(deal.discount_percent or 0)
        discount_points = 5 if discount <= 10 else 3 if discount <= 25 else 0
        factors.append(_factor("discount", "Размер скидки", discount_points, 5, f"{discount:g}%"))

        score = max(0, min(100, sum(item["points"] for item in factors)))
        if str(deal.status).lower() == "won":
            forecast_probability = 100
        elif str(deal.status).lower() in {"lost", "closed"}:
            forecast_probability = 0
        else:
            forecast_probability = max(0, min(100, round(stage_probability * 0.55 + score * 0.45)))
        result = self._store(
            deal,
            entity_type="deal",
            score=score,
            factors=factors,
            forecast_probability=forecast_probability,
            actor_id=actor_id,
            reason=reason,
        )
        if emit_automation and result.changed:
            self._emit_deal_change(deal, stage, result, actor_id)
        return result

    def history(self, tenant_id: UUID, entity_type: str, entity_id: UUID, limit: int = 20) -> list[ScoreSnapshot]:
        return (
            self.db.query(ScoreSnapshot)
            .filter(
                ScoreSnapshot.tenant_id == tenant_id,
                ScoreSnapshot.entity_type == entity_type,
                ScoreSnapshot.entity_id == entity_id,
            )
            .order_by(ScoreSnapshot.calculated_at.desc())
            .limit(limit)
            .all()
        )

    def _store(
        self,
        entity: Lead | Deal,
        *,
        entity_type: str,
        score: int,
        factors: list[dict[str, Any]],
        forecast_probability: int | None,
        actor_id: UUID | None,
        reason: str,
    ) -> ScoreResult:
        now = datetime.now(timezone.utc)
        previous_score = entity.score if entity_type == "lead" else entity.opportunity_score
        grade = _grade(score)
        factors_json = json.dumps(factors, ensure_ascii=False)
        if entity_type == "lead":
            entity.score = score
        else:
            entity.opportunity_score = score
            entity.scoring_probability = forecast_probability
        entity.score_grade = grade
        entity.score_factors_json = factors_json
        entity.score_model_version = MODEL_VERSION
        entity.score_updated_at = now
        snapshot = ScoreSnapshot(
            tenant_id=entity.tenant_id,
            entity_type=entity_type,
            entity_id=entity.id,
            score=score,
            previous_score=previous_score,
            grade=grade,
            factors_json=factors_json,
            forecast_probability=forecast_probability,
            model_version=MODEL_VERSION,
            calculation_reason=reason[:80],
            calculated_by_id=actor_id,
            calculated_at=now,
        )
        self.db.add(snapshot)
        self.db.flush()
        return ScoreResult(
            entity_type=entity_type,
            entity_id=entity.id,
            score=score,
            previous_score=previous_score,
            grade=grade,
            factors=factors,
            forecast_probability=forecast_probability,
            model_version=MODEL_VERSION,
            calculated_at=now,
        )

    def _emit_lead_change(self, lead: Lead, result: ScoreResult, actor_id: UUID | None) -> None:
        from app.modules.automation.service import AutomationEngine

        AutomationEngine(self.db).emit(
            tenant_id=lead.tenant_id,
            trigger_type="lead.score_changed",
            entity_type="lead",
            entity_id=lead.id,
            event_key=f"lead.score_changed:{lead.id}:{result.calculated_at.isoformat()}",
            context={
                "old_score": result.previous_score,
                "new_score": result.score,
                "score_delta": result.score - (result.previous_score or 0),
                "score_grade": result.grade,
                "source": lead.source,
                "status": lead.status,
                "owner_id": str(lead.owner_id) if lead.owner_id else None,
                "company_id": str(lead.company_id),
                "title": lead.title,
            },
            actor_id=actor_id,
        )

    def _emit_deal_change(
        self,
        deal: Deal,
        stage: PipelineStage | None,
        result: ScoreResult,
        actor_id: UUID | None,
    ) -> None:
        from app.modules.automation.service import AutomationEngine

        AutomationEngine(self.db).emit(
            tenant_id=deal.tenant_id,
            trigger_type="deal.score_changed",
            entity_type="deal",
            entity_id=deal.id,
            event_key=f"deal.score_changed:{deal.id}:{result.calculated_at.isoformat()}",
            context={
                "old_score": result.previous_score,
                "new_score": result.score,
                "score_delta": result.score - (result.previous_score or 0),
                "score_grade": result.grade,
                "forecast_probability": result.forecast_probability,
                "amount": float(deal.amount) if deal.amount is not None else None,
                "status": deal.status,
                "stage_id": str(deal.stage_id),
                "stage_name": stage.name if stage else None,
                "owner_id": str(deal.owner_id) if deal.owner_id else None,
                "company_id": str(deal.company_id),
                "title": deal.title,
            },
            actor_id=actor_id,
        )
