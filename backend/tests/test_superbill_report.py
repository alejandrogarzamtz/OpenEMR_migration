from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.models import Charge, ClinicalForm, Coverage, Encounter, Facility, Patient, Payer, Practitioner, ReceivableActivity, User, UserFacilityAccess
from app.security import password_hash


def headers_for(client,email,password):
    token=client.post("/api/v1/auth/token",json={"email":email,"password":password}).json()["access_token"]
    return {"Authorization":f"Bearer {token}"}


def test_superbill_preserves_demographics_insurance_charges_copay_provider_fallback_and_scope():
    with TestClient(app) as client:
        with SessionLocal() as db:
            north=Facility(name="Superbill North",street="1 Clinic Way",city="Austin",state="TX",postal_code="78701",billing_location=True)
            south=Facility(name="Superbill South",billing_location=True)
            reader=User(email="superbill@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["encounters:coding_a:read"])
            patient=Patient(legacy_pid=8101,first_name="Ada",middle_name="M",last_name="Lovelace",date_of_birth=date(1815,12,10),sex="female",legacy_payload={"fname":"Ada","lname":"Lovelace","DOB":"1815-12-10","ss":"111-22-3333","hipaa_mail":"YES"})
            remote=Patient(legacy_pid=8102,first_name="Remote",last_name="Patient",date_of_birth=date(1980,1,1),sex="unknown")
            payer=Payer(legacy_payer_id=99,name="Example Health")
            practitioner=Practitioner(legacy_user_id=77,first_name="Grace",last_name="Hopper")
            db.add_all([north,south,reader,patient,remote,payer,practitioner]);db.flush();db.add(UserFacilityAccess(user_id=reader.id,facility_id=north.id))
            coverage_payload={"subscriber_fname":"Ada","subscriber_mname":"M","subscriber_lname":"Lovelace","subscriber_DOB":"1815-12-10","subscriber_phone":"555-0100","subscriber_employer":"Analytical Engines"}
            db.add_all([
                Coverage(legacy_insurance_id=5001,patient_id=patient.id,payer_id=payer.id,priority="primary",plan_name="Gold",policy_number="P-1",subscriber_name="Ada M Lovelace",starts_on=date(2038,1,1),legacy_payload=coverage_payload|{"policy_number":"P-1","plan_name":"Gold"}),
                Coverage(legacy_insurance_id=5002,patient_id=patient.id,payer_id=payer.id,priority="secondary",policy_number="S-1",subscriber_name="Ada Lovelace",starts_on=date(2038,1,1),legacy_payload={"policy_number":"S-1","subscriber_fname":"Ada","subscriber_lname":"Lovelace"}),
            ]);db.flush()
            when=datetime(2038,4,15,9,30,tzinfo=timezone.utc)
            encounter=Encounter(legacy_encounter_id=6101,patient_id=patient.id,occurred_at=when,facility_id=north.id,legacy_provider_id=77,provider_name="Grace Hopper")
            empty_encounter=Encounter(legacy_encounter_id=6102,patient_id=patient.id,occurred_at=when.replace(hour=11),facility_id=north.id,legacy_provider_id=77,provider_name="Grace Hopper")
            remote_encounter=Encounter(legacy_encounter_id=6103,patient_id=remote.id,occurred_at=when,facility_id=south.id)
            db.add_all([encounter,empty_encounter,remote_encounter]);db.flush()
            db.add_all([
                ClinicalForm(legacy_form_key="forms:7101",patient_id=patient.id,encounter_id=encounter.id,form_type="custom",title="New Patient Encounter",content={},authored_at=when),
                ClinicalForm(legacy_form_key="forms:7102",patient_id=patient.id,encounter_id=empty_encounter.id,form_type="custom",title="New Patient Encounter",content={},authored_at=when.replace(hour=11)),
                ClinicalForm(legacy_form_key="forms:7103",patient_id=patient.id,encounter_id=encounter.id,form_type="soap",title="SOAP",content={},authored_at=when),
                ClinicalForm(legacy_form_key="forms:7104",patient_id=remote.id,encounter_id=remote_encounter.id,form_type="custom",title="New Patient Encounter",content={},authored_at=when),
            ]);db.flush()
            db.add_all([
                Charge(legacy_billing_id=7201,patient_id=patient.id,encounter_id=encounter.id,code_system="CPT4",code="99213",modifier="25",description="Office visit",unit_price=Decimal("125.00"),units=2,billed_at=when,active=True,legacy_payload={"provider_id":0}),
                Charge(legacy_billing_id=7202,patient_id=patient.id,encounter_id=encounter.id,code_system="CPT4",code="99999",description="Deleted source charge",unit_price=Decimal("900.00"),units=1,billed_at=when,active=False,legacy_payload={"provider_id":77}),
                ReceivableActivity(patient_id=patient.id,encounter_id=encounter.id,legacy_patient_id=8101,legacy_encounter_id=6101,legacy_sequence=1,payer_type=0,account_code="PCP",pay_amount=Decimal("20.00"),adjustment_amount=0,posted_at=when),
                ReceivableActivity(patient_id=patient.id,encounter_id=encounter.id,legacy_patient_id=8101,legacy_encounter_id=6101,legacy_sequence=2,payer_type=0,account_code="PCP",pay_amount=Decimal("99.00"),adjustment_amount=0,posted_at=when,deleted_at=when),
            ]);db.commit();patient_uuid=patient.uuid
        headers=headers_for(client,"superbill@example.com","report-password")
        missing=client.post("/api/v1/reports/custom_report_range/runs",headers=headers,json={})
        assert missing.status_code==422
        response=client.post("/api/v1/reports/custom_report_range/runs",headers=headers,json={"date_from":"2038-04-15","date_to":"2038-04-15","patient_uuid":patient_uuid})
        assert response.status_code==201,response.text
        payload=response.json();assert payload["row_count"]==2
        assert payload["totals"]=={"superbills":2,"charge_lines":1,"charges":"125.00","copay_paid":"20.00","subtotals":"145.00"}
        billed=next(row for row in payload["rows"] if row["code"]=="99213")
        assert {key:billed[key] for key in ("patient_fname","patient_ss","primary_provider_name","primary_subscriber_employer","secondary_policy_number","provider","fee","encounter_subtotal","copay_paid","encounter_total")}=={"patient_fname":"Ada","patient_ss":"111-22-3333","primary_provider_name":"Example Health","primary_subscriber_employer":"Analytical Engines","secondary_policy_number":"S-1","provider":"Grace Hopper","fee":"125.00","encounter_subtotal":"145.00","copay_paid":"20.00","encounter_total":"125.00"}
        assert next(row for row in payload["rows"] if row["legacy_encounter_id"]==6102)["code"] is None
        exported=client.get(f"/api/v1/report-runs/{payload['uuid']}/export.csv",headers=headers)
        assert exported.status_code==200 and "primary_subscriber_employer" in exported.text.splitlines()[0]


def test_superbill_requires_coding_permission():
    with TestClient(app) as client:
        with SessionLocal() as db:
            db.add(User(email="superbill-denied@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["patients:med:read"]));db.commit()
        headers=headers_for(client,"superbill-denied@example.com","report-password")
        assert client.post("/api/v1/reports/custom_report_range/runs",headers=headers,json={"date_from":"2038-01-01","date_to":"2038-01-02"}).status_code==403
