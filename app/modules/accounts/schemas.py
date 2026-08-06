from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator

from app.core.rbac import Role
from app.modules.auth.schemas import validate_new_password


class MembershipRoleUpdate(BaseModel):
    role: Role


class MembershipCreate(BaseModel):
    email: EmailStr
    role: Role
    team_id: UUID | None = None
    manager_membership_id: UUID | None = None


class MembershipStructureUpdate(BaseModel):
    team_id: UUID | None = None
    manager_membership_id: UUID | None = None


class MembershipStatusUpdate(BaseModel):
    is_active: bool
    reassign_to_user_id: UUID | None = None


class MembershipResponse(BaseModel):
    id: UUID
    user_id: UUID
    email: str
    full_name: str
    role: Role
    is_active: bool
    team_id: UUID | None = None
    manager_membership_id: UUID | None = None
    deactivated_at: datetime | None = None
    created_at: datetime


class InvitationCreate(BaseModel):
    email: EmailStr
    role: Role = Role.SALES_REP
    team_id: UUID | None = None
    manager_membership_id: UUID | None = None
    expires_in_hours: int = Field(default=72, ge=1, le=720)


class InvitationResponse(BaseModel):
    id: UUID
    email: str
    role: Role
    team_id: UUID | None
    manager_membership_id: UUID | None
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime
    token: str | None = None


class InvitationAccept(BaseModel):
    token: str = Field(min_length=32, max_length=255)
    full_name: str | None = Field(default=None, min_length=2, max_length=255)
    password: str = Field(min_length=12, max_length=72)

    @model_validator(mode="after")
    def validate_password(self) -> "InvitationAccept":
        validate_new_password(self.password)
        return self


class InvitationAcceptResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: UUID
    tenant_id: UUID


class TeamCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    manager_membership_id: UUID | None = None


class TeamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    manager_membership_id: UUID | None = None
    is_active: bool | None = None


class TeamResponse(BaseModel):
    id: UUID
    name: str
    manager_membership_id: UUID | None
    is_active: bool
    member_count: int = 0
    created_at: datetime


class QueueCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    team_id: UUID | None = None
    strategy: Literal["round_robin", "manual"] = "round_robin"
    membership_ids: list[UUID] = Field(default_factory=list)


class QueueUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    team_id: UUID | None = None
    strategy: Literal["round_robin", "manual"] | None = None
    membership_ids: list[UUID] | None = None
    is_active: bool | None = None


class QueueResponse(BaseModel):
    id: UUID
    name: str
    team_id: UUID | None
    strategy: str
    membership_ids: list[UUID]
    is_active: bool
    created_at: datetime


class TerritoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    region: str | None = Field(default=None, max_length=120)
    industry: str | None = Field(default=None, max_length=120)
    owner_membership_id: UUID | None = None
    team_id: UUID | None = None
    priority: int = Field(default=100, ge=0, le=10000)


class TerritoryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    region: str | None = Field(default=None, max_length=120)
    industry: str | None = Field(default=None, max_length=120)
    owner_membership_id: UUID | None = None
    team_id: UUID | None = None
    priority: int | None = Field(default=None, ge=0, le=10000)
    is_active: bool | None = None


class TerritoryResponse(BaseModel):
    id: UUID
    name: str
    country_code: str | None
    region: str | None
    industry: str | None
    owner_membership_id: UUID | None
    team_id: UUID | None
    priority: int
    is_active: bool
    created_at: datetime


class AssignmentRuleCreate(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    entity_type: Literal["lead", "company"]
    criteria: dict[str, str] = Field(default_factory=dict)
    target_type: Literal["member", "team", "queue", "territory"]
    target_id: UUID
    priority: int = Field(default=100, ge=0, le=10000)


class AssignmentRuleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    criteria: dict[str, str] | None = None
    target_type: Literal["member", "team", "queue", "territory"] | None = None
    target_id: UUID | None = None
    priority: int | None = Field(default=None, ge=0, le=10000)
    is_active: bool | None = None


class AssignmentRuleResponse(BaseModel):
    id: UUID
    name: str
    entity_type: str
    criteria: dict[str, str]
    target_type: str
    target_id: UUID
    priority: int
    is_active: bool
    created_at: datetime
