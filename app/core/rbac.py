from collections.abc import Callable
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, status


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    SALES_MANAGER = "sales_manager"
    SALES_REP = "sales_rep"
    VIEWER = "viewer"


class Permission(StrEnum):
    CRM_READ = "crm:read"
    CRM_WRITE = "crm:write"
    SALES_MANAGE = "sales:manage"
    ASSIGNMENTS_MANAGE = "assignments:manage"
    AI_USE = "ai:use"
    KNOWLEDGE_WRITE = "knowledge:write"
    INTEGRATIONS_MANAGE = "integrations:manage"
    TEMPLATES_MANAGE = "templates:manage"
    SETTINGS_READ = "settings:read"
    AUDIT_READ = "audit:read"
    FEATURE_FLAGS_MANAGE = "feature_flags:manage"
    BILLING_MANAGE = "billing:manage"
    DATA_EXPORT = "data:export"
    MEMBERS_MANAGE = "members:manage"
    AUTOMATIONS_MANAGE = "automations:manage"
    APPROVALS_MANAGE = "approvals:manage"
    CUSTOM_FIELDS_MANAGE = "custom_fields:manage"


ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.OWNER: frozenset(Permission),
    Role.ADMIN: frozenset(
        {
            Permission.CRM_READ,
            Permission.CRM_WRITE,
            Permission.SALES_MANAGE,
            Permission.ASSIGNMENTS_MANAGE,
            Permission.AI_USE,
            Permission.KNOWLEDGE_WRITE,
            Permission.INTEGRATIONS_MANAGE,
            Permission.TEMPLATES_MANAGE,
            Permission.SETTINGS_READ,
            Permission.AUDIT_READ,
            Permission.FEATURE_FLAGS_MANAGE,
            Permission.DATA_EXPORT,
            Permission.MEMBERS_MANAGE,
            Permission.AUTOMATIONS_MANAGE,
            Permission.APPROVALS_MANAGE,
            Permission.CUSTOM_FIELDS_MANAGE,
        }
    ),
    Role.SALES_MANAGER: frozenset(
        {
            Permission.CRM_READ,
            Permission.CRM_WRITE,
            Permission.SALES_MANAGE,
            Permission.ASSIGNMENTS_MANAGE,
            Permission.AI_USE,
            Permission.KNOWLEDGE_WRITE,
            Permission.AUTOMATIONS_MANAGE,
            Permission.APPROVALS_MANAGE,
        }
    ),
    Role.SALES_REP: frozenset(
        {
            Permission.CRM_READ,
            Permission.CRM_WRITE,
            Permission.AI_USE,
            Permission.KNOWLEDGE_WRITE,
        }
    ),
    Role.VIEWER: frozenset({Permission.CRM_READ}),
}


def has_permission(role: Role, permission: Permission) -> bool:
    return permission in ROLE_PERMISSIONS[role]


def deny_access(detail: str = "Permission denied") -> None:
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)


def require_permission(permission: Permission) -> Callable:
    from app.core.dependencies import CurrentTenant, get_current_tenant

    def dependency(
        tenant: Annotated[CurrentTenant, Depends(get_current_tenant)],
    ) -> CurrentTenant:
        if not has_permission(tenant.role, permission):
            deny_access()
        return tenant

    dependency.required_permission = permission  # type: ignore[attr-defined]
    return dependency


def require_object_owner(role: Role, user_id: UUID, owner_id: UUID | None) -> None:
    if has_permission(role, Permission.ASSIGNMENTS_MANAGE):
        return
    if owner_id != user_id:
        deny_access("Object access denied")


def require_allowed_fields(
    role: Role,
    requested_fields: set[str],
    restricted_fields: set[str],
) -> None:
    if has_permission(role, Permission.ASSIGNMENTS_MANAGE):
        return
    denied_fields = requested_fields & restricted_fields
    if denied_fields:
        deny_access(f"Fields require manager permission: {', '.join(sorted(denied_fields))}")
