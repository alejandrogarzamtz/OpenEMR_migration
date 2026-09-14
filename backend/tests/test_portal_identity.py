import time
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.mfa import totp_at
from app.models import CommunicationDelivery, PortalAccount, PortalMfaRegistration
from test_communications import create_patient, create_portal, staff_headers


def test_portal_password_reset_is_non_enumerating_one_time_and_revokes_sessions():
    with TestClient(app) as client:
        staff = staff_headers(client)
        patient = create_patient(client, staff, "PortalReset")
        portal = create_portal(client, staff, patient, "portal-reset")
        old_access = portal["Authorization"]
        assert client.post("/api/v1/portal/password", headers={"Authorization": old_access}, json={"current_password": "wrong-password", "new_password": "not-accepted-password-789"}).status_code == 401

        existing = client.post("/api/v1/portal/auth/password-reset/request", json={"email": patient["email"]})
        repeated = client.post("/api/v1/portal/auth/password-reset/request", json={"email": patient["email"].upper()})
        missing = client.post("/api/v1/portal/auth/password-reset/request", json={"email": "absent-portal@example.com"})
        assert existing.status_code == repeated.status_code == missing.status_code == 202
        assert existing.json() == repeated.json() == missing.json()
        with SessionLocal() as db:
            deliveries = list(db.scalars(select(CommunicationDelivery).where(CommunicationDelivery.recipient == patient["email"], CommunicationDelivery.template_name == "portal-password-reset").order_by(CommunicationDelivery.id.desc())))
            assert len(deliveries) == 1
            delivery = deliveries[0]
            token = parse_qs(urlparse(delivery.body.split()[-1]).query)["token"][0]

        confirmed = client.post("/api/v1/portal/auth/password-reset/confirm", json={"token": token, "new_password": "new-portal-password-789"})
        assert confirmed.status_code == 204
        assert client.get("/api/v1/portal/messages", headers={"Authorization": old_access}).status_code == 401
        assert client.post("/api/v1/portal/auth/password-reset/confirm", json={"token": token, "new_password": "another-portal-password-789"}).status_code == 400
        assert client.post("/api/v1/portal/auth/token", json={"username": "portal-reset", "password": "permanent-password-456"}).status_code == 401
        assert client.post("/api/v1/portal/auth/token", json={"username": "portal-reset", "password": "new-portal-password-789"}).status_code == 200


def test_portal_totp_enrollment_challenge_recovery_replay_and_disable():
    with TestClient(app) as client:
        staff = staff_headers(client)
        patient = create_patient(client, staff, "PortalMfa")
        portal = create_portal(client, staff, patient, "portal-mfa")
        enrollment = client.post("/api/v1/portal/mfa/enroll", headers=portal, json={"password": "permanent-password-456"})
        assert enrollment.status_code == 200
        secret = enrollment.json()["secret"]
        with SessionLocal() as db:
            account = db.scalar(select(PortalAccount).where(PortalAccount.username == "portal-mfa"))
            registration = db.scalar(select(PortalMfaRegistration).where(PortalMfaRegistration.portal_account_id == account.id))
            assert secret.encode() not in registration.encrypted_secret

        current_step = int(time.time()) // 30
        confirmed = client.post("/api/v1/portal/mfa/confirm", headers=portal, json={"code": totp_at(secret, current_step)})
        assert confirmed.status_code == 200
        recovery_codes = confirmed.json()["recovery_codes"]
        assert len(recovery_codes) == 10
        assert client.get("/api/v1/auth/mfa", headers=portal).status_code == 401
        assert client.post("/api/v1/portal/auth/logout", headers=portal).status_code == 204

        login = client.post("/api/v1/portal/auth/token", json={"username": "portal-mfa", "password": "permanent-password-456"})
        assert login.json()["mfa_required"] is True
        assert login.json()["access_token"] is None
        completed = client.post("/api/v1/portal/auth/mfa/challenge", json={"challenge_token": login.json()["challenge_token"], "code": totp_at(secret, current_step + 1)})
        assert completed.status_code == 200
        mfa_headers = {"Authorization": f"Bearer {completed.json()['access_token']}"}
        assert client.get("/api/v1/portal/mfa", headers=mfa_headers).json()["enabled"] is True

        replay_challenge = client.post("/api/v1/portal/auth/token", json={"username": "portal-mfa", "password": "permanent-password-456"}).json()["challenge_token"]
        assert client.post("/api/v1/portal/auth/mfa/challenge", json={"challenge_token": replay_challenge, "code": totp_at(secret, current_step + 1)}).status_code == 401
        recovered = client.post("/api/v1/portal/auth/mfa/challenge", json={"challenge_token": replay_challenge, "code": recovery_codes[0]})
        assert recovered.status_code == 200
        recovered_headers = {"Authorization": f"Bearer {recovered.json()['access_token']}"}
        assert client.get("/api/v1/portal/mfa", headers=recovered_headers).json()["recovery_codes_remaining"] == 9

        disabled = client.request("DELETE", "/api/v1/portal/mfa", headers=recovered_headers, json={"password": "permanent-password-456", "code": recovery_codes[1]})
        assert disabled.status_code == 204
        assert client.get("/api/v1/portal/mfa", headers=recovered_headers).json()["enabled"] is False
