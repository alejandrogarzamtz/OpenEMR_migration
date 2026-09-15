from datetime import date
from decimal import Decimal

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.main import app
from app.models import AmcTrackingEvent, Charge, ClinicalForm, ClinicalItem, Encounter, InventoryProduct, InventoryTransaction, LabOrder, Patient, QualityMeasureItem, QualityMeasureReport, Referral, ServiceCode, User
from app.security import password_hash


def admin_headers(client: TestClient):
    token=client.post("/api/v1/auth/token",json={"email":"admin@example.com","password":"change-me-now"}).json()["access_token"]
    return {"Authorization":f"Bearer {token}"}


def test_report_catalog_snapshots_filters_checksums_and_csv_export():
    with TestClient(app) as client:
        headers=admin_headers(client)
        catalog=client.get("/api/v1/reports",headers=headers)
        assert catalog.status_code==200 and len(catalog.json())==48
        assert sum(item["migrated"] for item in catalog.json())==45
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


def test_patient_list_creation_modes_filters_snapshots_and_csv():
    with TestClient(app) as client:
        headers=admin_headers(client)
        patient_response=client.post("/api/v1/patients",headers=headers,json={"first_name":"Cohort","last_name":"Builder","date_of_birth":"1985-06-01","sex":"female","race":"race-a","ethnicity":"ethnicity-a","email":"cohort-builder-report@example.com","allow_email":True})
        assert patient_response.status_code==201,patient_response.text
        patient=patient_response.json()
        encounter=client.post("/api/v1/encounters",headers=headers,json={"patient_uuid":patient["uuid"],"occurred_at":"2026-06-15T09:00:00Z","type":"AMB","chief_complaint":"Preventive visit"}).json()
        client.post(f"/api/v1/patients/{patient['uuid']}/clinical-items",headers=headers,json={"category":"allergy","title":"Penicillin","code":"Z88.0"})
        client.post(f"/api/v1/patients/{patient['uuid']}/prescriptions",headers=headers,json={"encounter_uuid":encounter["uuid"],"prescribed_at":"2026-06-15T10:00:00Z","drug_name":"Amoxicillin","dosage_instructions":"One daily","quantity":"10","refills":1})
        order=client.post(f"/api/v1/patients/{patient['uuid']}/lab-orders",headers=headers,json={"encounter_uuid":encounter["uuid"],"ordered_at":"2026-06-15T10:30:00Z","code":"718-7","name":"Hemoglobin","order_diagnosis":"Z00.00"}).json()
        client.post(f"/api/v1/lab-orders/{order['uuid']}/results",headers=headers,json={"observed_at":"2026-06-15T11:00:00Z","code":"718-7","name":"Hemoglobin","value":"13.7","unit":"g/dL","facility":"Community Lab"})
        with SessionLocal() as db:
            db_patient=db.scalar(select(Patient).where(Patient.uuid==patient["uuid"]));db_encounter=db.scalar(select(Encounter).where(Encounter.uuid==encounter["uuid"]))
            db_order=db.scalar(select(LabOrder).where(LabOrder.uuid==order["uuid"]));db_order.order_diagnosis="Z00.00"
            db.add(ClinicalForm(patient_id=db_patient.id,encounter_id=db_encounter.id,form_type="custom",title="Observation",source_formdir="observation",authored_at=db_encounter.occurred_at,content={"rows":[{"code":"8302-2","description":"Body height","ob_type":"numeric","ob_value":"170","ob_unit":"cm","observation":"Standing"}]}));db.commit()
        common={"date_from":"2026-01-01","date_to":"2026-12-31","patient_uuid":patient["uuid"]}
        allergies=client.post("/api/v1/reports/patient_list_creation/runs",headers=headers,json=common|{"patient_list_option":"allergs","procedure_diagnosis":"Z88%"})
        assert allergies.status_code==201,allergies.text
        assert allergies.json()["rows"][0]["allergy"]=="Penicillin" and allergies.json()["totals"]=={"rows":1,"patients":1,"option":"allergs"}
        prescriptions=client.post("/api/v1/reports/patient_list_creation/runs",headers=headers,json=common|{"patient_list_option":"prescripts","drug_name":"Amox%"})
        assert prescriptions.json()["rows"][0]["rx_drug"]=="Amoxicillin"
        observations=client.post("/api/v1/reports/patient_list_creation/runs",headers=headers,json=common|{"patient_list_option":"observs","observation_description":"Body%"})
        assert observations.json()["rows"][0]["obs_value"]=="170"
        results=client.post("/api/v1/reports/patient_list_creation/runs",headers=headers,json=common|{"patient_list_option":"results","procedure_diagnosis":"Z00%","patient_list_sort_order":"desc"})
        assert results.json()["rows"][0]["result_result"]=="13.7"
        csv=client.get(f"/api/v1/report-runs/{results.json()['uuid']}/export.csv",headers=headers)
        assert csv.status_code==200 and "result_document_id" in csv.text.splitlines()[0]


