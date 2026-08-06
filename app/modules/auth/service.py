import base64
import hashlib
import hmac
import json
import secrets
import smtplib
import struct
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from urllib.parse import quote
from uuid import UUID, uuid4

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, hash_password, verify_password
from app.modules.accounts.models import (
    AuthEvent,
    AuthRateLimit,
    AuthToken,
    User,
    UserSession,
)


REFRESH_COOKIE = "crm_refresh_token"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


class AuthService:
    def __init__(self, db: Session):
        self.db = db

    def ensure_allowed(self, action: str, identity: str, ip_address: str) -> None:
        now = utc_now()
        for raw_key in (f"{action}:identity:{identity.lower()}", f"{action}:ip:{ip_address}"):
            key_hash = self._hash(raw_key)
            row = self.db.query(AuthRateLimit).filter(AuthRateLimit.key_hash == key_hash).one_or_none()
            if row and row.blocked_until and as_utc(row.blocked_until) > now:
                raise RateLimitedError(max(1, int((as_utc(row.blocked_until) - now).total_seconds())))

    def record_failure(self, action: str, identity: str, ip_address: str) -> None:
        now = utc_now()
        window = timedelta(minutes=settings.auth_rate_limit_window_minutes)
        for raw_key in (f"{action}:identity:{identity.lower()}", f"{action}:ip:{ip_address}"):
            key_hash = self._hash(raw_key)
            row = self.db.query(AuthRateLimit).filter(AuthRateLimit.key_hash == key_hash).one_or_none()
            if row is None:
                row = AuthRateLimit(
                    key_hash=key_hash,
                    action=action,
                    attempts=0,
                    window_started_at=now,
                )
                self.db.add(row)
            elif as_utc(row.window_started_at) + window <= now:
                row.attempts = 0
                row.window_started_at = now
                row.blocked_until = None
            row.attempts += 1
            if row.attempts >= settings.auth_rate_limit_max_attempts:
                row.blocked_until = now + window
        self.db.commit()

    def clear_failures(self, action: str, identity: str, ip_address: str) -> None:
        hashes = [self._hash(f"{action}:identity:{identity.lower()}")]
        self.db.query(AuthRateLimit).filter(AuthRateLimit.key_hash.in_(hashes)).delete(
            synchronize_session=False
        )
        self.db.commit()

    def create_session(self, user: User, ip_address: str, user_agent: str) -> tuple[str, str, UserSession]:
        raw_refresh = secrets.token_urlsafe(48)
        now = utc_now()
        session = UserSession(
            user_id=user.id,
            family_id=uuid4(),
            refresh_token_hash=self._hash(raw_refresh),
            ip_address=ip_address,
            user_agent=user_agent[:500],
            expires_at=now + timedelta(days=settings.refresh_token_expire_days),
        )
        self.db.add(session)
        self.db.flush()
        self.log_event("session.created", user.id, ip_address, user_agent, {"session_id": str(session.id)})
        self.db.commit()
        return create_access_token(user.id, session.id), raw_refresh, session

    def rotate_session(self, raw_refresh: str, ip_address: str, user_agent: str) -> tuple[str, str, UserSession]:
        token_hash = self._hash(raw_refresh)
        session = self.db.query(UserSession).filter(UserSession.refresh_token_hash == token_hash).one_or_none()
        now = utc_now()
        if session is None:
            raise InvalidSessionError()
        if session.revoked_at is not None:
            if session.replaced_by_id is not None:
                self.revoke_family(session.family_id, "refresh_reuse")
                self.log_event("session.refresh_reuse", session.user_id, ip_address, user_agent)
                self.db.commit()
            raise InvalidSessionError()
        if as_utc(session.expires_at) <= now:
            session.revoked_at = now
            session.revoke_reason = "expired"
            self.db.commit()
            raise InvalidSessionError()

        user = self.db.get(User, session.user_id)
        if user is None or not user.is_active:
            self.revoke_family(session.family_id, "user_inactive")
            self.db.commit()
            raise InvalidSessionError()

        new_raw = secrets.token_urlsafe(48)
        replacement = UserSession(
            user_id=user.id,
            family_id=session.family_id,
            refresh_token_hash=self._hash(new_raw),
            ip_address=ip_address,
            user_agent=user_agent[:500],
            expires_at=now + timedelta(days=settings.refresh_token_expire_days),
        )
        self.db.add(replacement)
        self.db.flush()
        session.revoked_at = now
        session.revoke_reason = "rotated"
        session.replaced_by_id = replacement.id
        session.last_used_at = now
        self.log_event("session.refreshed", user.id, ip_address, user_agent, {"session_id": str(replacement.id)})
        self.db.commit()
        return create_access_token(user.id, replacement.id), new_raw, replacement

    def revoke_session(self, user_id: UUID, session_id: UUID, reason: str = "logout") -> bool:
        session = self.db.query(UserSession).filter(
            UserSession.id == session_id, UserSession.user_id == user_id
        ).one_or_none()
        if session is None:
            return False
        if session.revoked_at is None:
            session.revoked_at = utc_now()
            session.revoke_reason = reason
        self.db.commit()
        return True

    def revoke_other_sessions(self, user_id: UUID, current_session_id: UUID) -> int:
        sessions = self.db.query(UserSession).filter(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
            UserSession.id != current_session_id,
        ).all()
        now = utc_now()
        for session in sessions:
            session.revoked_at = now
            session.revoke_reason = "revoked_by_user"
        self.db.commit()
        return len(sessions)

    def revoke_all_sessions(self, user_id: UUID, reason: str) -> None:
        now = utc_now()
        for session in self.db.query(UserSession).filter(
            UserSession.user_id == user_id, UserSession.revoked_at.is_(None)
        ).all():
            session.revoked_at = now
            session.revoke_reason = reason
        self.db.commit()

    def revoke_family(self, family_id: UUID, reason: str) -> None:
        now = utc_now()
        for session in self.db.query(UserSession).filter(
            UserSession.family_id == family_id, UserSession.revoked_at.is_(None)
        ).all():
            session.revoked_at = now
            session.revoke_reason = reason

    def list_sessions(self, user_id: UUID) -> list[UserSession]:
        return self.db.query(UserSession).filter(
            UserSession.user_id == user_id,
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > utc_now(),
        ).order_by(UserSession.last_used_at.desc()).all()

    def create_auth_token(self, user_id: UUID, purpose: str, ip_address: str, minutes: int) -> str:
        now = utc_now()
        self.db.query(AuthToken).filter(
            AuthToken.user_id == user_id,
            AuthToken.purpose == purpose,
            AuthToken.consumed_at.is_(None),
        ).update({"consumed_at": now}, synchronize_session=False)
        raw = secrets.token_urlsafe(40)
        self.db.add(
            AuthToken(
                user_id=user_id,
                purpose=purpose,
                token_hash=self._hash(raw),
                ip_address=ip_address,
                expires_at=now + timedelta(minutes=minutes),
            )
        )
        self.db.commit()
        return raw

    def consume_auth_token(self, raw_token: str, purpose: str, max_attempts: int = 5) -> AuthToken:
        row = self.db.query(AuthToken).filter(
            AuthToken.token_hash == self._hash(raw_token), AuthToken.purpose == purpose
        ).one_or_none()
        if (
            row is None
            or row.consumed_at is not None
            or as_utc(row.expires_at) <= utc_now()
            or row.attempts >= max_attempts
        ):
            raise InvalidAuthTokenError()
        return row

    def request_password_reset(self, user: User, ip_address: str, user_agent: str) -> str:
        raw = self.create_auth_token(
            user.id,
            "password_reset",
            ip_address,
            settings.auth_reset_token_expire_minutes,
        )
        reset_url = f"{settings.frontend_url.rstrip('/')}/login?reset_token={quote(raw)}"
        self._send_reset_email(user.email, reset_url)
        self.log_event("password.reset_requested", user.id, ip_address, user_agent)
        self.db.commit()
        return raw

    def reset_password(self, raw_token: str, new_password: str, ip_address: str, user_agent: str) -> User:
        token = self.consume_auth_token(raw_token, "password_reset")
        user = self.db.get(User, token.user_id)
        if user is None or not user.is_active:
            raise InvalidAuthTokenError()
        token.consumed_at = utc_now()
        user.password_hash = hash_password(new_password)
        user.password_changed_at = utc_now()
        self.revoke_all_sessions(user.id, "password_reset")
        self.log_event("password.reset_completed", user.id, ip_address, user_agent)
        self.db.commit()
        return user

    def change_password(self, user: User, current_password: str, new_password: str, ip_address: str, user_agent: str) -> None:
        if not verify_password(current_password, user.password_hash):
            raise InvalidPasswordError()
        user.password_hash = hash_password(new_password)
        user.password_changed_at = utc_now()
        self.revoke_all_sessions(user.id, "password_changed")
        self.log_event("password.changed", user.id, ip_address, user_agent)
        self.db.commit()

    def begin_mfa_setup(self, user: User) -> tuple[str, str]:
        secret = base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")
        user.mfa_pending_secret_encrypted = self._encrypt(secret)
        self.db.commit()
        label = quote(f"{settings.app_name}:{user.email}")
        issuer = quote(settings.app_name)
        return secret, f"otpauth://totp/{label}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"

    def enable_mfa(self, user: User, code: str, ip_address: str, user_agent: str) -> list[str]:
        if not user.mfa_pending_secret_encrypted:
            raise MfaSetupRequiredError()
        secret = self._decrypt(user.mfa_pending_secret_encrypted)
        if not verify_totp(secret, code):
            raise InvalidMfaCodeError()
        recovery_codes = [f"{secrets.token_hex(4)}-{secrets.token_hex(4)}" for _ in range(10)]
        user.mfa_secret_encrypted = user.mfa_pending_secret_encrypted
        user.mfa_pending_secret_encrypted = None
        user.mfa_enabled = True
        user.mfa_enabled_at = utc_now()
        user.mfa_recovery_codes_json = json.dumps(
            [self._recovery_hash(user.id, code) for code in recovery_codes]
        )
        self.log_event("mfa.enabled", user.id, ip_address, user_agent)
        self.db.commit()
        return recovery_codes

    def verify_user_mfa(self, user: User, code: str) -> bool:
        if user.mfa_secret_encrypted and verify_totp(self._decrypt(user.mfa_secret_encrypted), code):
            return True
        hashes = json.loads(user.mfa_recovery_codes_json or "[]")
        candidate = self._recovery_hash(user.id, code.lower())
        if candidate in hashes:
            hashes.remove(candidate)
            user.mfa_recovery_codes_json = json.dumps(hashes)
            return True
        return False

    def disable_mfa(self, user: User, password: str, code: str, ip_address: str, user_agent: str) -> None:
        if not verify_password(password, user.password_hash) or not self.verify_user_mfa(user, code):
            raise InvalidMfaCodeError()
        user.mfa_enabled = False
        user.mfa_secret_encrypted = None
        user.mfa_pending_secret_encrypted = None
        user.mfa_recovery_codes_json = "[]"
        user.mfa_enabled_at = None
        self.log_event("mfa.disabled", user.id, ip_address, user_agent)
        self.db.commit()

    def regenerate_recovery_codes(self, user: User, code: str) -> list[str]:
        if not self.verify_user_mfa(user, code):
            raise InvalidMfaCodeError()
        recovery_codes = [f"{secrets.token_hex(4)}-{secrets.token_hex(4)}" for _ in range(10)]
        user.mfa_recovery_codes_json = json.dumps(
            [self._recovery_hash(user.id, value) for value in recovery_codes]
        )
        self.db.commit()
        return recovery_codes

    def log_event(
        self,
        event_type: str,
        user_id: UUID | None,
        ip_address: str,
        user_agent: str,
        metadata: dict | None = None,
    ) -> None:
        self.db.add(
            AuthEvent(
                user_id=user_id,
                event_type=event_type,
                ip_address=ip_address,
                user_agent=user_agent[:500],
                metadata_json=json.dumps(metadata or {}),
            )
        )

    def _send_reset_email(self, recipient: str, reset_url: str) -> None:
        if not settings.auth_smtp_host or not settings.auth_smtp_from_email:
            if settings.app_environment == "production":
                raise RuntimeError("Transactional SMTP is not configured")
            return
        message = EmailMessage()
        message["Subject"] = f"Восстановление доступа — {settings.app_name}"
        message["From"] = settings.auth_smtp_from_email
        message["To"] = recipient
        message.set_content(
            "Для смены пароля откройте ссылку. Если вы не запрашивали восстановление, проигнорируйте письмо.\n\n"
            f"{reset_url}\n\nСсылка действует {settings.auth_reset_token_expire_minutes} минут."
        )
        with smtplib.SMTP(settings.auth_smtp_host, settings.auth_smtp_port, timeout=10) as client:
            if settings.auth_smtp_use_tls:
                client.starttls()
            if settings.auth_smtp_username:
                client.login(settings.auth_smtp_username, settings.auth_smtp_password or "")
            client.send_message(message)

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()

    @staticmethod
    def _recovery_hash(user_id: UUID, value: str) -> str:
        return hashlib.sha256(f"{user_id}:{value.lower()}".encode()).hexdigest()

    @staticmethod
    def _fernet() -> Fernet:
        key = base64.urlsafe_b64encode(hashlib.sha256(settings.secret_key.encode()).digest())
        return Fernet(key)

    def _encrypt(self, value: str) -> str:
        return self._fernet().encrypt(value.encode()).decode("ascii")

    def _decrypt(self, value: str) -> str:
        try:
            return self._fernet().decrypt(value.encode()).decode()
        except InvalidToken as error:
            raise ValueError("MFA secret cannot be decrypted") from error


def totp_code(secret: str, timestamp: int | None = None) -> str:
    counter = int((timestamp if timestamp is not None else time.time()) // 30)
    padded = secret + "=" * ((8 - len(secret) % 8) % 8)
    key = base64.b32decode(padded, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = (struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF) % 1_000_000
    return f"{value:06d}"


def verify_totp(secret: str, code: str) -> bool:
    normalized = code.replace(" ", "")
    now = int(time.time())
    return any(hmac.compare_digest(totp_code(secret, now + offset * 30), normalized) for offset in (-1, 0, 1))


class RateLimitedError(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after


class InvalidSessionError(Exception):
    pass


class InvalidAuthTokenError(Exception):
    pass


class InvalidPasswordError(Exception):
    pass


class InvalidMfaCodeError(Exception):
    pass


class MfaSetupRequiredError(Exception):
    pass
