from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from .db import get_db
from .models import AuditEvent, ClinicalItem, Immunization, LabOrder, LabResult, Patient, Prescription, User, VitalSet
from .security import clinical_user

router = APIRouter(prefix="/fhir", tags=["FHIR R4"])


def bundle(resource_type: str, resources: list[dict]) -> dict:
    return {"resourceType": "Bundle", "type": "searchset", "total": len(resources), "entry": [{"fullUrl": f"urn:uuid:{item['id']}", "resource": item, "search": {"mode": "match"}} for item in resources]}


def patient_resource(patient: Patient) -> dict:
    resource = {"resourceType": "Patient", "id": patient.uuid, "identifier": [], "active": True, "name": [{"use": "official", "family": patient.last_name, "given": [patient.first_name]}], "gender": patient.sex.lower() if patient.sex.lower() in {"male", "female", "other", "unknown"} else "unknown", "birthDate": patient.date_of_birth.isoformat()}
    if patient.legacy_pid is not None: resource["identifier"].append({"system": "urn:openemr:patient:pid", "value": str(patient.legacy_pid)})
    if patient.email: resource["telecom"] = [{"system": "email", "value": patient.email}]
    if patient.phone: resource.setdefault("telecom", []).append({"system": "phone", "value": patient.phone})
    return resource


def patient_or_404(db: Session, patient_uuid: str) -> Patient:
    patient = db.scalar(select(Patient).where(Patient.uuid == patient_uuid))
    if not patient: raise HTTPException(status_code=404, detail={"resourceType": "OperationOutcome", "issue": [{"severity": "error", "code": "not-found"}]})
    return patient


def audit(db: Session, user: User, resource_type: str, patient_uuid: str):
    db.add(AuditEvent(actor_id=user.id, action="fhir-read", resource_type=resource_type, resource_id=patient_uuid)); db.commit()


@router.get("/metadata")
def metadata():
    return {"resourceType": "CapabilityStatement", "status": "active", "date": "2026-09-01", "kind": "instance", "fhirVersion": "4.0.1", "format": ["json"], "rest": [{"mode": "server", "security": {"cors": True, "service": [{"coding": [{"system": "http://terminology.hl7.org/CodeSystem/restful-security-service", "code": "OAuth"}]}]}, "resource": [{"type": "Patient", "interaction": [{"code": "read"}, {"code": "search-type"}]}, {"type": "Condition", "interaction": [{"code": "search-type"}]}, {"type": "AllergyIntolerance", "interaction": [{"code": "search-type"}]}, {"type": "MedicationStatement", "interaction": [{"code": "search-type"}]}, {"type": "Observation", "interaction": [{"code": "search-type"}]}, {"type": "Immunization", "interaction": [{"code": "search-type"}]}, {"type": "MedicationRequest", "interaction": [{"code": "search-type"}]}]}]}


