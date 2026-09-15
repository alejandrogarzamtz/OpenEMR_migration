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
        assert sum(item["migrated"] for item in catalog.json())==36
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
        history=client.post("/api/v1/reports/report_results/runs",headers=headers,json={})
        assert history.status_code==201
        appointment_history=next(row for row in history.json()["rows"] if row["run_uuid"]==payload["uuid"])
        assert appointment_history["status"]=="complete" and appointment_history["row_count"]==1
        assert appointment_history["checksum"]==payload["checksum"]
        assert all(row["title"]!="Report Results" for row in history.json()["rows"])
        history_csv=client.get(f"/api/v1/report-runs/{history.json()['uuid']}/export.csv",headers=headers)
        assert history_csv.status_code==200 and history_csv.text.splitlines()[0]=="run_uuid,title,created_at,status,row_count,checksum,actor"
        with SessionLocal() as db:
            db.add(User(email="report-reader@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["patients:appt:read"]));db.commit()
        reader_token=client.post("/api/v1/auth/token",json={"email":"report-reader@example.com","password":"report-password"}).json()["access_token"]
        reader_headers={"Authorization":f"Bearer {reader_token}"}
        assert client.get(f"/api/v1/report-runs/{payload['uuid']}",headers=reader_headers).status_code==403
        assert client.get(f"/api/v1/report-runs/{payload['uuid']}/export.csv",headers=reader_headers).status_code==403
        assert client.post("/api/v1/reports/cqm/runs",headers=headers,json={}).status_code==501
        assert client.post("/api/v1/reports/appointments_report/runs",headers=headers,json={"date_from":"2027-02-11","date_to":"2027-02-10"}).status_code==422


def test_clinical_report_multidimensional_golden_contract():
    with TestClient(app) as client:
        headers=admin_headers(client)
        patient=client.post("/api/v1/patients",headers=headers,json={"first_name":"Clinical","last_name":"Cohort","date_of_birth":"1990-05-04","sex":"female","race":"test-race","ethnicity":"test-ethnicity","email":"clinical-cohort@example.com","allow_email":True}).json()
        facility=client.post("/api/v1/admin/facilities",headers=headers,json={"name":"Clinical Report Clinic"}).json()
        practitioner=client.post("/api/v1/admin/practitioners",headers=headers,json={"first_name":"Report","last_name":"Doctor","primary_facility_uuid":facility["uuid"]}).json()
        client.post(f"/api/v1/patients/{patient['uuid']}/provider-assignments",headers=headers,json={"practitioner_uuid":practitioner["uuid"],"role":"primary","assigned_at":"2026-01-01T00:00:00Z"})
        encounter=client.post("/api/v1/encounters",headers=headers,json={"patient_uuid":patient["uuid"],"occurred_at":"2026-03-01T09:00:00Z","chief_complaint":"Annual review"}).json()
        client.post(f"/api/v1/patients/{patient['uuid']}/clinical-items",headers=headers,json={"category":"problem","title":"Migraine","code":"G43.909"})
        client.post(f"/api/v1/patients/{patient['uuid']}/prescriptions",headers=headers,json={"encounter_uuid":encounter["uuid"],"prescribed_at":"2026-03-01T10:00:00Z","drug_name":"Sumatriptan","dosage_instructions":"One tablet","dosage":"50 mg","route":"oral","quantity":"9","refills":2})
        order=client.post(f"/api/v1/patients/{patient['uuid']}/lab-orders",headers=headers,json={"encounter_uuid":encounter["uuid"],"ordered_at":"2026-03-01T10:30:00Z","code":"718-7","name":"Hemoglobin"}).json()
        client.post(f"/api/v1/lab-orders/{order['uuid']}/results",headers=headers,json={"observed_at":"2026-03-01T11:00:00Z","code":"718-7","name":"Hemoglobin","value":"13.4","unit":"g/dL","facility":"Clinical Lab","comments":"Verified"})
        client.post(f"/api/v1/patients/{patient['uuid']}/immunizations",headers=headers,json={"encounter_uuid":encounter["uuid"],"administered_at":"2026-03-01T12:00:00Z","cvx_code":"207","vaccine_name":"COVID-19","dose":"0.3","dose_unit":"mL"})
        run=client.post("/api/v1/reports/clinical_reports/runs",headers=headers,json={"date_from":"2026-01-01","date_to":"2026-12-31","facility_uuid":facility["uuid"],"patient_uuid":patient["uuid"],"gender":"female","race":"test-race","ethnicity":"test-ethnicity","diagnosis":"G43%","include_problems":True,"drug_name":"Suma%","lab_result":"13.%","clinical_type":"Procedure","immunization":"COVID","communication":"allow_email","sort_patient_name":True})
        assert run.status_code==201,run.text
        payload=run.json();assert payload["row_count"]==1 and payload["totals"]=={"rows":1,"patients":1}
        row=payload["rows"][0]
        assert {key:row[key] for key in ("patient_name","provider","facility","diagnosis_code","drug","result","procedure_code","procedure_standard_code","cvx_code","dose","dose_unit")}=={"patient_name":"Clinical Cohort","provider":"Report Doctor","facility":"Clinical Report Clinic","diagnosis_code":"G43.909","drug":"Sumatriptan","result":"13.4","procedure_code":"718-7","procedure_standard_code":None,"cvx_code":"207","dose":"0.3","dose_unit":"mL"}
        assert len(payload["checksum"])==64
        csv=client.get(f"/api/v1/report-runs/{payload['uuid']}/export.csv",headers=headers)
        assert csv.status_code==200 and "procedure_code" in csv.text.splitlines()[0]
        charge=client.post(f"/api/v1/patients/{patient['uuid']}/charges",headers=headers,json={"encounter_uuid":encounter["uuid"],"code_system":"CPT4","code":"99213","description":"Office visit","units":1,"unit_price":"125.00","billed_at":"2026-04-02T08:00:00Z"})
        assert charge.status_code==201,charge.text
        service=client.post("/api/v1/reports/clinical_reports/runs",headers=headers,json={"date_from":"2026-04-02","date_to":"2026-04-02","patient_uuid":patient["uuid"],"clinical_type":"Service Codes","service_code":"CPT4:99213"})
        assert service.status_code==201,service.text
        assert service.json()["rows"][0]["service_date"]=="2026-04-02T08:00:00"
        assert client.post("/api/v1/reports/clinical_reports/runs",headers=headers,json={"age_from":50,"age_to":20}).status_code==422


def test_report_execution_enforces_each_catalog_permission():
    with TestClient(app) as client:
        with SessionLocal() as db:
            db.add(User(email="report-denied@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["patients:demo:read"]));db.commit()
        token=client.post("/api/v1/auth/token",json={"email":"report-denied@example.com","password":"report-password"}).json()["access_token"]
        headers={"Authorization":f"Bearer {token}"}
        assert client.get("/api/v1/reports",headers=headers).status_code==200
        assert client.post("/api/v1/reports/patient_list/runs",headers=headers,json={}).status_code==403
        assert client.post("/api/v1/reports/inventory_list/runs",headers=headers,json={}).status_code==403
