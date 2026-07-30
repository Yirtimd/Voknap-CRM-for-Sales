import json
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import CurrentTenant, get_current_tenant
from app.core.rbac import (
    Permission,
    deny_access,
    has_permission,
    require_object_owner,
    require_permission,
)
from app.modules.ai_agent.models import AgentAction
from app.modules.ai_agent.schemas import (
    AgentActionResponse,
    AgentChatRequest,
    AgentChatResponse,
    AgentHistoryMessage,
    CompanyCopilotResponse,
    HomeCopilotResponse,
)
from app.modules.ai_agent.service import AgentService
from app.modules.sales.authorization import (
    require_company_write_access,
    require_deal_write_access,
)


router = APIRouter()


@router.get("/home/copilot", response_model=HomeCopilotResponse)
def home_copilot(
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(get_current_tenant),
) -> HomeCopilotResponse:
    return HomeCopilotResponse(**AgentService(db).home_copilot(tenant.id))


@router.get("/companies/{company_id}/copilot", response_model=CompanyCopilotResponse)
def company_copilot(
    company_id: UUID,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(get_current_tenant),
) -> CompanyCopilotResponse:
    service = AgentService(db)
    result = service.company_copilot(tenant.id, tenant.user_id, company_id)
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return CompanyCopilotResponse(
        company_id=company_id,
        summary=result["summary"],
        next_best_action=result["next_best_action"],
        deal_risk=result["deal_risk"],
        follow_up_draft=result["follow_up_draft"],
        meeting_prep=result["meeting_prep"],
        insight=result["insight"],
        actions=[_action_response(action) for action in result["actions"]],
    )


@router.post("/chat", response_model=AgentChatResponse)
def chat(
    payload: AgentChatRequest,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.AI_USE)),
) -> AgentChatResponse:
    service = AgentService(db)
    try:
        result = service.chat(
            tenant_id=tenant.id,
            user_id=tenant.user_id,
            message=payload.message,
            context_type=payload.context_type,
            company_id=payload.company_id,
            deal_id=payload.deal_id,
            document_id=payload.document_id,
            include_global=payload.include_global,
            page_path=payload.page_path,
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    return AgentChatResponse(
        message_id=result.message.id,
        query_id=result.query_id,
        answer=result.answer,
        actions=[_action_response(action) for action in result.actions],
        sources=result.sources,
        intent=result.intent,
        context=result.context,
    )


@router.get("/history", response_model=list[AgentHistoryMessage])
def history(
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(get_current_tenant),
) -> list[AgentHistoryMessage]:
    service = AgentService(db)
    messages = service.list_history(tenant.id)
    if not has_permission(tenant.role, Permission.ASSIGNMENTS_MANAGE):
        messages = [message for message in messages if message.user_id == tenant.user_id]
    return [
        AgentHistoryMessage(
            id=message.id,
            role=message.role,
            content=message.content,
            intent=message.intent,
            context=json.loads(message.context_json),
            sources=json.loads(message.sources_json),
            query_id=message.knowledge_query_id,
            created_at=message.created_at,
        )
        for message in messages
    ]


@router.get("/actions", response_model=list[AgentActionResponse])
def list_actions(
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(get_current_tenant),
) -> list[AgentActionResponse]:
    service = AgentService(db)
    actions = service.list_actions(tenant.id)
    if not has_permission(tenant.role, Permission.ASSIGNMENTS_MANAGE):
        actions = [action for action in actions if action.user_id == tenant.user_id]
    return [_action_response(action) for action in actions]


@router.post("/actions/{action_id}/confirm", response_model=AgentActionResponse)
def confirm_action(
    action_id: UUID,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> AgentActionResponse:
    service = AgentService(db)
    action = next((row for row in service.list_actions(tenant.id) if row.id == action_id), None)
    if action is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")
    require_object_owner(tenant.role, tenant.user_id, action.user_id)
    _authorize_action_target(db, tenant, action)
    action = service.confirm_action(tenant.id, action_id)
    if action is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")
    return _action_response(action)


@router.post("/actions/{action_id}/reject", response_model=AgentActionResponse)
def reject_action(
    action_id: UUID,
    db: Session = Depends(get_db),
    tenant: CurrentTenant = Depends(require_permission(Permission.CRM_WRITE)),
) -> AgentActionResponse:
    service = AgentService(db)
    action = next((row for row in service.list_actions(tenant.id) if row.id == action_id), None)
    if action is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")
    require_object_owner(tenant.role, tenant.user_id, action.user_id)
    action = service.reject_action(tenant.id, action_id)
    if action is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Action not found")
    return _action_response(action)


def _action_response(action: AgentAction) -> AgentActionResponse:
    return AgentActionResponse(
        id=action.id,
        action_type=action.action_type,
        status=action.status,
        payload=json.loads(action.payload_json),
        result=json.loads(action.result_json) if action.result_json else None,
        created_at=action.created_at,
        confirmed_at=action.confirmed_at,
    )


def _authorize_action_target(db: Session, tenant: CurrentTenant, action: AgentAction) -> None:
    payload = json.loads(action.payload_json)
    if action.action_type == "update_customer_insight":
        if not has_permission(tenant.role, Permission.SALES_MANAGE):
            deny_access("Customer insight updates require manager permission")
        return
    if payload.get("company_id"):
        require_company_write_access(db, tenant, UUID(payload["company_id"]))
    if payload.get("deal_id"):
        require_deal_write_access(db, tenant, UUID(payload["deal_id"]))
