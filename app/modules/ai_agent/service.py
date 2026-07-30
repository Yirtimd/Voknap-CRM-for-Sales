import json
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.activity.service import ActivityService
from app.modules.ai_agent.models import AgentAction, AgentMessage
from app.modules.analytics.service import AnalyticsService
from app.modules.knowledge.service import KnowledgeService
from app.modules.knowledge.models import KnowledgeDocument
from app.modules.sales.models import Company, Contact, CustomerInsight, Deal, Lead, NextAction, PipelineStage, Task
from app.modules.sales.stages import stage_label_ru


@dataclass
class AgentChatResult:
    answer: str
    actions: list[AgentAction]
    sources: list[dict]
    message: AgentMessage
    query_id: UUID | None
    intent: str
    context: dict


class AgentService:
    def __init__(self, db: Session):
        self.db = db
        self.knowledge_service = KnowledgeService(db)

    def chat(
        self,
        tenant_id: UUID,
        user_id: UUID,
        message: str,
        context_type: str = "workspace",
        company_id: UUID | None = None,
        deal_id: UUID | None = None,
        document_id: UUID | None = None,
        include_global: bool = False,
        page_path: str | None = None,
    ) -> AgentChatResult:
        context = {
            "type": context_type,
            "company_id": str(company_id) if company_id else None,
            "deal_id": str(deal_id) if deal_id else None,
            "document_id": str(document_id) if document_id else None,
            "include_global": include_global,
            "page_path": page_path,
        }
        self._save_message(
            tenant_id,
            user_id,
            "user",
            message,
            intent="request",
            context=context,
        )

        lowered = message.lower()
        actions: list[AgentAction] = []
        sources: list[dict] = []
        query_id: UUID | None = None

        if self._looks_like_task_request(lowered):
            intent = "create_task"
            action = self._propose_task(tenant_id, user_id, message)
            if action is None:
                answer = "Для создания задачи нужна компания или сделка. Укажи название сделки или оставь в workspace одну компанию."
            else:
                actions.append(action)
                answer = "Могу создать задачу. Проверь предложение и подтверди действие."
        elif self._looks_like_deal_move_request(lowered):
            intent = "move_deal"
            action = self._propose_deal_move(tenant_id, user_id, message)
            if action is None:
                answer = "Не нашла подходящую сделку или этап. Укажи название сделки и этап точнее."
            else:
                actions.append(action)
                answer = "Могу перенести сделку. Проверь предложение и подтверди действие."
        elif self._looks_like_summary_request(lowered):
            intent = "crm_summary"
            answer = self._summarize_crm(tenant_id)
        else:
            intent = "knowledge"
            answer, sources, query_id, context = self._answer_from_knowledge(
                tenant_id,
                user_id,
                message,
                context_type=context_type,
                company_id=company_id,
                deal_id=deal_id,
                document_id=document_id,
                include_global=include_global,
                page_path=page_path,
            )

        assistant_message = self._save_message(
            tenant_id,
            user_id,
            "assistant",
            answer,
            intent=intent,
            context=context,
            sources=sources,
            knowledge_query_id=query_id,
        )
        return AgentChatResult(
            answer=answer,
            actions=actions,
            sources=sources,
            message=assistant_message,
            query_id=query_id,
            intent=intent,
            context=context,
        )

    def list_history(self, tenant_id: UUID, limit: int = 30) -> list[AgentMessage]:
        return (
            self.db.query(AgentMessage)
            .filter(AgentMessage.tenant_id == tenant_id)
            .order_by(AgentMessage.created_at.desc())
            .limit(limit)
            .all()
        )

    def list_actions(self, tenant_id: UUID) -> list[AgentAction]:
        return (
            self.db.query(AgentAction)
            .filter(AgentAction.tenant_id == tenant_id)
            .order_by(AgentAction.created_at.desc())
            .limit(30)
            .all()
        )

    def home_copilot(self, tenant_id: UUID) -> dict:
        now = datetime.now(timezone.utc)
        overview = AnalyticsService(self.db).overview(
            tenant_id=tenant_id,
            forecast_days=90,
            stuck_days=14,
            activity_days=30,
        )
        risk_item = overview.risk_map.deals[0] if overview.risk_map.deals else None
        if risk_item is None:
            company = (
                self.db.query(Company)
                .filter(Company.tenant_id == tenant_id)
                .order_by(Company.created_at.asc())
                .first()
            )
            return {
                "generated_at": now,
                "source": "backend_copilot",
                "title": "Создать первую приоритетную сделку",
                "rationale": "Backend copilot не нашёл открытых сделок для ранжирования.",
                "company_id": company.id if company else None,
                "company_name": company.name if company else None,
                "action_label": "Открыть компании",
                "primary_url": f"/companies/{company.id}" if company else "/companies",
                "details_url": "/deals",
                "signals": ["нет открытых сделок"],
                "focus_deals": [],
            }

        deal = (
            self.db.query(Deal)
            .filter(Deal.id == risk_item.deal_id, Deal.tenant_id == tenant_id)
            .one()
        )
        company = (
            self.db.query(Company)
            .filter(Company.id == deal.company_id, Company.tenant_id == tenant_id)
            .one()
        )
        actions = (
            self.db.query(NextAction)
            .filter(
                NextAction.tenant_id == tenant_id,
                NextAction.status == "open",
                NextAction.company_id == company.id,
            )
            .all()
        )
        priority_rank = {"urgent": 3, "high": 2, "normal": 1, "low": 0}
        actions.sort(
            key=lambda action: (
                action.deal_id == deal.id,
                priority_rank.get(str(action.priority).lower(), 1),
                -(action.due_at.timestamp() if action.due_at else now.timestamp() + 10**9),
            ),
            reverse=True,
        )
        next_action = actions[0] if actions else None
        title = (
            next_action.title
            if next_action
            else deal.next_step
            or deal.expected_next_event
            or f"Связаться с {company.name} и назначить следующий шаг"
        )
        signal_labels = {
            "deal is stuck": "сделка зависла на этапе",
            "close date overdue": "дата закрытия просрочена",
            "next step missing": "не указан следующий шаг",
            "company health is low": "низкий health score компании",
            "AI risk and probability signals": "комбинация риска и вероятности",
        }
        signals = [signal_labels.get(reason, reason) for reason in risk_item.reasons]
        if next_action:
            signals.insert(0, f"активный NextAction: {next_action.title}")
        rationale = (
            f"Backend copilot выбрал сделку «{deal.title}»: риск {risk_item.score}%, "
            f"этап «{stage_label_ru(risk_item.stage_name)}». Основания: {', '.join(signals)}."
        )
        action_label = "Позвонить" if re.search(r"позвон|созвон|связаться", title, re.I) else "Открыть компанию"
        focus_deals = []
        for item in overview.risk_map.deals[:3]:
            focus_deal = (
                self.db.query(Deal)
                .filter(Deal.id == item.deal_id, Deal.tenant_id == tenant_id)
                .one()
            )
            focus_deals.append(
                {
                    "deal_id": focus_deal.id,
                    "company_id": item.company_id,
                    "company_name": item.company_name,
                    "deal_title": item.title,
                    "amount": item.amount,
                    "stage_name": stage_label_ru(item.stage_name),
                    "confidence": max(0, min(100, int(focus_deal.probability or 45))),
                    "risk_score": item.score,
                    "risk_level": item.level,
                    "next_action": focus_deal.next_step
                    or focus_deal.expected_next_event
                    or f"Связаться с {item.company_name}",
                }
            )
        return {
            "generated_at": now,
            "source": "backend_copilot",
            "title": title,
            "rationale": rationale,
            "company_id": company.id,
            "company_name": company.name,
            "deal_id": deal.id,
            "deal_title": deal.title,
            "amount": float(deal.amount or 0),
            "confidence": max(0, min(100, int(deal.probability or 45))),
            "risk_score": risk_item.score,
            "risk_level": risk_item.level,
            "action_label": action_label,
            "primary_url": f"/companies/{company.id}",
            "details_url": "/deals",
            "signals": signals,
            "focus_deals": focus_deals,
        }

    def company_copilot(self, tenant_id: UUID, user_id: UUID, company_id: UUID) -> dict | None:
        company = (
            self.db.query(Company)
            .filter(Company.id == company_id, Company.tenant_id == tenant_id)
            .one_or_none()
        )
        if company is None:
            return None

        contacts = self.db.query(Contact).filter(Contact.tenant_id == tenant_id, Contact.company_id == company.id).all()
        deals = self.db.query(Deal).filter(Deal.tenant_id == tenant_id, Deal.company_id == company.id).all()
        tasks = self.db.query(Task).filter(Task.tenant_id == tenant_id, Task.company_id == company.id).all()
        activities = ActivityService(self.db).list(tenant_id=tenant_id, company_id=company.id, limit=20)
        current_deal = deals[0] if deals else None
        open_tasks = [task for task in tasks if task.done_at is None]
        total_amount = sum(float(deal.amount or 0) for deal in deals)
        last_activity = activities[0] if activities else None
        days_since_activity = self._days_since(last_activity.created_at) if last_activity else 999

        risk_score = self._deal_risk_score(current_deal, open_tasks, days_since_activity)
        risk_level = "high" if risk_score >= 70 else "medium" if risk_score >= 35 else "low"
        next_best_action = self._next_best_action(current_deal, contacts, open_tasks, days_since_activity)
        summary = (
            f"{company.name}: {len(contacts)} контактов, {len(deals)} сделок, "
            f"{len(open_tasks)} открытых задач, pipeline {total_amount:,.0f} руб. "
            f"AI фокус: {next_best_action}."
        )
        follow_up_draft = self._follow_up_draft(company, contacts, current_deal, next_best_action)
        meeting_prep = self._meeting_prep(company, current_deal, activities)
        insight = {
            "health_score": max(0, min(100, 88 - risk_score // 2 + len(contacts) * 3)),
            "health_label": "Risk" if risk_level == "high" else "Healthy",
            "health_trend": "down" if risk_level == "high" else "up",
            "risk_level": risk_level,
            "success_chance": max(5, min(95, (current_deal.probability if current_deal and current_deal.probability else 45) - risk_score // 4)),
            "success_chance_delta": -6 if risk_level == "high" else 4,
            "ai_recommendations": [
                {
                    "type": "warning" if risk_level == "high" else "info",
                    "title": "AI Deal Risk",
                    "description": f"{risk_level}: {self._risk_reason(current_deal, open_tasks, days_since_activity)}",
                },
                {
                    "type": "success",
                    "title": "AI Next Best Action",
                    "description": next_best_action,
                },
            ],
        }

        actions = [
            self._ensure_pending_action(
                tenant_id,
                user_id,
                "create_next_action",
                {
                    "company_id": str(company.id),
                    "deal_id": str(current_deal.id) if current_deal else None,
                    "contact_id": str(contacts[0].id) if contacts else None,
                    "title": next_best_action,
                    "description": "AI next best action generated from company activity, deal risk, and open tasks.",
                    "priority": "high" if risk_level == "high" else "normal",
                    "due_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
                },
            ),
            self._ensure_pending_action(
                tenant_id,
                user_id,
                "update_customer_insight",
                {
                    "company_id": str(company.id),
                    **insight,
                },
            ),
        ]

        return {
            "summary": summary,
            "next_best_action": next_best_action,
            "deal_risk": {
                "level": risk_level,
                "score": risk_score,
                "reason": self._risk_reason(current_deal, open_tasks, days_since_activity),
            },
            "follow_up_draft": follow_up_draft,
            "meeting_prep": meeting_prep,
            "insight": insight,
            "actions": actions,
        }

    def confirm_action(self, tenant_id: UUID, action_id: UUID) -> AgentAction | None:
        action = (
            self.db.query(AgentAction)
            .filter(AgentAction.id == action_id, AgentAction.tenant_id == tenant_id)
            .one_or_none()
        )
        if action is None:
            return None
        if action.status != "pending":
            return action

        payload = json.loads(action.payload_json)
        if action.action_type == "create_task":
            task = Task(
                tenant_id=tenant_id,
                company_id=UUID(payload["company_id"]),
                assigned_to_id=action.user_id,
                title=payload["title"],
                description=payload.get("description"),
                deal_id=payload.get("deal_id"),
            )
            self.db.add(task)
            self.db.flush()
            ActivityService(self.db).create(
                tenant_id=tenant_id,
                created_by=action.user_id,
                company_id=task.company_id,
                deal_id=task.deal_id,
                activity_type="AI_ACTION",
                title="AI created task",
                description=task.title,
                metadata={"action_id": str(action.id), "task_id": str(task.id)},
                commit=False,
            )
            action.result_json = json.dumps({"task_id": str(task.id), "title": task.title})
        elif action.action_type == "create_next_action":
            next_action = NextAction(
                tenant_id=tenant_id,
                company_id=UUID(payload["company_id"]),
                deal_id=UUID(payload["deal_id"]) if payload.get("deal_id") else None,
                contact_id=UUID(payload["contact_id"]) if payload.get("contact_id") else None,
                assigned_to_id=action.user_id,
                title=payload["title"],
                description=payload.get("description"),
                source="ai",
                status="open",
                priority=payload.get("priority", "normal"),
                due_at=self._parse_datetime(payload.get("due_at")),
            )
            self.db.add(next_action)
            self.db.flush()
            company = (
                self.db.query(Company)
                .filter(Company.id == next_action.company_id, Company.tenant_id == tenant_id)
                .one_or_none()
            )
            if company:
                company.next_action_id = next_action.id
            if next_action.deal_id:
                deal = (
                    self.db.query(Deal)
                    .filter(Deal.id == next_action.deal_id, Deal.tenant_id == tenant_id)
                    .one_or_none()
                )
                if deal:
                    deal.next_action_id = next_action.id
                    deal.next_step = next_action.title
            ActivityService(self.db).create(
                tenant_id=tenant_id,
                created_by=action.user_id,
                company_id=next_action.company_id,
                deal_id=next_action.deal_id,
                contact_id=next_action.contact_id,
                activity_type="AI_ACTION",
                title="AI next action confirmed",
                description=next_action.title,
                metadata={"action_id": str(action.id), "next_action_id": str(next_action.id)},
                commit=False,
            )
            action.result_json = json.dumps({"next_action_id": str(next_action.id), "title": next_action.title})
        elif action.action_type == "update_customer_insight":
            company_id = UUID(payload["company_id"])
            insight = (
                self.db.query(CustomerInsight)
                .filter(CustomerInsight.tenant_id == tenant_id, CustomerInsight.company_id == company_id)
                .one_or_none()
            )
            if insight is None:
                insight = CustomerInsight(tenant_id=tenant_id, company_id=company_id)
                self.db.add(insight)
            insight.health_score = payload.get("health_score")
            insight.health_label = payload.get("health_label")
            insight.health_trend = payload.get("health_trend")
            insight.risk_level = payload.get("risk_level")
            insight.success_chance = payload.get("success_chance")
            insight.success_chance_delta = payload.get("success_chance_delta")
            insight.ai_recommendations_json = json.dumps(payload.get("ai_recommendations", []), ensure_ascii=False)
            insight.updated_at = datetime.now(timezone.utc)
            company = (
                self.db.query(Company)
                .filter(Company.id == company_id, Company.tenant_id == tenant_id)
                .one_or_none()
            )
            if company:
                company.health_score = insight.health_score
            ActivityService(self.db).create(
                tenant_id=tenant_id,
                created_by=action.user_id,
                company_id=company_id,
                activity_type="AI_ACTION",
                channel="AI",
                title="AI updated customer insight",
                description=f"Health {insight.health_score}, risk {insight.risk_level}",
                metadata={"action_id": str(action.id), "insight": payload},
                commit=False,
            )
            action.result_json = json.dumps({"company_id": str(company_id), "health_score": insight.health_score})
        elif action.action_type == "move_deal":
            deal = (
                self.db.query(Deal)
                .filter(Deal.id == UUID(payload["deal_id"]), Deal.tenant_id == tenant_id)
                .one_or_none()
            )
            if deal is None:
                action.status = "failed"
                action.result_json = json.dumps({"error": "Deal not found"})
                self.db.commit()
                return action
            deal.stage_id = UUID(payload["stage_id"])
            ActivityService(self.db).create(
                tenant_id=tenant_id,
                created_by=action.user_id,
                company_id=deal.company_id,
                deal_id=deal.id,
                activity_type="AI_ACTION",
                title="AI moved deal",
                description=f"{deal.title} moved to {payload.get('stage_name', 'new stage')}",
                metadata={"action_id": str(action.id), "stage_id": payload["stage_id"]},
                commit=False,
            )
            action.result_json = json.dumps({"deal_id": str(deal.id), "stage_id": str(deal.stage_id)})
        else:
            action.status = "failed"
            action.result_json = json.dumps({"error": "Unknown action"})
            self.db.commit()
            return action

        action.status = "confirmed"
        action.confirmed_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(action)
        return action

    def reject_action(self, tenant_id: UUID, action_id: UUID) -> AgentAction | None:
        action = (
            self.db.query(AgentAction)
            .filter(AgentAction.id == action_id, AgentAction.tenant_id == tenant_id)
            .one_or_none()
        )
        if action is None:
            return None
        if action.status == "pending":
            action.status = "rejected"
            self.db.commit()
            self.db.refresh(action)
        return action

    def _answer_from_knowledge(
        self,
        tenant_id: UUID,
        user_id: UUID,
        message: str,
        context_type: str = "workspace",
        company_id: UUID | None = None,
        deal_id: UUID | None = None,
        document_id: UUID | None = None,
        include_global: bool = False,
        page_path: str | None = None,
    ) -> tuple[str, list[dict], UUID, dict]:
        document = None
        if document_id is not None:
            document = (
                self.db.query(KnowledgeDocument)
                .filter(
                    KnowledgeDocument.tenant_id == tenant_id,
                    KnowledgeDocument.id == document_id,
                    KnowledgeDocument.status == "ready",
                )
                .one_or_none()
            )
            if document is None:
                raise ValueError("Document does not belong to current workspace")
            company_id = document.company_id
            deal_id = document.deal_id
        if deal_id and not company_id:
            deal = (
                self.db.query(Deal)
                .filter(Deal.tenant_id == tenant_id, Deal.id == deal_id)
                .one_or_none()
            )
            company_id = deal.company_id if deal else None
            if deal is None:
                deal_id = None
        scope = "deal" if company_id and deal_id else "company" if company_id else "global"
        result = self.knowledge_service.answer(
            tenant_id,
            user_id,
            message,
            limit=5,
            scope=scope,
            company_id=company_id,
            deal_id=deal_id,
            document_id=document_id,
            include_global=include_global if document_id is None else False,
        )
        sources = [
            {
                "document_id": str(item.document.id),
                "document_title": item.document.title,
                "document_scope": item.document.visibility,
                "company_id": str(item.document.company_id) if item.document.company_id else None,
                "deal_id": str(item.document.deal_id) if item.document.deal_id else None,
                "chunk_id": str(item.chunk.id),
                "chunk_index": item.chunk.chunk_index,
                "page_number": item.chunk.page_number,
                "score": item.score,
                "text": item.chunk.text[:500],
                "retrieval_method": item.retrieval_method,
                "download_url": (
                    f"/knowledge/documents/{item.document.id}/download"
                    if item.document.file_id
                    else None
                ),
            }
            for item in result.chunks
        ]
        normalized_context = {
            "type": "document" if document_id else (
                "deal" if deal_id else "company" if company_id else (
                    "knowledge" if context_type == "knowledge" else "workspace"
                )
            ),
            "company_id": str(company_id) if company_id else None,
            "deal_id": str(deal_id) if deal_id else None,
            "document_id": str(document_id) if document_id else None,
            "include_global": include_global if document_id is None else False,
            "page_path": page_path,
        }
        return result.answer, sources, result.query.id, normalized_context

    def _summarize_crm(self, tenant_id: UUID) -> str:
        leads_count = self.db.query(Lead).filter(Lead.tenant_id == tenant_id).count()
        deals = self.db.query(Deal).filter(Deal.tenant_id == tenant_id).all()
        open_tasks = (
            self.db.query(Task)
            .filter(Task.tenant_id == tenant_id, Task.done_at.is_(None))
            .count()
        )
        amount = sum(float(deal.amount or 0) for deal in deals)
        return (
            f"Сводка: лидов {leads_count}, сделок {len(deals)}, "
            f"открытых задач {open_tasks}, сумма пайплайна {amount:,.0f} руб."
        )

    def _propose_task(self, tenant_id: UUID, user_id: UUID, message: str) -> AgentAction | None:
        deal = self._find_deal_from_text(tenant_id, message)
        company_id = deal.company_id if deal else self._find_single_company_id(tenant_id)
        if company_id is None:
            return None
        title = self._extract_task_title(message)
        action = AgentAction(
            tenant_id=tenant_id,
            user_id=user_id,
            action_type="create_task",
            payload_json=json.dumps(
                {
                    "company_id": str(company_id),
                    "title": title,
                    "description": f"Создано AI агентом из запроса: {message}",
                    "deal_id": str(deal.id) if deal else None,
                }
            ),
        )
        self.db.add(action)
        self.db.commit()
        self.db.refresh(action)
        return action

    def _propose_deal_move(self, tenant_id: UUID, user_id: UUID, message: str) -> AgentAction | None:
        deal = self._find_deal_from_text(tenant_id, message)
        stage = self._find_stage_from_text(tenant_id, message)
        if deal is None or stage is None:
            return None

        action = AgentAction(
            tenant_id=tenant_id,
            user_id=user_id,
            action_type="move_deal",
            payload_json=json.dumps(
                {
                    "deal_id": str(deal.id),
                    "deal_title": deal.title,
                    "stage_id": str(stage.id),
                    "stage_name": stage_label_ru(stage.name),
                }
            ),
        )
        self.db.add(action)
        self.db.commit()
        self.db.refresh(action)
        return action

    def _find_deal_from_text(self, tenant_id: UUID, text: str) -> Deal | None:
        deals = self.db.query(Deal).filter(Deal.tenant_id == tenant_id).all()
        lowered = text.lower()
        for deal in deals:
            if deal.title.lower() in lowered:
                return deal
        return deals[0] if len(deals) == 1 else None

    def _find_stage_from_text(self, tenant_id: UUID, text: str) -> PipelineStage | None:
        stages = self.db.query(PipelineStage).filter(PipelineStage.tenant_id == tenant_id).all()
        lowered = text.lower()
        for stage in stages:
            if stage.name.lower() in lowered or stage_label_ru(stage.name).lower() in lowered:
                return stage
        return None

    def _find_single_company_id(self, tenant_id: UUID) -> UUID | None:
        from app.modules.sales.models import Company

        companies = self.db.query(Company).filter(Company.tenant_id == tenant_id).all()
        return companies[0].id if len(companies) == 1 else None

    def _extract_task_title(self, message: str) -> str:
        cleaned = re.sub(r"\b(создай|создать|задачу|задача|нужно)\b", "", message, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
        return cleaned[:255] if cleaned else "Связаться с клиентом"

    def _save_message(
        self,
        tenant_id: UUID,
        user_id: UUID,
        role: str,
        content: str,
        *,
        intent: str = "knowledge",
        context: dict | None = None,
        sources: list[dict] | None = None,
        knowledge_query_id: UUID | None = None,
    ) -> AgentMessage:
        message = AgentMessage(
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            content=content,
            intent=intent,
            context_json=json.dumps(context or {}, ensure_ascii=False),
            sources_json=json.dumps(sources or [], ensure_ascii=False),
            knowledge_query_id=knowledge_query_id,
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    def _ensure_pending_action(self, tenant_id: UUID, user_id: UUID, action_type: str, payload: dict) -> AgentAction:
        payload_key = payload.get("company_id") or payload.get("deal_id") or ""
        existing = (
            self.db.query(AgentAction)
            .filter(
                AgentAction.tenant_id == tenant_id,
                AgentAction.user_id == user_id,
                AgentAction.action_type == action_type,
                AgentAction.status == "pending",
            )
            .order_by(AgentAction.created_at.desc())
            .all()
        )
        for action in existing:
            current_payload = json.loads(action.payload_json)
            current_key = current_payload.get("company_id") or current_payload.get("deal_id") or ""
            if current_key == payload_key:
                action.payload_json = json.dumps(payload, ensure_ascii=False)
                self.db.commit()
                self.db.refresh(action)
                return action
        action = AgentAction(
            tenant_id=tenant_id,
            user_id=user_id,
            action_type=action_type,
            payload_json=json.dumps(payload, ensure_ascii=False),
        )
        self.db.add(action)
        self.db.commit()
        self.db.refresh(action)
        return action

    def _days_since(self, value: datetime) -> int:
        checked = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return max(0, (datetime.now(timezone.utc) - checked).days)

    def _deal_risk_score(self, deal: Deal | None, open_tasks: list[Task], days_since_activity: int) -> int:
        score = 0
        if deal is None:
            return 75
        if days_since_activity >= 7:
            score += 35
        if any(task.due_at and self._as_utc(task.due_at) < datetime.now(timezone.utc) for task in open_tasks):
            score += 30
        if deal.probability is not None and deal.probability < 45:
            score += 20
        if deal.expected_close_date and self._as_utc(deal.expected_close_date) < datetime.now(timezone.utc):
            score += 25
        return min(100, score)

    def _risk_reason(self, deal: Deal | None, open_tasks: list[Task], days_since_activity: int) -> str:
        if deal is None:
            return "нет активной сделки"
        if days_since_activity >= 7:
            return "нет свежей активности больше недели"
        if any(task.due_at and self._as_utc(task.due_at) < datetime.now(timezone.utc) for task in open_tasks):
            return "есть просроченные задачи"
        if deal.probability is not None and deal.probability < 45:
            return "низкая вероятность закрытия"
        return "риск контролируемый"

    def _next_best_action(self, deal: Deal | None, contacts: list[Contact], open_tasks: list[Task], days_since_activity: int) -> str:
        if open_tasks:
            return open_tasks[0].title
        if deal is None:
            return "Создать первую сделку и связать ее с ключевым контактом"
        if days_since_activity >= 3:
            return "Связаться с клиентом и подтвердить следующий шаг"
        if contacts:
            return f"Подготовить follow-up для {contacts[0].name}"
        return "Добавить ключевой контакт и назначить встречу"

    def _follow_up_draft(self, company: Company, contacts: list[Contact], deal: Deal | None, next_action: str) -> str:
        name = contacts[0].name if contacts else "коллеги"
        deal_line = f"по сделке «{deal.title}»" if deal else "по обсуждению внедрения"
        return (
            f"{name}, добрый день. Возвращаюсь {deal_line}. "
            f"Предлагаю следующий шаг: {next_action}. "
            f"Готова согласовать удобное время и подготовить материалы по {company.name}."
        )

    def _meeting_prep(self, company: Company, deal: Deal | None, activities: list) -> str:
        deal_part = f"Сделка: {deal.title}, сумма {float(deal.amount or 0):,.0f} руб." if deal else "Сделка еще не создана."
        last_titles = ", ".join(activity.title for activity in activities[:3]) or "активностей пока нет"
        return (
            f"Цель встречи: подтвердить потребность и следующий шаг. "
            f"{deal_part} Последние события: {last_titles}. "
            f"Вопросы: текущая CRM, число менеджеров, интеграции, срок пилота, критерий успеха."
        )

    def _parse_datetime(self, value: str | None) -> datetime | None:
        if not value:
            return None
        return datetime.fromisoformat(value)

    def _as_utc(self, value: datetime) -> datetime:
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)

    def _looks_like_task_request(self, lowered: str) -> bool:
        return "задач" in lowered or "напомни" in lowered or "создай task" in lowered

    def _looks_like_deal_move_request(self, lowered: str) -> bool:
        return ("перенеси" in lowered or "перемести" in lowered) and "сдел" in lowered

    def _looks_like_summary_request(self, lowered: str) -> bool:
        return "сводк" in lowered or "итог" in lowered or "что по crm" in lowered or "обзор" in lowered
