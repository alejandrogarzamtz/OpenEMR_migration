from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import CommunicationDelivery, User
from app.security import password_hash


def test_refresh_rotation_detects_reuse_and_revokes_session():
    with TestClient(app) as client:
        login = client.post("/api/v1/auth/token", json={"email": "admin@example.com", "password": "change-me-now"})
        assert login.status_code == 200
        access_token = login.json()["access_token"]
        old_refresh = client.cookies.get("staff_refresh_token")
        assert old_refresh

        refreshed = client.post("/api/v1/auth/refresh")
        assert refreshed.status_code == 200
        new_access_token = refreshed.json()["access_token"]
        assert new_access_token != access_token
        assert client.cookies.get("staff_refresh_token") != old_refresh
        assert client.get("/api/v1/patients", headers={"Authorization": f"Bearer {access_token}"}).status_code == 401

        client.cookies.set("staff_refresh_token", old_refresh, path="/api/v1/auth")
        replay = client.post("/api/v1/auth/refresh")
        assert replay.status_code == 401
        assert client.get("/api/v1/patients", headers={"Authorization": f"Bearer {new_access_token}"}).status_code == 401


def test_logout_revokes_access_immediately():
    with TestClient(app) as client:
        login = client.post("/api/v1/auth/token", json={"email": "admin@example.com", "password": "change-me-now"})
        token = login.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
        assert client.get("/api/v1/patients", headers=headers).status_code == 401
        assert client.post("/api/v1/auth/refresh").status_code == 401


def test_password_reset_is_non_enumerating_one_time_and_revokes_sessions():
    with TestClient(app) as client:
        with SessionLocal() as db:
            db.add(User(email="reset-user@example.com", password_hash=password_hash.hash("original-password-123"), role="clinician", permissions=["patients:demo:read"]))
            db.commit()
        login = client.post("/api/v1/auth/token", json={"email": "reset-user@example.com", "password": "original-password-123"})
        old_access = login.json()["access_token"]
        existing = client.post("/api/v1/auth/password-reset/request", json={"email": "reset-user@example.com"})
        missing = client.post("/api/v1/auth/password-reset/request", json={"email": "absent@example.com"})
        assert existing.status_code == missing.status_code == 202
        assert existing.json() == missing.json()

        with SessionLocal() as db:
            delivery = db.scalar(select(CommunicationDelivery).where(CommunicationDelivery.recipient == "reset-user@example.com", CommunicationDelivery.template_name == "staff-password-reset").order_by(CommunicationDelivery.id.desc()))
            token = parse_qs(urlparse(delivery.body.split()[-1]).query)["token"][0]

        confirmed = client.post("/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": "replacement-password-789"})
        assert confirmed.status_code == 204
        assert client.get("/api/v1/patients", headers={"Authorization": f"Bearer {old_access}"}).status_code == 401
        assert client.post("/api/v1/auth/password-reset/confirm", json={"token": token, "new_password": "another-password-789"}).status_code == 400
        assert client.post("/api/v1/auth/token", json={"email": "reset-user@example.com", "password": "original-password-123"}).status_code == 401
        assert client.post("/api/v1/auth/token", json={"email": "reset-user@example.com", "password": "replacement-password-789"}).status_code == 200
