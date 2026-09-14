import time

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.mfa import totp_at
from app.models import MfaRegistration, User
from app.security import password_hash


def test_totp_enrollment_login_recovery_and_disable_flow():
    with TestClient(app) as client:
        with SessionLocal() as db:
            user = User(email="mfa-user@example.com", password_hash=password_hash.hash("mfa-password-123"), role="clinician", permissions=["patients:demo:read"])
            db.add(user); db.commit(); user_id = user.id

        initial = client.post("/api/v1/auth/token", json={"email":"mfa-user@example.com", "password":"mfa-password-123"})
        headers = {"Authorization": f"Bearer {initial.json()['access_token']}"}
        enrollment = client.post("/api/v1/auth/mfa/enroll", headers=headers, json={"password":"mfa-password-123"})
        assert enrollment.status_code == 200
        secret = enrollment.json()["secret"]
        assert enrollment.json()["provisioning_uri"].startswith("otpauth://totp/")
        with SessionLocal() as db:
            registration = db.scalar(select(MfaRegistration).where(MfaRegistration.user_id == user_id))
            assert secret.encode() not in registration.encrypted_secret

        current_step = int(time.time()) // 30
        confirmed = client.post("/api/v1/auth/mfa/confirm", headers=headers, json={"code":totp_at(secret, current_step)})
        assert confirmed.status_code == 200
        recovery_codes = confirmed.json()["recovery_codes"]
        assert len(recovery_codes) == 10
        assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204

        challenged = client.post("/api/v1/auth/token", json={"email":"mfa-user@example.com", "password":"mfa-password-123"})
        assert challenged.json()["mfa_required"] is True
        assert challenged.json()["access_token"] is None
        completed = client.post("/api/v1/auth/mfa/challenge", json={"challenge_token":challenged.json()["challenge_token"], "code":totp_at(secret, current_step + 1)})
        assert completed.status_code == 200
        totp_headers = {"Authorization": f"Bearer {completed.json()['access_token']}"}
        assert client.get("/api/v1/auth/mfa", headers=totp_headers).json()["enabled"] is True
        assert client.post("/api/v1/auth/logout", headers=totp_headers).status_code == 204

        recovery_challenge = client.post("/api/v1/auth/token", json={"email":"mfa-user@example.com", "password":"mfa-password-123"}).json()["challenge_token"]
        recovered = client.post("/api/v1/auth/mfa/challenge", json={"challenge_token":recovery_challenge, "code":recovery_codes[0]})
        assert recovered.status_code == 200
        recovered_headers = {"Authorization": f"Bearer {recovered.json()['access_token']}"}
        assert client.get("/api/v1/auth/mfa", headers=recovered_headers).json()["recovery_codes_remaining"] == 9

        reused_challenge = client.post("/api/v1/auth/token", json={"email":"mfa-user@example.com", "password":"mfa-password-123"}).json()["challenge_token"]
        assert client.post("/api/v1/auth/mfa/challenge", json={"challenge_token":reused_challenge, "code":recovery_codes[0]}).status_code == 401
        valid_retry = client.post("/api/v1/auth/mfa/challenge", json={"challenge_token":reused_challenge, "code":recovery_codes[1]})
        assert valid_retry.status_code == 200

        disabled = client.request("DELETE", "/api/v1/auth/mfa", headers=recovered_headers, json={"password":"mfa-password-123", "code":recovery_codes[2]})
        assert disabled.status_code == 204
        assert client.get("/api/v1/auth/mfa", headers=recovered_headers).json()["enabled"] is False
