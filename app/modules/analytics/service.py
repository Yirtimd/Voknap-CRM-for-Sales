from collections import defaultdict
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.orm import Session

from app.modules.accounts.models import Membership, SalesTeam, User
from app.modules.activity.models import Activity
from app.modules.analytics.schemas import (
    AnalyticsOverview,
    CompanyHealthItem,
    DealRiskItem,
    ForecastBreakdown,
    ForecastDataQuality,
    ForecastSummary,
    ManagerActivity,
    OwnerTaskSLA,
    RiskMap,
    StageConversion,
    StuckDeal,
    TaskSLASummary,
)
from app.modules.sales.models import Company, CustomerInsight, Deal, Pipeline, PipelineStage, Task
from app.modules.sales.stages import stage_label_ru


OPEN_STATUSES = {"open", "active", "in_progress", "new"}


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _money(value: object) -> float:
    return round(float(value or 0), 2)


def _probability(deal: Deal) -> int:
    if deal.scoring_probability is not None:
        return max(0, min(100, deal.scoring_probability))
    if deal.probability is not None:
        return max(0, min(100, deal.probability))
    return {"commit": 90, "best_case": 60, "pipeline": 35}.get(
        str(deal.forecast_category or "").lower(), 45
    )


def _is_open(deal: Deal) -> bool:
    return str(deal.status or "open").lower() not in {"won", "lost", "closed"}