@router.get("/Patient/{patient_uuid}")
def read_patient(patient_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_or_404(db, patient_uuid); audit(db, user, "Patient", patient.uuid); return patient_resource(patient)


@router.get("/Patient")
def search_patients(family: str | None = None, given: str | None = None, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    query = select(Patient)
    if family: query = query.where(Patient.last_name.ilike(f"%{family}%"))
    if given: query = query.where(Patient.first_name.ilike(f"%{given}%"))
    patients = list(db.scalars(query.limit(100))); db.add(AuditEvent(actor_id=user.id, action="fhir-search", resource_type="Patient")); db.commit(); return bundle("Patient", [patient_resource(x) for x in patients])


def clinical_resources(db: Session, patient: Patient, category: str) -> list[dict]:
    items = list(db.scalars(select(ClinicalItem).where(ClinicalItem.patient_id == patient.id, ClinicalItem.category == category)))
    resources=[]
    for item in items:
        coding=[{"system": item.code_system, "code": item.code, "display": item.title}] if item.code else []
        if category == "problem": resources.append({"resourceType":"Condition","id":item.uuid,"clinicalStatus":{"coding":[{"system":"http://terminology.hl7.org/CodeSystem/condition-clinical","code":"active" if item.status=="active" else "resolved"}]},"code":{"coding":coding,"text":item.title},"subject":{"reference":f"Patient/{patient.uuid}"},**({"onsetDateTime":item.onset_date.isoformat()} if item.onset_date else {})})
        elif category == "allergy": resources.append({"resourceType":"AllergyIntolerance","id":item.uuid,"clinicalStatus":{"coding":[{"system":"http://terminology.hl7.org/CodeSystem/allergyintolerance-clinical","code":"active" if item.status=="active" else "inactive"}]},"code":{"coding":coding,"text":item.title},"patient":{"reference":f"Patient/{patient.uuid}"},**({"reaction":[{"manifestation":[{"text":item.reaction}],"severity":item.severity}]} if item.reaction else {})})
        else: resources.append({"resourceType":"MedicationStatement","id":item.uuid,"status":"active" if item.status=="active" else "stopped","medicationCodeableConcept":{"coding":coding,"text":item.title},"subject":{"reference":f"Patient/{patient.uuid}"},**({"dosage":[{"text":item.dosage}]} if item.dosage else {})})
    return resources


@router.get("/Condition")
def conditions(patient: str = Query(), db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    item=patient_or_404(db,patient); resources=clinical_resources(db,item,"problem"); audit(db,user,"Condition",item.uuid); return bundle("Condition",resources)


@router.get("/AllergyIntolerance")
def allergies(patient: str = Query(), db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    item=patient_or_404(db,patient); resources=clinical_resources(db,item,"allergy"); audit(db,user,"AllergyIntolerance",item.uuid); return bundle("AllergyIntolerance",resources)


@router.get("/MedicationStatement")
def medications(patient: str = Query(), db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    item=patient_or_404(db,patient); resources=clinical_resources(db,item,"medication"); audit(db,user,"MedicationStatement",item.uuid); return bundle("MedicationStatement",resources)


@router.get("/Observation")
def observations(patient: str = Query(), db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    item=patient_or_404(db,patient); rows=db.execute(select(LabResult).join(LabOrder).where(LabOrder.patient_id==item.id).order_by(LabResult.observed_at.desc())).scalars().all(); resources=[]
    for result in rows:
        value={"valueQuantity":{"value":float(result.value),"unit":result.unit}} if result.value.replace(".","",1).isdigit() else {"valueString":result.value}
        resources.append({"resourceType":"Observation","id":result.uuid,"status":result.status,"category":[{"coding":[{"system":"http://terminology.hl7.org/CodeSystem/observation-category","code":"laboratory"}]}],"code":{"coding":[{"system":"http://loinc.org","code":result.code,"display":result.name}],"text":result.name},"subject":{"reference":f"Patient/{item.uuid}"},"effectiveDateTime":result.observed_at.isoformat(),**value,**({"referenceRange":[{"text":result.reference_range}]} if result.reference_range else {})})
    vitals=db.scalars(select(VitalSet).where(VitalSet.patient_id==item.id)).all()
    vital_codes=(("systolic","8480-6","Systolic blood pressure","mm[Hg]"),("diastolic","8462-4","Diastolic blood pressure","mm[Hg]"),("weight_kg","29463-7","Body weight","kg"),("height_cm","8302-2","Body height","cm"),("temperature_c","8310-5","Body temperature","Cel"),("heart_rate","8867-4","Heart rate","/min"),("respiratory_rate","9279-1","Respiratory rate","/min"),("oxygen_saturation","2708-6","Oxygen saturation","%"),("bmi","39156-5","Body mass index","kg/m2"))
    for vital in vitals:
        for field,code,name,unit in vital_codes:
            value=getattr(vital,field)
            if value is not None: resources.append({"resourceType":"Observation","id":f"{vital.uuid}-{field}","status":"final","category":[{"coding":[{"system":"http://terminology.hl7.org/CodeSystem/observation-category","code":"vital-signs"}]}],"code":{"coding":[{"system":"http://loinc.org","code":code,"display":name}]},"subject":{"reference":f"Patient/{item.uuid}"},"effectiveDateTime":vital.observed_at.isoformat(),"valueQuantity":{"value":float(value),"unit":unit}})
    audit(db,user,"Observation",item.uuid); return bundle("Observation",resources)


@router.get("/Immunization")
def fhir_immunizations(patient: str = Query(), db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    item=patient_or_404(db,patient); rows=db.scalars(select(Immunization).where(Immunization.patient_id==item.id)).all(); resources=[{"resourceType":"Immunization","id":x.uuid,"status":x.status,"vaccineCode":{"coding":[{"system":"http://hl7.org/fhir/sid/cvx","code":x.cvx_code,"display":x.vaccine_name}]},"patient":{"reference":f"Patient/{item.uuid}"},"occurrenceDateTime":x.administered_at.isoformat(),**({"lotNumber":x.lot_number} if x.lot_number else {})} for x in rows]; audit(db,user,"Immunization",item.uuid); return bundle("Immunization",resources)


@router.get("/MedicationRequest")
def medication_requests(patient: str = Query(), db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    item=patient_or_404(db,patient); rows=db.scalars(select(Prescription).where(Prescription.patient_id==item.id)).all(); resources=[{"resourceType":"MedicationRequest","id":x.uuid,"status":x.status,"intent":"order","medicationCodeableConcept":{"coding":[{"system":"http://www.nlm.nih.gov/research/umls/rxnorm","code":x.rxnorm_code,"display":x.drug_name}] if x.rxnorm_code else [],"text":x.drug_name},"subject":{"reference":f"Patient/{item.uuid}"},"authoredOn":x.prescribed_at.isoformat(),"dosageInstruction":[{"text":x.dosage_instructions}],"dispenseRequest":{"numberOfRepeatsAllowed":x.refills,**({"quantity":{"value":float(x.quantity)}} if x.quantity and x.quantity.replace(".","",1).isdigit() else {})},"substitution":{"allowedBoolean":x.substitutions_allowed}} for x in rows]; audit(db,user,"MedicationRequest",item.uuid); return bundle("MedicationRequest",resources)
