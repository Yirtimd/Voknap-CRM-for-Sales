from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, model_validator


def validate_bcrypt_password(password: str) -> str:
    if len(password.encode("utf-8")) > 72:
        raise ValueError("Password must be 72 bytes or shorter")
    return password


def validate_new_password(password: str) -> str:
    validate_bcrypt_password(password)
    if len(password) < 12:
        raise ValueError("Password must be at least 12 characters")
    if password.lower() in {"password1234", "qwerty123456", "123456789012"}:
        raise ValueError("Choose a less common password")
    return password


class RegisterCompanyRequest(BaseModel):
    company_name: str = Field(min_length=2, max_length=255)
    company_slug: str = Field(min_length=2, max_length=80, pattern=r"^[a-z0-9-]+$")
    owner_email: EmailStr
    owner_full_name: str = Field(min_length=2, max_length=255)
    owner_password: str = Field(min_length=12, max_length=72)

    @model_validator(mode="after")
    def validate_password(self) -> "RegisterCompanyRequest":
        validate_new_password(self.owner_password)
        return self


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)

    @model_validator(mode="after")
    def validate_password(self) -> "LoginRequest":
        validate_bcrypt_password(self.password)
        return self


class TenantResponse(BaseModel):
    id: UUID
    name: str
    slug: str

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_id: UUID
    tenants: list[TenantResponse]


class LoginResponse(BaseModel):
    status: str
    access_token: str | None = None
    token_type: str = "bearer"
    user_id: UUID | None = None
    tenants: list[TenantResponse] = Field(default_factory=list)
    mfa_token: str | None = None


class MfaLoginRequest(BaseModel):
    mfa_token: str = Field(min_length=32, max_length=255)
    code: str = Field(min_length=6, max_length=32)


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetRequested(BaseModel):
    message: str = "If the account exists, reset instructions were sent"
    dev_reset_token: str | None = None


class PasswordResetConfirm(BaseModel):
    token: str = Field(min_length=32, max_length=255)
    new_password: str = Field(min_length=12, max_length=72)

    @model_validator(mode="after")
    def validate_password(self) -> "PasswordResetConfirm":
        validate_new_password(self.new_password)
        return self


class PasswordChangeRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=12, max_length=72)

    @model_validator(mode="after")
    def validate_password(self) -> "PasswordChangeRequest":
        validate_bcrypt_password(self.current_password)
        validate_new_password(self.new_password)
        return self


class MfaCodeRequest(BaseModel):
    code: str = Field(min_length=6, max_length=32)


class MfaDisableRequest(MfaCodeRequest):
    password: str = Field(min_length=1, max_length=72)


class MfaSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str


class RecoveryCodesResponse(BaseModel):
    recovery_codes: list[str]


class MfaStatusResponse(BaseModel):
    enabled: bool
    enabled_at: datetime | None
    recovery_codes_remaining: int


class SessionResponse(BaseModel):
    id: UUID
    ip_address: str | None
    user_agent: str | None
    created_at: datetime
    last_used_at: datetime
    expires_at: datetime
    current: bool


class SessionRevokeResponse(BaseModel):
    revoked: int