def test_ippf_cyp_report_combines_services_and_paid_drug_sales():
    with TestClient(app) as client:
        headers=admin_headers(client)
        patient=client.post("/api/v1/patients",headers=headers,json={"first_name":"CYP","last_name":"Fixture","date_of_birth":"1992-01-02","sex":"female"}).json()
        encounter=client.post("/api/v1/encounters",headers=headers,json={"patient_uuid":patient["uuid"],"occurred_at":"2026-07-01T09:00:00Z","type":"AMB"}).json()
        with SessionLocal() as db:
            db_patient=db.scalar(select(Patient).where(Patient.uuid==patient["uuid"]));db_encounter=db.scalar(select(Encounter).where(Encounter.uuid==encounter["uuid"]))
            service=ServiceCode(code_type_id=12,code="CYP-TEST",modifier="",description="Contraceptive service",cyp_factor=Decimal("2.5000"),active=True);product=InventoryProduct(name="CYP test product",cyp_factor=Decimal("0.2500"));db.add_all([service,product]);db.flush()
            db.add_all([Charge(patient_id=db_patient.id,encounter_id=db_encounter.id,code_system="MA",code="CYP-TEST",description="Contraceptive service",units=2,unit_price=Decimal("1.00"),active=True),InventoryTransaction(product_id=product.id,patient_id=db_patient.id,encounter_id=db_encounter.id,transaction_type="dispense",occurred_on=date(2026,7,1),quantity=4,fee=Decimal("10.00"))]);db.commit()
        details=client.post("/api/v1/reports/ippf_cyp_report/runs",headers=headers,json={"date_from":"2026-07-01","date_to":"2026-07-01"})
        assert details.status_code==201,details.text
        payload=details.json();assert payload["row_count"]==2 and payload["totals"]=={"quantity":6,"cyp_result":"6.00","items":2}
        assert {row["source"]:row["result"] for row in payload["rows"]}=={"service":"5.00","drug":"1.00"}
        summary=client.post("/api/v1/reports/ippf_cyp_report/runs",headers=headers,json={"date_from":"2026-07-01","date_to":"2026-07-01","include_details":False})
        assert summary.json()["columns"]==["item","quantity","cyp","result"] and summary.json()["row_count"]==2


