from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import IpLoginTracker


def test_ip_failure_policy_report_and_admin_reset():
    with TestClient(app,client=("198.51.100.20",50000)) as client:
        admin=client.post("/api/v1/auth/token",json={"email":"admin@example.com","password":"change-me-now"})
        assert admin.status_code==200
        headers={"Authorization":f"Bearer {admin.json()['access_token']}"}
        for _ in range(5):
            assert client.post("/api/v1/auth/token",json={"email":"missing@example.com","password":"wrong-password"}).status_code==401
        assert client.post("/api/v1/auth/token",json={"email":"admin@example.com","password":"change-me-now"}).status_code==429
        report=client.post("/api/v1/reports/ip_tracker/runs",headers=headers,json={"only_auto_blocked":True})
        assert report.status_code==201 and report.json()["row_count"]==1
        row=report.json()["rows"][0]
        assert row["ip_address"]=="198.51.100.20" and row["total_failed_logins"]==5 and row["auto_blocked"] is True
        with SessionLocal() as db: tracker_id=db.query(IpLoginTracker).filter_by(ip_string="198.51.100.20").one().id
        reset=client.patch(f"/api/v1/admin/ip-trackers/{tracker_id}",headers=headers,json={"reset_applicable_failures":True,"force_block":False})
        assert reset.status_code==200 and reset.json()["applicable_failed_logins"]==0
        assert client.post("/api/v1/auth/token",json={"email":"admin@example.com","password":"change-me-now"}).status_code==200


def test_manual_ip_block_denies_valid_credentials():
    with TestClient(app,client=("203.0.113.9",50000)) as client:
        first=client.post("/api/v1/auth/token",json={"email":"admin@example.com","password":"change-me-now"});headers={"Authorization":f"Bearer {first.json()['access_token']}"}
        client.post("/api/v1/auth/token",json={"email":"none@example.com","password":"wrong"})
        with SessionLocal() as db: tracker_id=db.query(IpLoginTracker).filter_by(ip_string="203.0.113.9").one().id
        assert client.patch(f"/api/v1/admin/ip-trackers/{tracker_id}",headers=headers,json={"force_block":True,"skip_timing_protection":True}).status_code==200
        assert client.post("/api/v1/auth/token",json={"email":"admin@example.com","password":"change-me-now"}).status_code==429
