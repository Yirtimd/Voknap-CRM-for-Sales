from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import app.main  # noqa: F401
from app.core.database import Base, get_db
from app.core.security import hash_password
from app.main import app
from app.modules.accounts.models import Membership, Tenant, User, UserSession
from app.modules.auth.service import REFRESH_COOKIE, totp_code


PASSWORD = "Pilot-Password-2026!"
NEW_PASSWORD = "Pilot-New-Password-2026!"


@pytest.fixture
def auth_api() -> Generator[dict, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    tenant = Tenant(name="Auth Tenant", slug=f"auth-{uuid4()}")
    user = User(
        email=f"owner-{uuid4()}@example.com",
        full_name="Auth Owner",
        password_hash=hash_password(PASSWORD),
    )
    db.add_all([tenant, user])
    db.flush()
    db.add(Membership(tenant_id=tenant.id, user_id=user.id, role="owner"))
    db.commit()

    def override_db() -> Generator[Session, None, None]:
        yield db

    app.dependency_overrides[get_db] = override_db
    try:
        yield {"client": TestClient(app), "db": db, "tenant": tenant, "user": user}
    finally:
        app.dependency_overrides.clear()
        db.close()


def _login(data: dict, password: str = PASSWORD, client: TestClient | None = None):
    return (client or data["client"]).post(
        "/auth/login",
        json={"email": data["user"].email, "password": password},
    )


def _auth_headers(data: dict, token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "X-Tenant-Id": str(data["tenant"].id)}


def test_login_creates_refresh_session_and_access_token(auth_api):
    response = _login(auth_api)

    assert response.status_code == 200
    assert response.json()["status"] == "authenticated"
    assert response.cookies.get(REFRESH_COOKIE)
    token = response.json()["access_token"]
    assert auth_api["client"].get("/me", headers=_auth_headers(auth_api, token)).status_code == 200
    assert auth_api["db"].query(UserSession).filter(UserSession.user_id == auth_api["user"].id).count() == 1


def test_refresh_rotates_token_and_reuse_revokes_family(auth_api):
    login = _login(auth_api)
    old_refresh = login.cookies.get(REFRESH_COOKIE)
    refreshed = auth_api["client"].post("/auth/refresh")
    new_refresh = refreshed.cookies.get(REFRESH_COOKIE)

    assert refreshed.status_code == 200
    assert new_refresh and new_refresh != old_refresh

    replay = TestClient(app)
    replay.cookies.set(REFRESH_COOKIE, old_refresh, path="/auth")
    assert replay.post("/auth/refresh").status_code == 401

    latest = TestClient(app)
    latest.cookies.set(REFRESH_COOKIE, new_refresh, path="/auth")
    assert latest.post("/auth/refresh").status_code == 401


def test_logout_revokes_current_session(auth_api):
    login = _login(auth_api)
    token = login.json()["access_token"]

    response = auth_api["client"].post("/auth/logout", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 204
    assert auth_api["client"].get("/me", headers=_auth_headers(auth_api, token)).status_code == 401


def test_password_reset_is_one_time_and_revokes_sessions(auth_api):
    login = _login(auth_api)
    token = login.json()["access_token"]
    requested = auth_api["client"].post(
        "/auth/password/reset/request", json={"email": auth_api["user"].email}
    )
    reset_token = requested.json()["dev_reset_token"]

    assert requested.status_code == 200
    assert reset_token
    confirmed = auth_api["client"].post(
        "/auth/password/reset/confirm",
        json={"token": reset_token, "new_password": NEW_PASSWORD},
    )
    assert confirmed.status_code == 204
    assert auth_api["client"].get("/me", headers=_auth_headers(auth_api, token)).status_code == 401
    assert auth_api["client"].post(
        "/auth/password/reset/confirm",
        json={"token": reset_token, "new_password": PASSWORD},
    ).status_code == 400
    assert _login(auth_api).status_code == 401
    assert _login(auth_api, NEW_PASSWORD).status_code == 200


def test_mfa_setup_login_and_recovery_code(auth_api):
    login = _login(auth_api)
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    setup = auth_api["client"].post("/auth/mfa/setup", headers=headers)
    secret = setup.json()["secret"]
    enabled = auth_api["client"].post(
        "/auth/mfa/enable", headers=headers, json={"code": totp_code(secret)}
    )

    assert enabled.status_code == 200
    recovery_code = enabled.json()["recovery_codes"][0]
    second_client = TestClient(app)
    challenge = _login(auth_api, client=second_client)
    assert challenge.json()["status"] == "mfa_required"
    verified = second_client.post(
        "/auth/mfa/verify-login",
        json={"mfa_token": challenge.json()["mfa_token"], "code": recovery_code},
    )
    assert verified.status_code == 200
    assert verified.json()["status"] == "authenticated"

    third_client = TestClient(app)
    challenge = _login(auth_api, client=third_client)
    reused = third_client.post(
        "/auth/mfa/verify-login",
        json={"mfa_token": challenge.json()["mfa_token"], "code": recovery_code},
    )
    assert reused.status_code == 401


def test_login_rate_limit_blocks_repeated_failures(auth_api):
    for _ in range(5):
        assert _login(auth_api, "wrong-password").status_code == 401

    blocked = _login(auth_api)

    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0