def test_ippf_daily_counts_clients_visits_and_named_services_by_method():
    with TestClient(app) as client:
        headers=admin_headers(client)
        patient=client.post("/api/v1/patients",headers=headers,json={"first_name":"Daily","last_name":"Fixture","date_of_birth":"1994-03-02","sex":"female"}).json()
        encounter=client.post("/api/v1/encounters",headers=headers,json={"patient_uuid":patient["uuid"],"occurred_at":"2026-09-15T09:00:00Z","type":"AMB"}).json()
        with SessionLocal() as db:
            db_patient=db.scalar(select(Patient).where(Patient.uuid==patient["uuid"]));db_encounter=db.scalar(select(Encounter).where(Encounter.uuid==encounter["uuid"]))
            db_patient.legacy_payload={"regdate":"2026-09-15"};db_encounter.legacy_payload={"pc_catid":10}
            db.add(ClinicalItem(patient_id=db_patient.id,category="contraceptive",title="Injectable",code="inj|or",status="active",onset_date=date(2026,1,1)))
            db.add_all([
                Charge(patient_id=db_patient.id,encounter_id=db_encounter.id,code_system="MA",code="255004",description="Pap smear",units=1,unit_price=Decimal("0"),active=True),
                Charge(patient_id=db_patient.id,encounter_id=db_encounter.id,code_system="MA",code="19916",description="Counseling",units=1,unit_price=Decimal("0"),active=True),
            ]);db.commit()
        result=client.post("/api/v1/reports/ippf_daily/runs",headers=headers,json={"date_from":"2026-09-15"})
        assert result.status_code==201,result.text
        payload=result.json();injectable=next(row for row in payload["rows"] if row["method_code"]=="inj")
        assert payload["row_count"]==15
        assert {key:injectable[key] for key in ("new_clients","old_clients","total_clients","contra_clients","pap_smear","counseling_by_method")}=={"new_clients":1,"old_clients":0,"total_clients":1,"contra_clients":1,"pap_smear":1,"counseling_by_method":1}
        assert payload["totals"]["total_clients"]==1 and payload["totals"]["date"]=="2026-09-15"
        exported=client.get(f"/api/v1/report-runs/{payload['uuid']}/export.csv",headers=headers)
        assert exported.status_code==200 and exported.text.splitlines()[0].startswith("method_code,method,new_clients")


def test_ippf_statistics_preserves_families_dimensions_products_and_referrals():
    with TestClient(app) as client:
        headers=admin_headers(client)
        patient=client.post("/api/v1/patients",headers=headers,json={"first_name":"Statistics","last_name":"Fixture","date_of_birth":"2003-06-01","sex":"female","race":"community-a"}).json()
        encounter=client.post("/api/v1/encounters",headers=headers,json={"patient_uuid":patient["uuid"],"occurred_at":"2026-08-10T09:00:00Z","type":"AMB"}).json()
        with SessionLocal() as db:
            db_patient=db.scalar(select(Patient).where(Patient.uuid==patient["uuid"]));db_encounter=db.scalar(select(Encounter).where(Encounter.uuid==encounter["uuid"]));db_patient.legacy_payload={"regdate":"2026-08-01","contrastart":"2026-08-10","referral_source":"Community partner"}
            definition=ServiceCode(code_type_id=12,code="MA-STATS",modifier="",description="Injectable counseling",category_title="Family planning",related_codes="IPPF:111111;IPPF:2522211",active=True)
            ippf=ServiceCode(code_type_id=11,code="111111",modifier="",description="Injectable contraceptive service",active=True)
            product=InventoryProduct(name="Statistics contraceptive",cyp_factor=Decimal("0.2500"),legacy_payload={"related_code":"IPPF:112141"});db.add_all([definition,ippf,product]);db.flush()
            db.add_all([Charge(patient_id=db_patient.id,encounter_id=db_encounter.id,code_system="MA",code="MA-STATS",description="Injectable counseling",units=1,unit_price=Decimal("0"),active=True),InventoryTransaction(product_id=product.id,patient_id=db_patient.id,encounter_id=db_encounter.id,transaction_type="dispense",occurred_on=date(2026,8,10),quantity=3,fee=Decimal("0")),Referral(patient_id=db_patient.id,recipient_name="External clinic",referred_at=db_encounter.occurred_at,reason="Family planning",legacy_fields={"refer_external":"1","refer_related_code":"IPPF:111111"})]);db.commit()
        common={"date_from":"2026-08-01","date_to":"2026-08-31","ippf_report_type":"i","ippf_group_by":"6","ippf_columns":["total","sex","age2","race"]}
        services=client.post("/api/v1/reports/ippf_statistics/runs",headers=headers,json=common|{"ippf_content":"1"})
        assert services.status_code==201,services.text
        payload=services.json();row=next(item for item in payload["rows"] if item["group"]=="Injectables")
        assert row["total"]==1 and row["women"]==1 and row["age_0_24"]==1 and row["race:community-a"]==1
        acceptors=client.post("/api/v1/reports/ippf_statistics/runs",headers=headers,json=common|{"ippf_content":"3"})
        assert acceptors.json()["totals"]["total"]==1
        products=client.post("/api/v1/reports/ippf_statistics/runs",headers=headers,json=common|{"ippf_content":"5","ippf_columns":["total"]})
        assert products.json()["rows"]==[{"group":"Injectables","total":3}]
        ma=client.post("/api/v1/reports/ippf_statistics/runs",headers=headers,json={"date_from":"2026-08-01","date_to":"2026-08-31","ippf_report_type":"m","ippf_group_by":"102","ippf_content":"2"})
        assert ma.json()["rows"]==[{"group":"MA-STATS","description":"Injectable counseling","total":1}]
        referral=client.post("/api/v1/reports/ippf_statistics/runs",headers=headers,json={"date_from":"2026-08-01","date_to":"2026-08-31","ippf_report_type":"i","ippf_group_by":"10","ippf_content":"1"})
        assert referral.json()["rows"][0]["group"]=="111111"
        invalid=client.post("/api/v1/reports/ippf_statistics/runs",headers=headers,json={"ippf_report_type":"m","ippf_group_by":"3","ippf_content":"1"})
        assert invalid.status_code==422
        exported=client.get(f"/api/v1/report-runs/{payload['uuid']}/export.csv",headers=headers)
        assert exported.status_code==200 and "age_0_24" in exported.text.splitlines()[0]