class AnalyticsService:
    def __init__(self, db: Session):
        self.db = db

    def overview(
        self,
        *,
        tenant_id: UUID,
        forecast_days: int,
        stuck_days: int,
        activity_days: int,
    ) -> AnalyticsOverview:
        now = datetime.now(timezone.utc)
        companies = self.db.query(Company).filter(Company.tenant_id == tenant_id).all()
        pipelines = self.db.query(Pipeline).filter(Pipeline.tenant_id == tenant_id).all()
        stages = (
            self.db.query(PipelineStage)
            .filter(PipelineStage.tenant_id == tenant_id)
            .order_by(PipelineStage.pipeline_id, PipelineStage.sort_order)
            .all()
        )
        deals = self.db.query(Deal).filter(Deal.tenant_id == tenant_id).all()
        tasks = self.db.query(Task).filter(Task.tenant_id == tenant_id).all()
        activities = self.db.query(Activity).filter(Activity.tenant_id == tenant_id).all()
        insights = (
            self.db.query(CustomerInsight).filter(CustomerInsight.tenant_id == tenant_id).all()
        )
        memberships = (
            self.db.query(Membership).filter(Membership.tenant_id == tenant_id).all()
        )
        teams = self.db.query(SalesTeam).filter(SalesTeam.tenant_id == tenant_id).all()
        user_ids = {membership.user_id for membership in memberships}
        users = self.db.query(User).filter(User.id.in_(user_ids)).all() if user_ids else []

        company_by_id = {company.id: company for company in companies}
        pipeline_by_id = {pipeline.id: pipeline for pipeline in pipelines}
        stage_by_id = {stage.id: stage for stage in stages}
        user_by_id = {user.id: user for user in users}
        membership_by_user = {membership.user_id: membership for membership in memberships}
        team_by_id = {team.id: team for team in teams}
        insight_by_company = {insight.company_id: insight for insight in insights}

        deal_activities: dict[UUID, list[Activity]] = defaultdict(list)
        company_activities: dict[UUID, list[Activity]] = defaultdict(list)
        for activity in activities:
            company_activities[activity.company_id].append(activity)
            if activity.deal_id:
                deal_activities[activity.deal_id].append(activity)

        stage_entered_at = {
            deal.id: self._stage_entered_at(deal, deal_activities.get(deal.id, []))
            for deal in deals
        }
        stuck_ids = {
            deal.id
            for deal in deals
            if _is_open(deal) and (now - stage_entered_at[deal.id]).days >= stuck_days
        }
        health = self._company_health(
            now=now,
            companies=companies,
            deals=deals,
            tasks=tasks,
            company_activities=company_activities,
            insights=insight_by_company,
        )
        health_by_company = {item.company_id: item for item in health}
        risk_map = self._risk_map(
            now=now,
            deals=deals,
            company_by_id=company_by_id,
            stage_by_id=stage_by_id,
            user_by_id=user_by_id,
            stuck_ids=stuck_ids,
            health_by_company=health_by_company,
        )

        forecast = self._forecast(now, deals, forecast_days)
        return AnalyticsOverview(
            generated_at=now,
            forecast=forecast,
            forecast_by_owner=self._forecast_breakdown(
                now,
                deals,
                forecast_days,
                lambda deal: deal.owner_id,
                lambda owner_id: user_by_id.get(owner_id).full_name
                if owner_id in user_by_id
                else "Без ответственного",
            ),
            forecast_by_team=self._forecast_breakdown(
                now,
                deals,
                forecast_days,
                lambda deal: membership_by_user.get(deal.owner_id).team_id
                if deal.owner_id in membership_by_user
                else None,
                lambda team_id: team_by_id.get(team_id).name
                if team_id in team_by_id
                else "Без команды",
            ),
            forecast_quality=self._forecast_quality(deals),
            stage_conversion=self._stage_conversion(
                deals, stages, pipeline_by_id, stuck_ids
            ),
            stuck_deals=self._stuck_deals(
                now=now,
                deals=deals,
                company_by_id=company_by_id,
                stage_by_id=stage_by_id,
                user_by_id=user_by_id,
                deal_activities=deal_activities,
                stage_entered_at=stage_entered_at,
                stuck_ids=stuck_ids,
            ),
            task_sla=self._task_sla(now, tasks, user_by_id),
            manager_activity=self._manager_activity(
                now, deals, tasks, activities, users, activity_days
            ),
            company_health=health,
            risk_map=risk_map,
        )

    @staticmethod
    def _stage_entered_at(deal: Deal, activities: list[Activity]) -> datetime:
        stage_changes = [
            activity
            for activity in activities
            if activity.type == "DEAL_STAGE_CHANGED" and _utc(activity.created_at)
        ]
        if stage_changes:
            return max(_utc(activity.created_at) for activity in stage_changes)  # type: ignore[arg-type]
        return _utc(deal.created_at) or datetime.now(timezone.utc)

    @staticmethod
    def _forecast(now: datetime, deals: list[Deal], forecast_days: int) -> ForecastSummary:
        open_deals = [deal for deal in deals if _is_open(deal)]
        period_end = now + timedelta(days=forecast_days)
        due = [
            deal
            for deal in open_deals
            if deal.expected_close_date is not None
            and now <= (_utc(deal.expected_close_date) or now) <= period_end
        ]

        def total(items: list[Deal]) -> float:
            return round(sum(_money(deal.amount) for deal in items), 2)

        return ForecastSummary(
            period_days=forecast_days,
            open_pipeline=total(open_deals),
            due_in_period=total(due),
            weighted_revenue=round(
                sum(_money(deal.amount) * _probability(deal) / 100 for deal in due), 2
            ),
            commit_revenue=total(
                [deal for deal in due if str(deal.forecast_category).lower() == "commit"]
            ),
            best_case_revenue=total(
                [deal for deal in due if str(deal.forecast_category).lower() == "best_case"]
            ),
            pipeline_revenue=total(
                [deal for deal in due if str(deal.forecast_category).lower() == "pipeline"]
            ),
            overdue_revenue=total(
                [
                    deal
                    for deal in open_deals
                    if deal.expected_close_date and (_utc(deal.expected_close_date) or now) < now
                ]
            ),
            won_revenue=total([deal for deal in deals if str(deal.status).lower() == "won"]),
            open_deals=len(open_deals),
            scoring_coverage_rate=_percent(
                sum(deal.opportunity_score is not None for deal in open_deals),
                len(open_deals),
            ),
        )

    @classmethod
    def _forecast_breakdown(
        cls,
        now: datetime,
        deals: list[Deal],
        forecast_days: int,
        key,
        name,
    ) -> list[ForecastBreakdown]:
        result = []
        for scope_id, scoped_deals in _group_by(deals, key).items():
            summary = cls._forecast(now, scoped_deals, forecast_days)
            result.append(
                ForecastBreakdown(
                    scope_id=scope_id,
                    scope_name=name(scope_id),
                    open_deals=summary.open_deals,
                    open_pipeline=summary.open_pipeline,
                    due_in_period=summary.due_in_period,
                    weighted_revenue=summary.weighted_revenue,
                    commit_revenue=summary.commit_revenue,
                    overdue_revenue=summary.overdue_revenue,
                )
            )
        return sorted(result, key=lambda item: item.weighted_revenue, reverse=True)

    @staticmethod
    def _forecast_quality(deals: list[Deal]) -> ForecastDataQuality:
        open_deals = [deal for deal in deals if _is_open(deal)]
        missing_owner = sum(deal.owner_id is None for deal in open_deals)
        missing_close_date = sum(deal.expected_close_date is None for deal in open_deals)
        missing_probability = sum(
            deal.probability is None and deal.scoring_probability is None
            for deal in open_deals
        )
        missing_category = sum(not deal.forecast_category for deal in open_deals)
        missing_score = sum(deal.opportunity_score is None for deal in open_deals)
        expected = len(open_deals) * 5
        missing = (
            missing_owner
            + missing_close_date
            + missing_probability
            + missing_category
            + missing_score
        )
        return ForecastDataQuality(
            completeness_rate=_percent(expected - missing, expected),
            missing_owner=missing_owner,
            missing_close_date=missing_close_date,
            missing_probability=missing_probability,
            missing_forecast_category=missing_category,
            missing_opportunity_score=missing_score,
        )

    @staticmethod
    def _stage_conversion(
        deals: list[Deal],
        stages: list[PipelineStage],
        pipeline_by_id: dict[UUID, Pipeline],
        stuck_ids: set[UUID],
    ) -> list[StageConversion]:
        stage_by_id = {stage.id: stage for stage in stages}
        result: list[StageConversion] = []
        for pipeline_id, pipeline_stages in _group_stages(stages).items():
            pipeline_deals = [
                deal for deal in deals if stage_by_id.get(deal.stage_id, None) in pipeline_stages
            ]
            first_reached = len(pipeline_deals)
            previous_reached = first_reached
            for stage in pipeline_stages:
                current = [deal for deal in pipeline_deals if deal.stage_id == stage.id]
                reached = sum(
                    1
                    for deal in pipeline_deals
                    if stage_by_id[deal.stage_id].sort_order >= stage.sort_order
                )
                result.append(
                    StageConversion(
                        pipeline_id=pipeline_id,
                        pipeline_name=pipeline_by_id[pipeline_id].name,
                        stage_id=stage.id,
                        stage_name=stage_label_ru(stage.name),
                        sort_order=stage.sort_order,
                        deal_count=len(current),
                        reached_count=reached,
                        amount=round(sum(_money(deal.amount) for deal in current), 2),
                        weighted_amount=round(
                            sum(
                                _money(deal.amount) * _probability(deal) / 100
                                for deal in current
                            ),
                            2,
                        ),
                        conversion_from_first=_percent(reached, first_reached),
                        conversion_from_previous=_percent(reached, previous_reached),
                        stuck_count=sum(deal.id in stuck_ids for deal in current),
                    )
                )
                previous_reached = reached
        return result

    @staticmethod
    def _stuck_deals(
        *,
        now: datetime,
        deals: list[Deal],
        company_by_id: dict[UUID, Company],
        stage_by_id: dict[UUID, PipelineStage],
        user_by_id: dict[UUID, User],
        deal_activities: dict[UUID, list[Activity]],
        stage_entered_at: dict[UUID, datetime],
        stuck_ids: set[UUID],
    ) -> list[StuckDeal]:
        result = []
        for deal in deals:
            if deal.id not in stuck_ids:
                continue
            last_activity = max(
                (_utc(item.created_at) for item in deal_activities.get(deal.id, [])),
                default=None,
            )
            result.append(
                StuckDeal(
                    deal_id=deal.id,
                    title=deal.title,
                    company_id=deal.company_id,
                    company_name=company_by_id[deal.company_id].name,
                    stage_name=stage_label_ru(stage_by_id[deal.stage_id].name),
                    owner_name=user_by_id.get(deal.owner_id).full_name if deal.owner_id in user_by_id else None,
                    amount=_money(deal.amount),
                    weighted_amount=round(_money(deal.amount) * _probability(deal) / 100, 2),
                    days_in_stage=max(0, (now - stage_entered_at[deal.id]).days),
                    last_activity_at=last_activity,
                    risk_level=str(deal.risk_level or "medium").lower(),
                )
            )
        return sorted(result, key=lambda item: (item.days_in_stage, item.amount), reverse=True)

    @staticmethod
    def _task_sla(
        now: datetime, tasks: list[Task], user_by_id: dict[UUID, User]
    ) -> TaskSLASummary:
        completed = [task for task in tasks if task.done_at or str(task.status).lower() == "done"]
        overdue = [
            task
            for task in tasks
            if task.due_at
            and (
                (_utc(task.done_at) or now) > (_utc(task.due_at) or now)
                and (task.done_at is not None or str(task.status).lower() != "done")
            )
        ]
        on_time = [
            task
            for task in completed
            if task.due_at and _utc(task.done_at) and _utc(task.done_at) <= _utc(task.due_at)
        ]
        measured = [task for task in tasks if task.due_at]
        resolution_hours = [
            ((_utc(task.done_at) or now) - (_utc(task.created_at) or now)).total_seconds() / 3600
            for task in completed
            if task.done_at
        ]
        by_owner = []
        for owner_id, owner_tasks in _group_by(tasks, lambda task: task.assigned_to_id).items():
            owner_overdue = [task for task in overdue if task.assigned_to_id == owner_id]
            owner_measured = [task for task in owner_tasks if task.due_at]
            by_owner.append(
                OwnerTaskSLA(
                    owner_id=owner_id,
                    owner_name=user_by_id.get(owner_id).full_name if owner_id in user_by_id else "Unknown",
                    total=len(owner_tasks),
                    completed=sum(task in completed for task in owner_tasks),
                    overdue=len(owner_overdue),
                    sla_rate=_percent(len(owner_measured) - len(owner_overdue), len(owner_measured)),
                )
            )
        return TaskSLASummary(
            total=len(tasks),
            open=len(tasks) - len(completed),
            completed=len(completed),
            overdue=len(overdue),
            completed_on_time=len(on_time),
            completion_rate=_percent(len(completed), len(tasks)),
            sla_rate=_percent(len(measured) - len(overdue), len(measured)),
            average_resolution_hours=(
                round(sum(resolution_hours) / len(resolution_hours), 1) if resolution_hours else None
            ),
            by_owner=sorted(by_owner, key=lambda item: (item.overdue, -item.sla_rate), reverse=True),
        )

    @staticmethod
    def _manager_activity(
        now: datetime,
        deals: list[Deal],
        tasks: list[Task],
        activities: list[Activity],
        users: list[User],
        activity_days: int,
    ) -> list[ManagerActivity]:
        since = now - timedelta(days=activity_days)
        recent = [activity for activity in activities if (_utc(activity.created_at) or now) >= since]
        result = []
        for user in users:
            owned_deals = [deal for deal in deals if deal.owner_id == user.id and _is_open(deal)]
            owned_tasks = [task for task in tasks if task.assigned_to_id == user.id]
            authored = [activity for activity in recent if activity.created_by == user.id]
            result.append(
                ManagerActivity(
                    manager_id=user.id,
                    manager_name=user.full_name,
                    activities=len(authored),
                    calls=sum(activity.type == "CALL" for activity in authored),
                    emails=sum(activity.type == "EMAIL" for activity in authored),
                    meetings=sum(activity.type == "MEETING" for activity in authored),
                    notes=sum(activity.type in {"NOTE", "COMMENT"} for activity in authored),
                    tasks_completed=sum(task.done_at is not None for task in owned_tasks),
                    tasks_overdue=sum(
                        bool(task.due_at and not task.done_at and (_utc(task.due_at) or now) < now)
                        for task in owned_tasks
                    ),
                    open_deals=len(owned_deals),
                    pipeline_amount=round(sum(_money(deal.amount) for deal in owned_deals), 2),
                    weighted_revenue=round(
                        sum(_money(deal.amount) * _probability(deal) / 100 for deal in owned_deals), 2
                    ),
                )
            )
        return sorted(result, key=lambda item: (item.weighted_revenue, item.activities), reverse=True)

    @staticmethod
    def _company_health(
        *,
        now: datetime,
        companies: list[Company],
        deals: list[Deal],
        tasks: list[Task],
        company_activities: dict[UUID, list[Activity]],
        insights: dict[UUID, CustomerInsight],
    ) -> list[CompanyHealthItem]:
        result = []
        for company in companies:
            open_deals = [deal for deal in deals if deal.company_id == company.id and _is_open(deal)]
            overdue = [
                task
                for task in tasks
                if task.company_id == company.id
                and task.due_at
                and not task.done_at
                and (_utc(task.due_at) or now) < now
            ]
            latest = max(
                (_utc(activity.created_at) for activity in company_activities.get(company.id, [])),
                default=None,
            )
            idle_days = max(0, (now - latest).days) if latest else None
            insight = insights.get(company.id)
            base = insight.health_score if insight and insight.health_score is not None else company.health_score
            score = int(base if base is not None else 70)
            reasons = []
            if overdue:
                score -= min(30, len(overdue) * 10)
                reasons.append(f"{len(overdue)} overdue tasks")
            if idle_days is None or idle_days >= 30:
                score -= 20
                reasons.append("no recent activity")
            elif idle_days >= 14:
                score -= 10
                reasons.append(f"inactive for {idle_days} days")
            high_risk = sum(str(deal.risk_level).lower() == "high" for deal in open_deals)
            if high_risk:
                score -= min(25, high_risk * 12)
                reasons.append(f"{high_risk} high-risk deals")
            score = max(0, min(100, score))
            level = "low" if score >= 70 else "medium" if score >= 45 else "high"
            result.append(
                CompanyHealthItem(
                    company_id=company.id,
                    company_name=company.name,
                    score=score,
                    label="Healthy" if score >= 70 else "Watch" if score >= 45 else "At risk",
                    trend=insight.health_trend if insight else None,
                    open_deals=len(open_deals),
                    pipeline_amount=round(sum(_money(deal.amount) for deal in open_deals), 2),
                    overdue_tasks=len(overdue),
                    days_since_activity=idle_days,
                    risk_level=level,
                    reasons=reasons or ["stable signals"],
                )
            )
        return sorted(result, key=lambda item: (item.score, -item.pipeline_amount))

    @staticmethod
    def _risk_map(
        *,
        now: datetime,
        deals: list[Deal],
        company_by_id: dict[UUID, Company],
        stage_by_id: dict[UUID, PipelineStage],
        user_by_id: dict[UUID, User],
        stuck_ids: set[UUID],
        health_by_company: dict[UUID, CompanyHealthItem],
    ) -> RiskMap:
        items = []
        base_risk = {"high": 60, "medium": 35, "low": 10}
        for deal in deals:
            if not _is_open(deal):
                continue
            score = base_risk.get(str(deal.risk_level or "medium").lower(), 30)
            score += round((100 - _probability(deal)) * 0.25)
            reasons = []
            if deal.id in stuck_ids:
                score += 20
                reasons.append("deal is stuck")
            if deal.expected_close_date and (_utc(deal.expected_close_date) or now) < now:
                score += 15
                reasons.append("close date overdue")
            if not deal.next_step:
                score += 10
                reasons.append("next step missing")
            health = health_by_company.get(deal.company_id)
            if health and health.score < 45:
                score += 10
                reasons.append("company health is low")
            score = max(0, min(100, score))
            level = "high" if score >= 70 else "medium" if score >= 40 else "low"
            if not reasons:
                reasons.append("AI risk and probability signals")
            items.append(
                DealRiskItem(
                    deal_id=deal.id,
                    title=deal.title,
                    company_id=deal.company_id,
                    company_name=company_by_id[deal.company_id].name,
                    stage_name=stage_label_ru(stage_by_id[deal.stage_id].name),
                    owner_name=user_by_id.get(deal.owner_id).full_name if deal.owner_id in user_by_id else None,
                    amount=_money(deal.amount),
                    weighted_amount=round(_money(deal.amount) * _probability(deal) / 100, 2),
                    score=score,
                    level=level,
                    reasons=reasons,
                )
            )
        items.sort(key=lambda item: (item.score, item.amount), reverse=True)
        return RiskMap(
            high=sum(item.level == "high" for item in items),
            medium=sum(item.level == "medium" for item in items),
            low=sum(item.level == "low" for item in items),
            revenue_at_risk=round(
                sum(item.amount for item in items if item.level == "high"), 2
            ),
            deals=items,
        )


def _percent(numerator: int, denominator: int) -> float:
    return round(numerator / denominator * 100, 1) if denominator else 0.0


def _group_stages(stages: list[PipelineStage]) -> dict[UUID, list[PipelineStage]]:
    grouped: dict[UUID, list[PipelineStage]] = defaultdict(list)
    for stage in stages:
        grouped[stage.pipeline_id].append(stage)
    return grouped


def _group_by(items: list, key):
    grouped = defaultdict(list)
    for item in items:
        grouped[key(item)].append(item)
    return grouped
