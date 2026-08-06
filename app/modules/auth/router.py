import hashlib
import json
import smtplib
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db, set_tenant_context
from app.core.dependencies import get_current_session_id, get_current_user
from app.core.security import hash_password, verify_password
from app.modules.accounts.models import Membership, TeamInvitation, Tenant, User
from app.modules.accounts.schemas import InvitationAccept, InvitationAcceptResponse
from app.modules.auth.schemas import (
    LoginRequest,
    LoginResponse,
    MfaCodeRequest,
    MfaDisableRequest,
    MfaLoginRequest,
    MfaSetupResponse,
    MfaStatusResponse,
    PasswordChangeRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    PasswordResetRequested,
    RecoveryCodesResponse,
    RegisterCompanyRequest,
    SessionResponse,
    SessionRevokeResponse,
    TenantResponse,
)
from app.modules.auth.service import (
    REFRESH_COOKIE,
    AuthService,
    InvalidAuthTokenError,
    InvalidMfaCodeError,
    InvalidPasswordError,
    InvalidSessionError,
    MfaSetupRequiredError,
    RateLimitedError,
)


router = APIRouter()


@router.post("/register-company", response_model=LoginResponse, status_code=status.HTTP_201_CREATED)
def register_company(
    payload: RegisterCompanyRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    service = AuthService(db)
    ip, agent = _client(request)
    _check_rate(service, "register", payload.owner_email, ip)
    existing_user = db.query(User).filter(User.email == payload.owner_email).one_or_none()
    if existing_user is not None:
        service.record_failure("register", payload.owner_email, ip)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

    existing_tenant = db.query(Tenant).filter(Tenant.slug == payload.company_slug).one_or_none()
    if existing_tenant is not None:
        service.record_failure("register", payload.owner_email, ip)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Company slug already used")

    tenant = Tenant(name=payload.company_name, slug=payload.company_slug)
    user = User(
        email=payload.owner_email,
        full_name=payload.owner_full_name,
        password_hash=hash_password(payload.owner_password),
    )
    db.add_all([tenant, user])
    db.flush()
    db.add(Membership(tenant_id=tenant.id, user_id=user.id, role="owner"))
    db.commit()
    db.refresh(tenant)
    db.refresh(user)
    access, refresh, _ = service.create_session(user, ip, agent)
    service.clear_failures("register", payload.owner_email, ip)
    _set_refresh_cookie(response, refresh)
    return _authenticated(access, user, [tenant])


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    service = AuthService(db)
    ip, agent = _client(request)
    _check_rate(service, "login", payload.email, ip)
    user = db.query(User).filter(User.email == payload.email).one_or_none()
    if user is None or not user.is_active or not verify_password(payload.password, user.password_hash):
        service.record_failure("login", payload.email, ip)
        service.log_event("login.failed", user.id if user else None, ip, agent)
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    service.clear_failures("login", payload.email, ip)
    if user.mfa_enabled:
        mfa_token = service.create_auth_token(
            user.id,
            "mfa_login",
            ip,
            settings.auth_mfa_challenge_expire_minutes,
        )
        service.log_event("login.mfa_required", user.id, ip, agent)
        db.commit()
        return LoginResponse(status="mfa_required", mfa_token=mfa_token)

    access, refresh, _ = service.create_session(user, ip, agent)
    service.log_event("login.succeeded", user.id, ip, agent)
    db.commit()
    _set_refresh_cookie(response, refresh)
    return _authenticated(access, user, _active_tenants(user))


@router.post("/mfa/verify-login", response_model=LoginResponse)
def verify_mfa_login(
    payload: MfaLoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> LoginResponse:
    service = AuthService(db)
    ip, agent = _client(request)
    try:
        challenge = service.consume_auth_token(payload.mfa_token, "mfa_login")
    except InvalidAuthTokenError as error:
        raise HTTPException(status_code=401, detail="MFA challenge is invalid or expired") from error
    user = db.get(User, challenge.user_id)
    if user is None or not user.is_active or not service.verify_user_mfa(user, payload.code):
        challenge.attempts += 1
        service.log_event("login.mfa_failed", challenge.user_id, ip, agent)
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid MFA code")
    challenge.consumed_at = datetime.now(timezone.utc)
    access, refresh, _ = service.create_session(user, ip, agent)
    service.log_event("login.succeeded", user.id, ip, agent, {"mfa": True})
    db.commit()
    _set_refresh_cookie(response, refresh)
    return _authenticated(access, user, _active_tenants(user))


@router.post("/refresh", response_model=LoginResponse)
def refresh_session(
    request: Request,
    response: Response,
    crm_refresh_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
) -> LoginResponse:
    if not crm_refresh_token:
        raise HTTPException(status_code=401, detail="Refresh session not found")
    service = AuthService(db)
    ip, agent = _client(request)
    try:
        access, refresh, session = service.rotate_session(crm_refresh_token, ip, agent)
    except InvalidSessionError as error:
        _delete_refresh_cookie(response)
        raise HTTPException(status_code=401, detail="Refresh session is invalid or expired") from error
    user = db.get(User, session.user_id)
    _set_refresh_cookie(response, refresh)
    return _authenticated(access, user, _active_tenants(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    session_id: UUID = Depends(get_current_session_id),
    db: Session = Depends(get_db),
) -> None:
    ip, agent = _client(request)
    service = AuthService(db)
    service.revoke_session(user.id, session_id)
    service.log_event("session.logout", user.id, ip, agent, {"session_id": str(session_id)})
    db.commit()
    _delete_refresh_cookie(response)


@router.get("/sessions", response_model=list[SessionResponse])
def list_sessions(
    user: User = Depends(get_current_user),
    session_id: UUID = Depends(get_current_session_id),
    db: Session = Depends(get_db),
) -> list[SessionResponse]:
    return [
        SessionResponse(
            id=row.id,
            ip_address=row.ip_address,
            user_agent=row.user_agent,
            created_at=row.created_at,
            last_used_at=row.last_used_at,
            expires_at=row.expires_at,
            current=row.id == session_id,
        )
        for row in AuthService(db).list_sessions(user.id)
    ]


@router.delete("/sessions/{target_session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(
    target_session_id: UUID,
    user: User = Depends(get_current_user),
    current_session_id: UUID = Depends(get_current_session_id),
    db: Session = Depends(get_db),
) -> None:
    if target_session_id == current_session_id:
        raise HTTPException(status_code=409, detail="Use logout to revoke the current session")
    if not AuthService(db).revoke_session(user.id, target_session_id, "revoked_by_user"):
        raise HTTPException(status_code=404, detail="Session not found")


@router.delete("/sessions", response_model=SessionRevokeResponse)
def revoke_other_sessions(
    user: User = Depends(get_current_user),
    current_session_id: UUID = Depends(get_current_session_id),
    db: Session = Depends(get_db),
) -> SessionRevokeResponse:
    count = AuthService(db).revoke_other_sessions(user.id, current_session_id)
    return SessionRevokeResponse(revoked=count)


@router.post("/password/reset/request", response_model=PasswordResetRequested)
def request_password_reset(
    payload: PasswordResetRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> PasswordResetRequested:
    service = AuthService(db)
    ip, agent = _client(request)
    _check_rate(service, "password_reset", payload.email, ip)
    service.record_failure("password_reset", payload.email, ip)
    user = db.query(User).filter(User.email == payload.email, User.is_active.is_(True)).one_or_none()
    raw_token = None
    if user:
        try:
            raw_token = service.request_password_reset(user, ip, agent)
        except (RuntimeError, OSError, smtplib.SMTPException):
            service.log_event("password.reset_delivery_failed", user.id, ip, agent)
            db.commit()
    return PasswordResetRequested(
        dev_reset_token=(
            raw_token
            if raw_token and settings.app_environment != "production" and settings.auth_expose_reset_token
            else None
        )
    )


@router.post("/password/reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm_password_reset(
    payload: PasswordResetConfirm,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> None:
    ip, agent = _client(request)
    try:
        AuthService(db).reset_password(payload.token, payload.new_password, ip, agent)
    except InvalidAuthTokenError as error:
        raise HTTPException(status_code=400, detail="Reset token is invalid or expired") from error
    _delete_refresh_cookie(response)


@router.post("/password/change", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    response: Response,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    ip, agent = _client(request)
    try:
        AuthService(db).change_password(user, payload.current_password, payload.new_password, ip, agent)
    except InvalidPasswordError as error:
        raise HTTPException(status_code=400, detail="Current password is invalid") from error
    _delete_refresh_cookie(response)


@router.get("/mfa", response_model=MfaStatusResponse)
def mfa_status(user: User = Depends(get_current_user)) -> MfaStatusResponse:
    return MfaStatusResponse(
        enabled=user.mfa_enabled,
        enabled_at=user.mfa_enabled_at,
        recovery_codes_remaining=len(json.loads(user.mfa_recovery_codes_json or "[]")),
    )


@router.post("/mfa/setup", response_model=MfaSetupResponse)
def setup_mfa(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> MfaSetupResponse:
    if user.mfa_enabled:
        raise HTTPException(status_code=409, detail="MFA is already enabled")
    secret, uri = AuthService(db).begin_mfa_setup(user)
    return MfaSetupResponse(secret=secret, provisioning_uri=uri)


@router.post("/mfa/enable", response_model=RecoveryCodesResponse)
def enable_mfa(
    payload: MfaCodeRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecoveryCodesResponse:
    ip, agent = _client(request)
    try:
        codes = AuthService(db).enable_mfa(user, payload.code, ip, agent)
    except MfaSetupRequiredError as error:
        raise HTTPException(status_code=409, detail="Start MFA setup first") from error
    except InvalidMfaCodeError as error:
        raise HTTPException(status_code=400, detail="Invalid MFA code") from error
    return RecoveryCodesResponse(recovery_codes=codes)


@router.post("/mfa/disable", status_code=status.HTTP_204_NO_CONTENT)
def disable_mfa(
    payload: MfaDisableRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    ip, agent = _client(request)
    try:
        AuthService(db).disable_mfa(user, payload.password, payload.code, ip, agent)
    except InvalidMfaCodeError as error:
        raise HTTPException(status_code=400, detail="Password or MFA code is invalid") from error


@router.post("/mfa/recovery-codes", response_model=RecoveryCodesResponse)
def regenerate_recovery_codes(
    payload: MfaCodeRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecoveryCodesResponse:
    try:
        codes = AuthService(db).regenerate_recovery_codes(user, payload.code)
    except InvalidMfaCodeError as error:
        raise HTTPException(status_code=400, detail="Invalid MFA code") from error
    return RecoveryCodesResponse(recovery_codes=codes)


@router.post("/invitations/accept", response_model=InvitationAcceptResponse)
def accept_invitation(
    payload: InvitationAccept,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> InvitationAcceptResponse:
    try:
        tenant_id = UUID(payload.token.split(".", 1)[0])
    except (ValueError, IndexError):
        raise HTTPException(status_code=404, detail="Invitation not found") from None
    set_tenant_context(db, tenant_id)
    token_hash = hashlib.sha256(payload.token.encode()).hexdigest()
    invitation = db.query(TeamInvitation).filter(
        TeamInvitation.tenant_id == tenant_id,
        TeamInvitation.token_hash == token_hash,
    ).one_or_none()
    now = datetime.now(timezone.utc)
    if (
        invitation is None
        or invitation.accepted_at is not None
        or invitation.revoked_at is not None
        or _as_utc(invitation.expires_at) <= now
    ):
        raise HTTPException(status_code=404, detail="Invitation not found")

    user = db.query(User).filter(User.email == invitation.email).one_or_none()
    if user is None:
        if payload.full_name is None:
            raise HTTPException(status_code=422, detail="full_name is required for a new user")
        user = User(
            email=invitation.email,
            full_name=payload.full_name,
            password_hash=hash_password(payload.password),
        )
        db.add(user)
        db.flush()
    elif not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    elif not user.is_active:
        raise HTTPException(status_code=403, detail="User is inactive")

    existing = db.query(Membership).filter(
        Membership.tenant_id == tenant_id, Membership.user_id == user.id
    ).one_or_none()
    if existing is not None:
        raise HTTPException(status_code=409, detail="User is already a member")
    db.add(
        Membership(
            tenant_id=tenant_id,
            user_id=user.id,
            role=invitation.role,
            team_id=invitation.team_id,
            manager_membership_id=invitation.manager_membership_id,
            is_active=True,
        )
    )
    invitation.accepted_at = now
    db.commit()
    ip, agent = _client(request)
    access, refresh, _ = AuthService(db).create_session(user, ip, agent)
    _set_refresh_cookie(response, refresh)
    return InvitationAcceptResponse(access_token=access, user_id=user.id, tenant_id=tenant_id)


def _authenticated(access: str, user: User, tenants: list[Tenant]) -> LoginResponse:
    return LoginResponse(
        status="authenticated",
        access_token=access,
        user_id=user.id,
        tenants=[TenantResponse.model_validate(tenant) for tenant in tenants],
    )


def _active_tenants(user: User) -> list[Tenant]:
    return [
        membership.tenant
        for membership in user.memberships
        if membership.is_active and membership.tenant.is_active
    ]


def _client(request: Request) -> tuple[str, str]:
    return (
        request.client.host if request.client else "unknown",
        request.headers.get("user-agent", "unknown")[:500],
    )


def _check_rate(service: AuthService, action: str, identity: str, ip: str) -> None:
    try:
        service.ensure_allowed(action, identity, ip)
    except RateLimitedError as error:
        raise HTTPException(
            status_code=429,
            detail="Too many attempts. Try again later.",
            headers={"Retry-After": str(error.retry_after)},
        ) from error


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        REFRESH_COOKIE,
        token,
        max_age=settings.refresh_token_expire_days * 86400,
        path="/auth",
        secure=settings.auth_cookie_secure or settings.app_environment == "production",
        httponly=True,
        samesite="lax",
    )


def _delete_refresh_cookie(response: Response) -> None:
    response.delete_cookie(REFRESH_COOKIE, path="/auth")


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