def test_amc_tracking_lists_and_completes_referral_and_encounter_evidence():
    with TestClient(app) as client:
        headers=admin_headers(client)
        patient=client.post("/api/v1/patients",headers=headers,json={"first_name":"AMC","last_name":"Fixture","date_of_birth":"1980-01-01","sex":"female"}).json()
        encounter=client.post("/api/v1/encounters",headers=headers,json={"patient_uuid":patient["uuid"],"occurred_at":"2026-09-01T09:00:00Z","type":"AMB"}).json()
        with SessionLocal() as db:
            db_patient=db.scalar(select(Patient).where(Patient.uuid==patient["uuid"]));db_encounter=db.scalar(select(Encounter).where(Encounter.uuid==encounter["uuid"]));db_encounter.legacy_encounter_id=7201
            referral=Referral(legacy_transaction_id=7101,patient_id=db_patient.id,recipient_name="Care partner",referred_at=db_encounter.occurred_at,reason="Transition of care");db.add(referral);db.commit();db.refresh(referral);referral_uuid=referral.uuid
        referral_run=client.post("/api/v1/reports/amc_tracking/runs",headers=headers,json={"date_from":"2026-09-01","date_to":"2026-09-01","amc_rule":"send_sum_amc"})
        assert referral_run.status_code==201,referral_run.text
        payload=referral_run.json();row=next(item for item in payload["rows"] if item["source_uuid"]==referral_uuid);assert row["completed"] is False and row["electronically"] is False
        completed=client.patch(f"/api/v1/amc-tracking/send_sum_amc/{referral_uuid}",headers=headers,json={"completed":True,"electronically":True})
        assert completed.status_code==200 and completed.json()["electronically"] is True
        pending=client.post("/api/v1/reports/amc_tracking/runs",headers=headers,json={"date_from":"2026-09-01","date_to":"2026-09-01","amc_rule":"send_sum_amc"})
        assert all(item["source_uuid"]!=referral_uuid for item in pending.json()["rows"])
        history=client.post("/api/v1/reports/amc_tracking/runs",headers=headers,json={"date_from":"2026-09-01","date_to":"2026-09-01","amc_rule":"send_sum_amc","include_completed":True})
        historical=next(item for item in history.json()["rows"] if item["source_uuid"]==referral_uuid);assert historical["completed"] is True and historical["electronically"] is True
        encounter_run=client.post("/api/v1/reports/amc_tracking/runs",headers=headers,json={"date_from":"2026-09-01","date_to":"2026-09-01","amc_rule":"provide_sum_pat_amc"})
        encounter_row=next(item for item in encounter_run.json()["rows"] if item["source_uuid"]==encounter["uuid"]);assert encounter_row["legacy_source_id"]==7201
        with SessionLocal() as db:assert db.scalar(select(AmcTrackingEvent).where(AmcTrackingEvent.rule_id=="send_sum_elec_amc")).completed_at is not None


