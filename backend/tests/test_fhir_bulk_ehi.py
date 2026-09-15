from io import BytesIO
import json
from datetime import date, datetime, timezone
from hashlib import sha256
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from fastapi.testclient import TestClient

from app.main import app
from app.db import SessionLocal
from app.models import Document, ExternalProcedure, InventoryProduct, InventoryTransaction, LabOrder, Patient, ReferenceOption
from sqlalchemy import select


def staff(client):
    token=client.post("/api/v1/auth/token",json={"email":"admin@example.com","password":"change-me-now"}).json()["access_token"]
    return {"Authorization":f"Bearer {token}"}


def test_complete_legacy_fhir_contract_is_registered():
    expected='''GET AllergyIntolerance
GET AllergyIntolerance/:uuid
GET Appointment
GET Appointment/:uuid
GET CarePlan
GET CarePlan/:uuid
GET CareTeam
GET CareTeam/:uuid
GET Condition
GET Condition/:uuid
GET Coverage
GET Coverage/:uuid
GET Device
GET Device/:uuid
GET DiagnosticReport
GET DiagnosticReport/:uuid
GET DocumentReference
POST DocumentReference/$docref
GET DocumentReference/:uuid
GET Binary/:id
GET Encounter
GET Encounter/:uuid
GET Goal
GET Goal/:uuid
GET Group
GET Group/:uuid
GET Group/:id/$export
GET Immunization
GET Immunization/:uuid
GET Location
GET Location/:uuid
GET Media
GET Media/:uuid
GET Medication
GET Medication/:uuid
GET MedicationDispense
GET MedicationDispense/:uuid
GET MedicationRequest
GET MedicationRequest/:uuid
GET Observation
GET Observation/:uuid
GET Organization
GET Organization/:uuid
GET Specimen
GET Specimen/:uuid
POST Organization
PUT Organization/:uuid
POST Patient
PUT Patient/:uuid
GET Patient
GET Patient/$export
GET Patient/:uuid
GET Person
GET Person/:uuid
GET Practitioner
GET Practitioner/:uuid
POST Practitioner
PUT Practitioner/:uuid
GET PractitionerRole
GET PractitionerRole/:uuid
GET Procedure
GET RelatedPerson
GET RelatedPerson/:uuid
GET ServiceRequest
GET ServiceRequest/:uuid
GET Procedure/:uuid
GET Provenance/:uuid
GET Provenance
GET Questionnaire
GET QuestionnaireResponse
GET QuestionnaireResponse/:uuid
GET ValueSet
GET ValueSet/:uuid
GET metadata
GET .well-known/smart-configuration
GET OperationDefinition
GET OperationDefinition/:operation
GET $export
GET $bulkdata-status
DELETE $bulkdata-status'''.splitlines()
    actual={(method,route.path.removeprefix("/fhir/")) for route in app.routes for method in getattr(route,"methods",set())}
    for contract in expected:
        method,path=contract.split(" ",1);parts=path.split("/");normalized=[]
        for part in parts:normalized.append("{}" if part.startswith(":") else part)
        assert any(m==method and len(candidate.split("/"))==len(normalized) and all(want=="{}" and got.startswith("{") or want==got for want,got in zip(normalized,candidate.split("/"))) for m,candidate in actual),contract
    assert len(expected)==80


def test_fhir_writes_docref_resources_and_bulk_export():
    with TestClient(app) as client:
        headers=staff(client)
        patient=client.post("/fhir/Patient",headers=headers,json={"resourceType":"Patient","name":[{"family":"Export","given":["FHIR"]}],"gender":"unknown","birthDate":"1980-01-02","telecom":[{"system":"email","value":"fhir-export@example.com"}]})
        assert patient.status_code==201,patient.text
        patient_id=patient.json()["id"]
        organization=client.post("/fhir/Organization",headers=headers,json={"resourceType":"Organization","name":"FHIR Clinic","active":True})
        practitioner=client.post("/fhir/Practitioner",headers=headers,json={"resourceType":"Practitioner","name":[{"family":"FHIR","given":["Doctor"]}]})
        assert organization.status_code==201 and practitioner.status_code==201
        assert client.put(f"/fhir/Patient/{patient_id}",headers=headers,json={"resourceType":"Patient","name":[{"family":"Exported","given":["FHIR"]}],"gender":"unknown","birthDate":"1980-01-02"}).json()["name"][0]["family"]=="Exported"
        assert client.get("/fhir/Group",headers=headers).json()["entry"][0]["resource"]["quantity"]>=1
        assert client.get("/fhir/OperationDefinition/$export",headers=headers).json()["code"]=="export"
        empty_docref=client.post("/fhir/DocumentReference/$docref",headers=headers,json={"resourceType":"Parameters","parameter":[{"name":"patient","valueId":patient_id}]})
        assert empty_docref.status_code==200 and empty_docref.json()["total"]==0

        started=client.get(f"/fhir/Patient/$export?patient=Patient/{patient_id}&_type=Patient,Condition",headers=headers)
        assert started.status_code==202 and "$bulkdata-status" in started.headers["content-location"]
        status=client.get(started.headers["content-location"],headers=headers)
        assert status.status_code==200 and {x["type"] for x in status.json()["output"]}=={"Patient","Condition"}
        patient_file=next(x["url"] for x in status.json()["output"] if x["type"]=="Patient")
        ndjson=client.get(patient_file,headers=headers)
        assert ndjson.status_code==200 and json.loads(ndjson.text)["id"]==patient_id


