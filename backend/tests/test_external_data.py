from datetime import date

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import AuditEvent, ExternalEncounter, ExternalProcedure, Patient


def test_external_clinical_data_patient_view_and_report():
    with TestClient(app) as client:
        token=client.post("/api/v1/auth/token",json={"email":"admin@example.com","password":"change-me-now"}).json()["access_token"];headers={"Authorization":f"Bearer {token}"}
        patient=client.post("/api/v1/patients",headers=headers,json={"first_name":"External","last_name":"Patient","date_of_birth":"1980-01-02","sex":"unknown"}).json()
        with SessionLocal() as db:
            stored=db.query(Patient).filter(Patient.uuid==patient["uuid"]).one()
            db.add(ExternalEncounter(patient_id=stored.id,occurred_on=date(2027,5,2),diagnosis="Remote diagnosis",provider_name="Dr Rivera",facility_name="Partner Clinic",external_id="ENC-9"))
            db.add(ExternalProcedure(patient_id=stored.id,occurred_on=date(2027,5,3),code_system="CPT",code="71045",code_text="Chest radiograph",facility_name="Partner Imaging",external_id="PROC-4"));db.commit()
        response=client.get(f"/api/v1/patients/{patient['uuid']}/external-data",headers=headers)
        assert response.status_code==200 and response.json()["encounters"][0]["provider_name"]=="Dr Rivera"
        assert response.json()["procedures"][0]["code"]=="71045"
        missing=client.post("/api/v1/reports/external_data/runs",headers=headers,json={})
        assert missing.status_code==422
        report=client.post("/api/v1/reports/external_data/runs",headers=headers,json={"patient_uuid":patient["uuid"],"date_from":"2027-05-01","date_to":"2027-05-31"})
        assert report.status_code==201 and report.json()["row_count"]==2
        assert report.json()["totals"]=={"records":2,"encounters":1,"procedures":1}
        assert report.json()["rows"][0]["code"]=="CPT:71045"
        export=client.get(f"/api/v1/report-runs/{report.json()['uuid']}/export.csv",headers=headers)
        assert export.status_code==200 and "record_uuid,record_type,date,code,description,provider,facility,external_id" in export.text
        with SessionLocal() as db:
            assert db.query(AuditEvent).filter(AuditEvent.resource_type=="external_clinical_data",AuditEvent.resource_id==patient["uuid"]).count()==1
