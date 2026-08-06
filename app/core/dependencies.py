from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db, set_tenant_context
from app.core.rbac import Role, deny_access
from app.core.security import decode_access_token
from app.modules.accounts.models import Membership, User, UserSession


bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentTenant:
    id: UUID
    user_id: UUID
    role: Role


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    claims = decode_access_token(credentials.credentials)
    if claims is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if claims.session_id is not None:
        session = db.get(UserSession, claims.session_id)
        if (
            session is None
            or session.user_id != claims.user_id
            or session.revoked_at is not None
            or _as_utc(session.expires_at) <= datetime.now(timezone.utc)
        ):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")

    user = db.get(User, claims.user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return user


def get_current_session_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> UUID:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    claims = decode_access_token(credentials.credentials)
    if claims is None or claims.session_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session required")
    return claims.session_id


def _as_utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def get_current_tenant(
    x_tenant_id: UUID = Header(alias="X-Tenant-Id"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CurrentTenant:
    membership = (
        db.query(Membership)
        .filter(
            Membership.tenant_id == x_tenant_id,
            Membership.user_id == user.id,
            Membership.is_active.is_(True),
        )
        .one_or_none()
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant access denied")

    try:
        role = Role(membership.role)
    except ValueError:
        deny_access("Invalid membership role")

    set_tenant_context(db, x_tenant_id)
    return CurrentTenant(id=x_tenant_id, user_id=user.id, role=role)