def test_amc_full_report_preserves_measure_math_and_patient_evidence():
    with TestClient(app) as client:
        headers=admin_headers(client)
        patient=client.post("/api/v1/patients",headers=headers,json={"first_name":"Quality","last_name":"Evidence","date_of_birth":"1978-04-03","sex":"female"}).json()
        with SessionLocal() as db:
            db_patient=db.scalar(select(Patient).where(Patient.uuid==patient["uuid"]))
            report=QualityMeasureReport(legacy_report_id=99001,report_type="mips",provider="group_calculation",data=[{"is_main":True,"id":"measure-a","pass_filter":10,"pass_target":6,"excluded":1,"percentage":"66.7","itemized_test_id":4},{"is_sub":True,"action_category":"communication","action_item":"summary","pass_target":5,"itemized_test_id":5}],legacy_fields={});db.add(report);db.flush()
            db.add_all([QualityMeasureItem(report_id=report.id,sequence=1,itemized_test_id=4,numerator_label="numerator",pass_status=1,patient_id=db_patient.id,legacy_patient_id=123,rule_id="measure-a",item_details={"numerator":[{"value":True}]}),QualityMeasureItem(report_id=report.id,sequence=2,itemized_test_id=4,numerator_label="",pass_status=0,patient_id=None,legacy_patient_id=999,rule_id="measure-a",item_details={"denominator":[{"value":True}]})]);db.commit();report_uuid=report.uuid
        detailed=client.post("/api/v1/reports/amc_full_report/runs",headers=headers,json={"quality_report_uuid":report_uuid})
        assert detailed.status_code==201,detailed.text
        payload=detailed.json();assert payload["row_count"]==2 and payload["totals"]["measures"]==2
        assert payload["rows"][0]["failed"]==3 and payload["rows"][0]["patient"]=="Quality Evidence" and payload["rows"][1]["legacy_patient_id"]==999
        summary=client.post("/api/v1/reports/amc_full_report/runs",headers=headers,json={"quality_report_uuid":report_uuid,"include_details":False})
        assert summary.json()["rows"][1]["failed"]==5
        assert client.post("/api/v1/reports/amc_full_report/runs",headers=headers,json={}).status_code==422


def test_report_execution_enforces_each_catalog_permission():
    with TestClient(app) as client:
        with SessionLocal() as db:
            db.add(User(email="report-denied@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["patients:demo:read"]));db.commit()
        token=client.post("/api/v1/auth/token",json={"email":"report-denied@example.com","password":"report-password"}).json()["access_token"]
        headers={"Authorization":f"Bearer {token}"}
        assert client.get("/api/v1/reports",headers=headers).status_code==200
        assert client.post("/api/v1/reports/patient_list/runs",headers=headers,json={}).status_code==403
        assert client.post("/api/v1/reports/inventory_list/runs",headers=headers,json={}).status_code==403
        with SessionLocal() as db:
            db.add(User(email="patient-list-med-only@example.com",password_hash=password_hash.hash("report-password"),role="viewer",permissions=["patients:med:read"]));db.commit()
        med_token=client.post("/api/v1/auth/token",json={"email":"patient-list-med-only@example.com","password":"report-password"}).json()["access_token"]
        med_headers={"Authorization":f"Bearer {med_token}"}
        assert client.post("/api/v1/reports/patient_list_creation/runs",headers=med_headers,json={"patient_list_option":"prescripts"}).status_code==403
