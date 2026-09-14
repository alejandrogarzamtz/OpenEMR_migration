from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import AuditEvent, User
from app.security import password_hash
from test_communications import create_patient, staff_headers


def test_printable_chart_report_is_patient_scoped_escaped_audited_and_permissioned():
    with TestClient(app) as client:
        admin=staff_headers(client);patient=create_patient(client,admin,"ReportOne");other=create_patient(client,admin,"ReportTwo")
        item=client.post(f"/api/v1/patients/{patient['uuid']}/clinical-items",headers=admin,json={"category":"problem","title":"Risk <script>alert(1)</script>"})
        assert item.status_code==201
        with SessionLocal() as db:
            report_user=User(email="report-only@example.com",password_hash=password_hash.hash("report-only-password"),role="records",permissions=["patients:pat_rep:read","patients:demo:read","patients:med:read","patients:docs:read","acct:bill:read"])
            limited_user=User(email="limited-report@example.com",password_hash=password_hash.hash("limited-report-password"),role="records",permissions=["patients:pat_rep:read"])
            denied_user=User(email="no-report@example.com",password_hash=password_hash.hash("no-report-password"),role="viewer",permissions=["patients:demo:read"])
            db.add_all([report_user,limited_user,denied_user]);db.commit()
        report_token=client.post("/api/v1/auth/token",json={"email":"report-only@example.com","password":"report-only-password"}).json()["access_token"]
        denied_token=client.post("/api/v1/auth/token",json={"email":"no-report@example.com","password":"no-report-password"}).json()["access_token"]
        limited_token=client.post("/api/v1/auth/token",json={"email":"limited-report@example.com","password":"limited-report-password"}).json()["access_token"]
        report_headers={"Authorization":f"Bearer {report_token}"};denied_headers={"Authorization":f"Bearer {denied_token}"}
        assert client.get(f"/api/v1/patients/{patient['uuid']}/report.html",headers=denied_headers).status_code==403
        limited=client.get(f"/api/v1/patients/{patient['uuid']}/report.html",headers={"Authorization":f"Bearer {limited_token}"})
        assert limited.status_code==200 and "Restricted by section ACL." in limited.text and "Risk &lt;script" not in limited.text
        invalid=client.get(f"/api/v1/patients/{patient['uuid']}/report.html?start=2026-12-31&end=2026-01-01",headers=report_headers)
        assert invalid.status_code==422
        response=client.get(f"/api/v1/patients/{patient['uuid']}/report.html",headers=report_headers)
        assert response.status_code==200 and response.headers["cache-control"]=="private, no-store"
        assert response.headers["x-report-sha256"] and "ReportOne" in response.text and "ReportTwo" not in response.text
        assert "Risk &lt;script&gt;alert(1)&lt;/script&gt;" in response.text and "Risk <script>" not in response.text
        assert all(section in response.text for section in ("Demographics","Problems, allergies, and medications","Encounters","Laboratory and procedures","Documents","Insurance","Claims"))
        with SessionLocal() as db:
            audit=db.scalar(select(AuditEvent).where(AuditEvent.action=="export",AuditEvent.resource_type=="patient_report",AuditEvent.resource_id==patient["uuid"]).order_by(AuditEvent.id.desc()))
            assert audit and response.headers["x-report-sha256"] in audit.detail
        other_response=client.get(f"/api/v1/patients/{other['uuid']}/report.html",headers=report_headers)
        assert "ReportTwo" in other_response.text and "ReportOne" not in other_response.text
