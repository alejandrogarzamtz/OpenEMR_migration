from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import User
from app.security import password_hash


def admin_headers(client: TestClient):
    token=client.post("/api/v1/auth/token",json={"email":"admin@example.com","password":"change-me-now"}).json()["access_token"]
    return {"Authorization":f"Bearer {token}"}


def test_report_catalog_snapshots_filters_checksums_and_csv_export():
    with TestClient(app) as client:
        headers=admin_headers(client)
        catalog=client.get("/api/v1/reports",headers=headers)
        assert catalog.status_code==200 and len(catalog.json())==48
        assert sum(item["migrated"] for item in catalog.json())==21
        patient=client.post("/api/v1/patients",headers=headers,json={"first_name":"Report","last_name":"Fixture","date_of_birth":"1988-02-03","sex":"unknown"}).json()
        appointment=client.post("/api/v1/appointments",headers=headers,json={"patient_uuid":patient["uuid"],"starts_at":"2027-02-10T10:00:00Z","ends_at":"2027-02-10T10:30:00Z","title":"Annual visit"})
        assert appointment.status_code==201
        report=client.post("/api/v1/reports/appointments_report/runs",headers=headers,json={"date_from":"2027-02-10","date_to":"2027-02-10"})
        assert report.status_code==201
        payload=report.json(); assert payload["columns"]==["appointment_uuid","starts_at","patient","status","provider","facility","room"]
        assert payload["row_count"]==1 and payload["rows"][0]["patient"]=="Fixture, Report"
        assert len(payload["checksum"])==64
        stored=client.get(f"/api/v1/report-runs/{payload['uuid']}",headers=headers)
        assert stored.json()["checksum"]==payload["checksum"]
        exported=client.get(f"/api/v1/report-runs/{payload['uuid']}/export.csv",headers=headers)
        assert exported.status_code==200
        assert exported.headers["x-report-checksum"]==payload["checksum"]
        assert exported.text.splitlines()[0]=="appointment_uuid,starts_at,patient,status,provider,facility,room"
        with SessionLocal() as db:
            db.add(User(email="report-reader@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["patients:appt:read"]));db.commit()
        reader_token=client.post("/api/v1/auth/token",json={"email":"report-reader@example.com","password":"report-password"}).json()["access_token"]
        reader_headers={"Authorization":f"Bearer {reader_token}"}
        assert client.get(f"/api/v1/report-runs/{payload['uuid']}",headers=reader_headers).status_code==403
        assert client.get(f"/api/v1/report-runs/{payload['uuid']}/export.csv",headers=reader_headers).status_code==403
        assert client.post("/api/v1/reports/cqm/runs",headers=headers,json={}).status_code==501
        assert client.post("/api/v1/reports/appointments_report/runs",headers=headers,json={"date_from":"2027-02-11","date_to":"2027-02-10"}).status_code==422


def test_report_execution_enforces_each_catalog_permission():
    with TestClient(app) as client:
        with SessionLocal() as db:
            db.add(User(email="report-denied@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["patients:demo:read"]));db.commit()
        token=client.post("/api/v1/auth/token",json={"email":"report-denied@example.com","password":"report-password"}).json()["access_token"]
        headers={"Authorization":f"Bearer {token}"}
        assert client.get("/api/v1/reports",headers=headers).status_code==200
        assert client.post("/api/v1/reports/patient_list/runs",headers=headers,json={}).status_code==403
        assert client.post("/api/v1/reports/inventory_list/runs",headers=headers,json={}).status_code==403
