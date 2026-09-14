from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import BackgroundService, User
from app.security import password_hash


def headers(client, email="admin@example.com", password="change-me-now"):
    token=client.post("/api/v1/auth/token",json={"email":email,"password":password}).json()["access_token"]
    return {"Authorization":f"Bearer {token}"}


def test_background_service_report_uses_live_lease_and_schedule_semantics():
    now=datetime.now(timezone.utc).replace(microsecond=0)
    with TestClient(app) as client:
        with SessionLocal() as db:
            db.add_all([
                BackgroundService(name="email",title="Email delivery",active=True,running_state=0,next_run=now+timedelta(minutes=5),execute_interval_minutes=5,handler="deliver_email",sort_order=20,lock_expires_at=now+timedelta(minutes=1)),
                BackgroundService(name="manual",title="Manual maintenance",active=True,running_state=-1,next_run=now,execute_interval_minutes=0,handler="maintain",sort_order=10,lock_expires_at=now-timedelta(minutes=1)),
                BackgroundService(name="off",title="Disabled worker",active=False,running_state=0,next_run=now,execute_interval_minutes=10,handler="disabled",sort_order=30),
            ]);db.commit()
        auth=headers(client)
        result=client.post("/api/v1/reports/background_services/runs",headers=auth,json={})
        assert result.status_code==201
        payload=result.json();assert [row["name"] for row in payload["rows"]]==["manual","email","off"]
        assert payload["totals"]=={"services":3,"active":2,"automatic":1,"busy":1}
        email=payload["rows"][1]
        assert email["currently_busy"] is True and email["automatic"] is True and email["interval_minutes"]==5
        assert email["last_run_started_at"]==now.isoformat()
        assert payload["rows"][0]["next_scheduled_run"] is None and payload["rows"][2]["interval_minutes"] is None
        export=client.get(f"/api/v1/report-runs/{payload['uuid']}/export.csv",headers=auth)
        assert export.status_code==200 and export.headers["x-report-checksum"]==payload["checksum"]


def test_background_service_report_requires_super_admin_permission():
    with TestClient(app) as client:
        with SessionLocal() as db:
            db.add(User(email="operations@example.com",password_hash=password_hash.hash("operations-password"),role="viewer",permissions=["patients:demo:read"]));db.commit()
        assert client.post("/api/v1/reports/background_services/runs",headers=headers(client,"operations@example.com","operations-password"),json={}).status_code==403
