from datetime import date, datetime, timezone

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import BillingCodeType, ClinicalItem, Facility, Patient, ServiceCode, SyndromicSubmission, User, UserFacilityAccess
from app.security import password_hash


def headers_for(client,email,password):
    token=client.post("/api/v1/auth/token",json={"email":email,"password":password}).json()["access_token"]
    return {"Authorization":f"Bearer {token}"}


def test_non_reported_syndromic_filter_hl7_export_and_submission_lifecycle():
    with TestClient(app) as client:
        with SessionLocal() as db:
            facility=Facility(name="Public Health Clinic",npi="1234567890")
            reader=User(email="syndromic@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["patients:med:read"])
            patient=Patient(legacy_pid=9101,first_name="Public",last_name="Health",date_of_birth=date(1990,2,3),sex="Female",phone="555-0110",address_line_1="10 Main",city="Austin",state="TX",postal_code="78701",legacy_payload={"status":"married"})
            db.add_all([facility,reader,patient]);db.flush();db.add(UserFacilityAccess(user_id=reader.id,facility_id=facility.id))
            icd9=BillingCodeType(key="ICD9",legacy_type_id=2,sequence=1,diagnosis=True)
            db.add(icd9);db.flush()
            db.add_all([
                ServiceCode(legacy_code_id=101,code_type_id=2,code="487.1",modifier="",description="Influenza with respiratory manifestations",legacy_payload={"reportable":1}),
                ServiceCode(legacy_code_id=102,code_type_id=2,code="250.00",modifier="",description="Diabetes",legacy_payload={"reportable":0}),
            ]);db.flush();when=datetime(2039,6,5,10,30,tzinfo=timezone.utc)
            reportable=ClinicalItem(legacy_list_id=201,patient_id=patient.id,category="problem",title="Influenza syndrome",code_system="ICD9",code="487.1",recorded_at=when,onset_date=date(2039,6,1),legacy_payload={"diagnosis":"ICD9:487.1"})
            ignored=ClinicalItem(legacy_list_id=202,patient_id=patient.id,category="problem",title="Diabetes",code_system="ICD9",code="250.00",recorded_at=when)
            already=ClinicalItem(legacy_list_id=203,patient_id=patient.id,category="problem",title="Old influenza",code_system="ICD9",code="487.1",recorded_at=when)
            db.add_all([reportable,ignored,already]);db.flush();db.add(SyndromicSubmission(legacy_submission_id=301,clinical_item_id=already.id,submitted_at=when,filename="old.hl7"));db.commit();facility_uuid=facility.uuid;patient_uuid=patient.uuid
        headers=headers_for(client,"syndromic@example.com","report-password")
        response=client.post("/api/v1/reports/non_reported/runs",headers=headers,json={"date_from":"2039-06-05","date_to":"2039-06-05","facility_uuid":facility_uuid,"patient_uuid":patient_uuid,"reportable_code_ids":[101]})
        assert response.status_code==201,response.text
        payload=response.json();assert payload["row_count"]==1 and payload["totals"]=={"unreported_issues":1,"patients":1,"reportable_codes":1}
        assert payload["rows"][0]["diagnosis"]=="ICD9:487.1" and payload["rows"][0]["legacy_issue_id"]==201
        exported=client.get(f"/api/v1/report-runs/{payload['uuid']}/export.hl7",headers=headers)
        assert exported.status_code==200,exported.text
        assert all(segment in exported.text for segment in ("MSH|^~\\&|OPENRM|Public Health Clinic^1234567890^NPI","ADT^A01^ADT_A01","PID|1||9101^^^^MR","OBX|1|CWE|8661-1^^LN","DG1|1||4871^Influenza with respiratory manifestations^I9CDX"))
        assert exported.headers["x-report-checksum"]==payload["checksum"]
        assert client.get(f"/api/v1/report-runs/{payload['uuid']}/export.hl7",headers=headers).status_code==409
        refreshed=client.post("/api/v1/reports/non_reported/runs",headers=headers,json={"facility_uuid":facility_uuid})
        assert refreshed.status_code==201 and refreshed.json()["row_count"]==0


def test_syndromic_hl7_requires_sending_facility_npi_and_permission():
    with TestClient(app) as client:
        admin=headers_for(client,"admin@example.com","change-me-now")
        run=client.post("/api/v1/reports/non_reported/runs",headers=admin,json={})
        assert run.status_code==201
        assert client.get(f"/api/v1/report-runs/{run.json()['uuid']}/export.hl7",headers=admin).status_code==422
        with SessionLocal() as db:
            db.add(User(email="syndromic-denied@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["patients:demo:read"]));db.commit()
        denied=headers_for(client,"syndromic-denied@example.com","report-password")
        assert client.post("/api/v1/reports/non_reported/runs",headers=denied,json={}).status_code==403
