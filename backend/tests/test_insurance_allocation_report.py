from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Appointment, Charge, Coverage, Encounter, Facility, Patient, Payer, User, UserFacilityAccess
from app.security import password_hash


def headers_for(client: TestClient,email: str,password: str) -> dict[str,str]:
    response=client.post("/api/v1/auth/token",json={"email":email,"password":password})
    assert response.status_code==200
    return {"Authorization":f"Bearer {response.json()['access_token']}"}


def test_insurance_distribution_matches_visits_unique_patients_charges_and_scope():
    with TestClient(app) as client:
        with SessionLocal() as db:
            north=Facility(legacy_facility_id=930001,name="Insurance North")
            south=Facility(legacy_facility_id=930002,name="Insurance South")
            insured=Patient(legacy_pid=930001,first_name="Primary",last_name="Insured",date_of_birth=date(1980,1,1),sex="unknown")
            self_pay=Patient(legacy_pid=930002,first_name="Self",last_name="Pay",date_of_birth=date(1981,1,1),sex="unknown")
            remote=Patient(legacy_pid=930003,first_name="Remote",last_name="Patient",date_of_birth=date(1982,1,1),sex="unknown")
            payer=Payer(legacy_payer_id=930001,name="Acme Health",active=True)
            future=Payer(legacy_payer_id=930002,name="Future Health",active=True)
            reader=User(email="insurance-report@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["acct:rep_a:read"])
            db.add_all([north,south,insured,self_pay,remote,payer,future,reader]);db.flush()
            db.add_all([Coverage(patient_id=insured.id,payer_id=payer.id,priority="primary",policy_number="ACME-1",subscriber_name="Primary Insured",starts_on=date(2033,1,1)),Coverage(patient_id=insured.id,payer_id=future.id,priority="primary",policy_number="FUTURE-1",subscriber_name="Primary Insured",starts_on=date(2034,1,1)),UserFacilityAccess(user_id=reader.id,facility_id=north.id)]);db.flush()
            when=datetime(2033,6,5,10,0,tzinfo=timezone.utc)
            appointments=[]
            for index,(patient,facility) in enumerate(((insured,north),(insured,north),(self_pay,north),(remote,south))):
                appointment=Appointment(patient_id=patient.id,facility_id=facility.id,legacy_facility_id=facility.legacy_facility_id,starts_at=when+timedelta(hours=index),ends_at=when+timedelta(hours=index,minutes=30),status="fulfilled")
                db.add(appointment);db.flush();appointments.append(appointment)
            encounters=[]
            for appointment in appointments:
                encounter=Encounter(patient_id=appointment.patient_id,appointment_id=appointment.id,occurred_at=appointment.starts_at,status="closed")
                db.add(encounter);db.flush();encounters.append(encounter)
            for encounter,amount,units in ((encounters[0],"100.00",1),(encounters[1],"25.00",2),(encounters[2],"50.00",1),(encounters[3],"80.00",1)):
                db.add(Charge(patient_id=encounter.patient_id,encounter_id=encounter.id,code_system="CPT",code="99213",description="Visit",units=units,unit_price=Decimal(amount)))
            db.add(Charge(patient_id=insured.id,encounter_id=encounters[0].id,code_system="COPAY",code="COPAY",description="Copay",units=1,unit_price=Decimal("10.00")))
            db.commit();north_uuid=north.uuid

        scoped=headers_for(client,"insurance-report@example.com","report-password")
        response=client.post("/api/v1/reports/insurance_allocation_report/runs",headers=scoped,json={"date_from":"2033-06-05","date_to":"2033-06-05"})
        assert response.status_code==201
        payload=response.json();rows={row["insurance"]:row for row in payload["rows"]}
        assert payload["columns"]==["insurance","charges","visits","patients","patient_percent"]
        assert rows["Acme Health"]=={"insurance":"Acme Health","charges":"150.00","visits":2,"patients":1,"patient_percent":"50.0"}
        assert rows["-- No Insurance --"]=={"insurance":"-- No Insurance --","charges":"50.00","visits":1,"patients":1,"patient_percent":"50.0"}
        assert payload["totals"]=={"charges":"200.00","visits":3,"patients":2}
        exported=client.get(f"/api/v1/report-runs/{payload['uuid']}/export.csv",headers=scoped)
        assert exported.status_code==200 and exported.text.splitlines()[0]=="insurance,charges,visits,patients,patient_percent"

        admin=headers_for(client,"admin@example.com","change-me-now")
        all_rows=client.post("/api/v1/reports/insurance_allocation_report/runs",headers=admin,json={"date_from":"2033-06-05","date_to":"2033-06-05"})
        assert all_rows.status_code==201 and all_rows.json()["totals"]=={"charges":"280.00","visits":4,"patients":3}
        selected=client.post("/api/v1/reports/insurance_allocation_report/runs",headers=admin,json={"date_from":"2033-06-05","date_to":"2033-06-05","facility_uuid":north_uuid})
        assert selected.status_code==201 and selected.json()["totals"]=={"charges":"200.00","visits":3,"patients":2}


def test_insurance_distribution_requires_financial_report_permission():
    with TestClient(app) as client:
        with SessionLocal() as db:
            db.add(User(email="insurance-denied@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["patients:med:read"]));db.commit()
        headers=headers_for(client,"insurance-denied@example.com","report-password")
        assert client.post("/api/v1/reports/insurance_allocation_report/runs",headers=headers,json={}).status_code==403
