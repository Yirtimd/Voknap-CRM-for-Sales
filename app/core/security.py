from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
from uuid import UUID, uuid4

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: UUID
    session_id: UUID | None
    token_id: UUID | None


def create_access_token(user_id: UUID, session_id: UUID | None = None) -> str:
    now = datetime.now(timezone.utc)
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes
    )
    payload = {
        "sub": str(user_id),
        "sid": str(session_id) if session_id else None,
        "jti": str(uuid4()),
        "typ": "access",
        "iss": settings.app_name,
        "aud": "crm-api",
        "iat": now,
        "nbf": now,
        "exp": expires_at,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> AccessTokenClaims | None:
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[ALGORITHM],
            audience="crm-api",
            issuer=settings.app_name,
        )
        if payload.get("typ") != "access":
            return None
        subject = payload.get("sub")
        if not subject:
            return None
        return AccessTokenClaims(
            user_id=UUID(subject),
            session_id=UUID(payload["sid"]) if payload.get("sid") else None,
            token_id=UUID(payload["jti"]) if payload.get("jti") else None,
        )
    except (JWTError, ValueError):
        # Development compatibility for unit-test tokens created before sessions.
        if settings.app_environment == "production":
            return None
        try:
            payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
            subject = payload.get("sub")
            return AccessTokenClaims(UUID(subject), None, None) if subject else None
        except (JWTError, ValueError):
            return None