def test_ccda_and_ehi_exports_are_parseable_and_patient_scoped():
    with TestClient(app) as client:
        headers=staff(client)
        patient=client.post("/api/v1/patients",headers=headers,json={"first_name":"EHI","last_name":"Patient","date_of_birth":"1970-04-05","sex":"female"}).json()
        other=client.post("/api/v1/patients",headers=headers,json={"first_name":"Private","last_name":"Other","date_of_birth":"1971-05-06","sex":"male"}).json()
        ccda=client.get(f"/api/v1/patients/{patient['uuid']}/ccda",headers=headers)
        root=ET.fromstring(ccda.content)
        assert ccda.status_code==200 and root.tag.endswith("ClinicalDocument") and b"EHI" in ccda.content
        exported=client.get(f"/api/v1/patients/{patient['uuid']}/ehi-export",headers=headers)
        with ZipFile(BytesIO(exported.content)) as archive:
            assert set(archive.namelist())=={"ccda.xml","designated-record-set.json","manifest.json"}
            record=json.loads(archive.read("designated-record-set.json"));manifest=json.loads(archive.read("manifest.json"))
        assert record["patients"][0]["uuid"]==patient["uuid"]
        assert other["uuid"] not in json.dumps(record)
        assert manifest["patient"]==patient["uuid"] and len(manifest["files"])==2


def test_remaining_fhir_resource_mappings_are_resolvable():
    with TestClient(app) as client:
        headers=staff(client)
        patient=client.post("/api/v1/patients",headers=headers,json={"first_name":"Resource","last_name":"Coverage","date_of_birth":"1988-08-08","sex":"unknown"}).json()
        with SessionLocal() as db:
            owner=db.scalar(select(Patient).where(Patient.uuid==patient["uuid"]));product=InventoryProduct(name="FHIR Device Drug",ndc_number="0001",consumable=False,unit="tablet");db.add(product);db.flush()
            transaction=InventoryTransaction(product_id=product.id,patient_id=owner.id,transaction_type="dispense",occurred_on=date(2026,9,15),quantity=-2)
            procedure=ExternalProcedure(patient_id=owner.id,occurred_on=date(2026,9,14),code_system="CPT",code="99213",code_text="Office visit")
            order=LabOrder(patient_id=owner.id,ordered_at=datetime(2026,9,15,tzinfo=timezone.utc),code="24323-8",name="Panel",specimen_type="blood",specimen_location="arm",specimen_volume="5 mL")
            content=b"image";document=Document(patient_id=owner.id,name="scan.png",mime_type="image/png",content=content,sha256=sha256(content).hexdigest())
            value=ReferenceOption(list_id="fhir-test-values",option_id="one",title="One");db.add_all([transaction,procedure,order,document,value]);db.commit();ids={"product":product.uuid,"transaction":transaction.uuid,"procedure":procedure.uuid,"order":order.uuid,"document":document.uuid}
        checks=(("Medication",ids["product"]),("Device",ids["product"]),("MedicationDispense",ids["transaction"]),("Procedure",ids["procedure"]),("Specimen",ids["order"]),("Media",ids["document"]),("ValueSet","fhir-test-values"))
        for resource,identifier in checks:
            response=client.get(f"/fhir/{resource}/{identifier}",headers=headers);assert response.status_code==200,(resource,response.text);assert response.json()["resourceType"]==resource
        for resource in ("MedicationDispense","Procedure","Specimen","Media"):
            assert client.get(f"/fhir/{resource}?patient={patient['uuid']}",headers=headers).json()["total"]==1
        provenance=client.get(f"/fhir/Provenance?target=Patient/{patient['uuid']}",headers=headers)
        assert provenance.status_code==200 and provenance.json()["resourceType"]=="Bundle"
        role=client.get("/fhir/PractitionerRole",headers=headers)
        assert role.status_code==200 and role.json()["resourceType"]=="Bundle"
