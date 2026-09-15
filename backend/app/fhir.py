from base64 import b64encode
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import or_, select
from sqlalchemy.orm import Session
from .config import settings
from .db import get_db
from .models import Appointment, AuditEvent, CarePlan, CarePlanOutcome, CareTeam, CareTeamMember, ClinicalItem, Coverage, Document, Encounter, Facility, Immunization, LabOrder, LabResult, Patient, PatientRelatedPerson, Payer, Practitioner, Prescription, QuestionnaireDefinition, QuestionnaireResponse, User, VitalSet
from .security import appointment_user, clinical_user, patient_demographics_user
from .services.access import facility_scope, require_facility_access
from .services.patients import patient_by_uuid

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
    try: return patient_by_uuid(db, patient_uuid)
    except HTTPException as exc:
        if exc.status_code == 404: raise HTTPException(status_code=404, detail={"resourceType": "OperationOutcome", "issue": [{"severity": "error", "code": "not-found"}]}) from exc
        raise


def audit(db: Session, user: User, resource_type: str, resource_id: str | None = None, *, search: bool = False):
    db.add(AuditEvent(actor_id=user.id, action="fhir-search" if search else "fhir-read", resource_type=resource_type, resource_id=resource_id)); db.commit()


@router.get("/metadata")
def metadata():
    read_search=[{"code":"read"},{"code":"search-type"}]
    patient_resources=[{"type":name,"interaction":read_search,"searchParam":[{"name":"patient","type":"reference"}]} for name in ("Condition","AllergyIntolerance","MedicationStatement","Observation","Immunization","MedicationRequest")]
    patient_resources.extend([{"type":"Coverage","interaction":read_search,"searchParam":[{"name":"patient","type":"reference"},{"name":"status","type":"token"}]},{"type":"DocumentReference","interaction":read_search,"searchParam":[{"name":"patient","type":"reference"},{"name":"type","type":"token"},{"name":"date","type":"date"}]},{"type":"Binary","interaction":[{"code":"read"}]}])
    patient_resources.extend([{"type":"ServiceRequest","interaction":read_search,"searchParam":[{"name":"patient","type":"reference"},{"name":"status","type":"token"},{"name":"code","type":"token"},{"name":"authored","type":"date"}]},{"type":"DiagnosticReport","interaction":read_search,"searchParam":[{"name":"patient","type":"reference"},{"name":"status","type":"token"},{"name":"code","type":"token"},{"name":"date","type":"date"}]}])
    patient_resources.extend([{"type":"Questionnaire","interaction":read_search,"searchParam":[{"name":"code","type":"token"},{"name":"title","type":"string"},{"name":"status","type":"token"}]},{"type":"QuestionnaireResponse","interaction":read_search,"searchParam":[{"name":"patient","type":"reference"},{"name":"questionnaire","type":"reference"},{"name":"authored","type":"date"}]}])
    patient_resources.append({"type":"RelatedPerson","interaction":read_search,"searchParam":[{"name":"patient","type":"reference"},{"name":"name","type":"string"},{"name":"relationship","type":"token"},{"name":"active","type":"token"}]})
    status_resources=[{"type":name,"interaction":read_search,"searchParam":[{"name":"patient","type":"reference"},{"name":"status","type":"token"}]} for name in ("Appointment","Encounter","CarePlan","Goal","CareTeam")]
    directory_resources=[{"type":name,"interaction":read_search,"searchParam":[{"name":"name","type":"string"},{"name":"active","type":"token"}]} for name in ("Organization","Location")]+[{"type":"Practitioner","interaction":read_search,"searchParam":[{"name":"family","type":"string"},{"name":"given","type":"string"},{"name":"identifier","type":"token"},{"name":"active","type":"token"}]},{"type":"Person","interaction":read_search,"searchParam":[{"name":"name","type":"string"},{"name":"identifier","type":"token"},{"name":"active","type":"token"}]}]
    resources=[{"type":"Patient","interaction":read_search,"searchParam":[{"name":"_id","type":"token"},{"name":"family","type":"string"},{"name":"given","type":"string"}]},*patient_resources,*status_resources,*directory_resources]
    base=settings.api_public_url.rstrip("/")
    oauth_uris=[{"url":"authorize","valueUri":f"{base}/oauth2/default/authorize"},{"url":"token","valueUri":f"{base}/oauth2/default/token"},{"url":"revoke","valueUri":f"{base}/oauth2/default/revoke"}]
    return {"resourceType":"CapabilityStatement","status":"active","date":"2026-09-15","kind":"instance","fhirVersion":"4.0.1","format":["json"],"rest":[{"mode":"server","security":{"cors":True,"service":[{"coding":[{"system":"http://terminology.hl7.org/CodeSystem/restful-security-service","code":"SMART-on-FHIR"}]}],"extension":[{"url":"http://fhir-registry.smarthealthit.org/StructureDefinition/oauth-uris","extension":oauth_uris}]},"resource":resources}]}


@router.get("/Patient/{patient_uuid}")
def read_patient(patient_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_or_404(db, patient_uuid); audit(db, user, "Patient", patient.uuid); return patient_resource(patient)


@router.get("/Patient")
def search_patients(family: str | None = None, given: str | None = None, resource_id:str|None=Query(default=None,alias="_id"), db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    query = select(Patient).where(Patient.merged_at.is_(None))
    if resource_id: query = query.where(Patient.uuid == resource_id.rsplit("/",1)[-1])
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
    item=patient_or_404(db,patient_reference(patient)); resources=clinical_resources(db,item,"problem"); audit(db,user,"Condition",item.uuid,search=True); return bundle("Condition",resources)


@router.get("/AllergyIntolerance")
def allergies(patient: str = Query(), db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    item=patient_or_404(db,patient_reference(patient)); resources=clinical_resources(db,item,"allergy"); audit(db,user,"AllergyIntolerance",item.uuid,search=True); return bundle("AllergyIntolerance",resources)


@router.get("/MedicationStatement")
def medications(patient: str = Query(), db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    item=patient_or_404(db,patient_reference(patient)); resources=clinical_resources(db,item,"medication"); audit(db,user,"MedicationStatement",item.uuid,search=True); return bundle("MedicationStatement",resources)


VITAL_CODES=(("systolic","8480-6","Systolic blood pressure","mm[Hg]"),("diastolic","8462-4","Diastolic blood pressure","mm[Hg]"),("weight_kg","29463-7","Body weight","kg"),("height_cm","8302-2","Body height","cm"),("temperature_c","8310-5","Body temperature","Cel"),("heart_rate","8867-4","Heart rate","/min"),("respiratory_rate","9279-1","Respiratory rate","/min"),("oxygen_saturation","2708-6","Oxygen saturation","%"),("bmi","39156-5","Body mass index","kg/m2"))


def lab_observation_resource(result: LabResult, patient_uuid: str) -> dict:
    value={"valueQuantity":{"value":float(result.value),"unit":result.unit}} if result.value.replace(".","",1).isdigit() else {"valueString":result.value}
    return {"resourceType":"Observation","id":result.uuid,"status":result.status,"category":[{"coding":[{"system":"http://terminology.hl7.org/CodeSystem/observation-category","code":"laboratory"}]}],"code":{"coding":[{"system":"http://loinc.org","code":result.code,"display":result.name}],"text":result.name},"subject":{"reference":f"Patient/{patient_uuid}"},"effectiveDateTime":result.observed_at.isoformat(),**value,**({"referenceRange":[{"text":result.reference_range}]} if result.reference_range else {})}


def vital_observation_resource(vital: VitalSet, patient_uuid: str, field: str, code: str, name: str, unit: str) -> dict:
    return {"resourceType":"Observation","id":f"{vital.uuid}-{field}","status":"final","category":[{"coding":[{"system":"http://terminology.hl7.org/CodeSystem/observation-category","code":"vital-signs"}]}],"code":{"coding":[{"system":"http://loinc.org","code":code,"display":name}]},"subject":{"reference":f"Patient/{patient_uuid}"},"effectiveDateTime":vital.observed_at.isoformat(),"valueQuantity":{"value":float(getattr(vital,field)),"unit":unit}}


@router.get("/Observation")
def observations(patient: str = Query(), db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    item=patient_or_404(db,patient_reference(patient)); rows=db.execute(select(LabResult).join(LabOrder).where(LabOrder.patient_id==item.id).order_by(LabResult.observed_at.desc())).scalars().all(); resources=[]
    for result in rows:
        resources.append(lab_observation_resource(result,item.uuid))
    vitals=db.scalars(select(VitalSet).where(VitalSet.patient_id==item.id)).all()
    for vital in vitals:
        for field,code,name,unit in VITAL_CODES:
            value=getattr(vital,field)
            if value is not None: resources.append(vital_observation_resource(vital,item.uuid,field,code,name,unit))
    audit(db,user,"Observation",item.uuid,search=True); return bundle("Observation",resources)


@router.get("/Immunization")
def fhir_immunizations(patient: str = Query(), db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    item=patient_or_404(db,patient_reference(patient)); rows=db.scalars(select(Immunization).where(Immunization.patient_id==item.id)).all(); resources=[immunization_resource(x,item.uuid) for x in rows]; audit(db,user,"Immunization",item.uuid,search=True); return bundle("Immunization",resources)


@router.get("/MedicationRequest")
def medication_requests(patient: str = Query(), db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    item=patient_or_404(db,patient_reference(patient)); rows=db.scalars(select(Prescription).where(Prescription.patient_id==item.id)).all(); resources=[medication_request_resource(x,item.uuid) for x in rows]; audit(db,user,"MedicationRequest",item.uuid,search=True); return bundle("MedicationRequest",resources)


FHIR_STATUS={"draft":"draft","active":"active","on-hold":"on-hold","inactive":"revoked","revoked":"revoked","cancelled":"revoked","canceled":"revoked","completed":"completed","entered-in-error":"entered-in-error","unknown":"unknown"}
ACTIVITY_STATUS={"draft":"not-started","active":"in-progress","on-hold":"on-hold","revoked":"stopped","cancelled":"cancelled","canceled":"cancelled","completed":"completed","entered-in-error":"entered-in-error","unknown":"unknown"}
ACHIEVEMENT_BY_STATUS={"active":"in-progress","on-hold":"sustaining","completed":"achieved","cancelled":"not-achieved","canceled":"not-achieved"}


def fhir_not_found(resource_type:str):
    raise HTTPException(status_code=404,detail={"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"not-found","diagnostics":f"{resource_type} not found"}]})


def patient_reference(value:str)->str:
    return value.removeprefix("Patient/")


def coded_concept(code:str|None,display:str|None)->dict:
    concept={"text":display or code or "Care plan"}
    if code:
        prefix,value=code.split(":",1) if ":" in code else ("",code);systems={"SNOMED-CT":"http://snomed.info/sct","SNOMED":"http://snomed.info/sct","LOINC":"http://loinc.org","ICD10":"http://hl7.org/fhir/sid/icd-10-cm"}
        concept["coding"]=[{"system":systems.get(prefix,prefix or "urn:openrm:care-plan-code"),"code":value,"display":display or value}]
    return concept


def source_status_extension(status_value:str,mapped:str)->list[dict]:
    return [{"url":"https://openrm.org/fhir/StructureDefinition/source-status","valueCode":status_value}] if status_value!=mapped else []


def latest_outcome(db:Session,plan_id:int)->CarePlanOutcome|None:
    return db.scalar(select(CarePlanOutcome).where(CarePlanOutcome.care_plan_id==plan_id).order_by(CarePlanOutcome.recorded_at.desc(),CarePlanOutcome.id.desc()).limit(1))


def goal_resource(db:Session,plan:CarePlan,patient_uuid:str)->dict:
    lifecycle=FHIR_STATUS.get(plan.status,"unknown");outcome=latest_outcome(db,plan.id);achievement=outcome.achievement_status if outcome and outcome.achievement_status else ACHIEVEMENT_BY_STATUS.get(plan.status)
    resource={"resourceType":"Goal","id":plan.uuid,"meta":{"profile":["http://hl7.org/fhir/us/core/StructureDefinition/us-core-goal"]},"lifecycleStatus":lifecycle,"category":[{"text":plan.engagement_category or "Clinical goal"}],"description":coded_concept(plan.code,plan.code_text or plan.description),"subject":{"reference":f"Patient/{patient_uuid}"},"startDate":plan.recorded_at.date().isoformat(),"extension":source_status_extension(plan.status,lifecycle)}
    if achievement:resource["achievementStatus"]={"coding":[{"system":"http://terminology.hl7.org/CodeSystem/goal-achievement","code":achievement}]}
    if plan.target_date:resource["target"]=[{"dueDate":plan.target_date.date().isoformat()}]
    if plan.note_related_to or plan.reason_description:resource["note"]=[{"text":text} for text in (plan.note_related_to,plan.reason_description) if text]
    return resource


def care_plan_resource(db:Session,plan:CarePlan,patient_uuid:str)->dict:
    status_value=FHIR_STATUS.get(plan.status,"unknown");encounter_uuid=db.scalar(select(Encounter.uuid).where(Encounter.id==plan.encounter_id));goal_ids=list(db.scalars(select(CarePlan.uuid).where(CarePlan.patient_id==plan.patient_id,CarePlan.encounter_id==plan.encounter_id,CarePlan.plan_type=="goal",CarePlan.active.is_(True))))
    resource={"resourceType":"CarePlan","id":plan.uuid,"meta":{"profile":["http://hl7.org/fhir/us/core/StructureDefinition/us-core-careplan"]},"status":status_value,"intent":"plan","category":[{"coding":[{"system":"http://hl7.org/fhir/us/core/CodeSystem/careplan-category","code":"assess-plan"}]}],"title":plan.code_text or plan.description,"description":plan.description,"subject":{"reference":f"Patient/{patient_uuid}"},"created":plan.recorded_at.isoformat(),"period":{"start":plan.recorded_at.isoformat(),**({"end":plan.ends_at.isoformat()} if plan.ends_at else {})},"activity":[{"detail":{"status":ACTIVITY_STATUS.get(plan.status,"unknown"),"code":coded_concept(plan.code,plan.code_text or plan.description),**({"scheduledPeriod":{"start":plan.recorded_at.isoformat(),"end":plan.target_date.isoformat()}} if plan.target_date else {})}}],"extension":source_status_extension(plan.status,status_value)}
    if encounter_uuid:resource["encounter"]={"reference":f"Encounter/{encounter_uuid}"}
    if goal_ids:resource["goal"]=[{"reference":f"Goal/{goal_uuid}"} for goal_uuid in goal_ids]
    if plan.reason_code:resource["extension"].append({"url":"https://openrm.org/fhir/StructureDefinition/care-plan-reason","valueCodeableConcept":coded_concept(plan.reason_code,plan.reason_description)})
    if plan.note_related_to:resource["note"]=[{"text":plan.note_related_to}]
    return resource


def care_team_resource(db:Session,team:CareTeam,patient_uuid:str)->dict:
    members=list(db.scalars(select(CareTeamMember).where(CareTeamMember.care_team_id==team.id).order_by(CareTeamMember.id)));participants=[]
    for member in members:
        reference=None
        if member.practitioner_id:
            uuid=db.scalar(select(Practitioner.uuid).where(Practitioner.id==member.practitioner_id));reference=f"Practitioner/{uuid}" if uuid else None
        elif member.facility_id:
            uuid=db.scalar(select(Facility.uuid).where(Facility.id==member.facility_id));reference=f"Organization/{uuid}" if uuid else None
        participant={"role":[{"text":member.role}],"member":{"display":member.display_name,**({"reference":reference} if reference else {})},**({"period":{"start":member.provider_since.isoformat()}} if member.provider_since else {})}
        if member.status not in {"active","proposed"}:participant["extension"]=[{"url":"https://openrm.org/fhir/StructureDefinition/participant-status","valueCode":member.status}]
        participants.append(participant)
    status_value=team.status if team.status in {"proposed","active","suspended","inactive","entered-in-error"} else "entered-in-error" if team.status=="entered-in-error" else "inactive"
    return {"resourceType":"CareTeam","id":team.uuid,"meta":{"profile":["http://hl7.org/fhir/us/core/StructureDefinition/us-core-careteam"]},"status":status_value,"name":team.name,"subject":{"reference":f"Patient/{patient_uuid}"},"participant":participants,"period":{"start":team.created_at.isoformat(),**({"end":team.updated_at.isoformat()} if status_value=="inactive" else {})},**({"note":[{"text":team.note}]} if team.note else {})}


@router.get("/CarePlan")
def search_care_plans(patient:str=Query(),status:str|None=None,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    owner=patient_or_404(db,patient_reference(patient));rows=list(db.scalars(select(CarePlan).where(CarePlan.patient_id==owner.id,or_(CarePlan.plan_type!="goal",CarePlan.plan_type.is_(None))).order_by(CarePlan.recorded_at.desc())));resources=[care_plan_resource(db,row,owner.uuid) for row in rows];resources=[item for item in resources if not status or item["status"]==status];audit(db,user,"CarePlan",owner.uuid,search=True);return bundle("CarePlan",resources)


@router.get("/CarePlan/{resource_uuid}")
def read_care_plan(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    row=db.scalar(select(CarePlan).where(CarePlan.uuid==resource_uuid,or_(CarePlan.plan_type!="goal",CarePlan.plan_type.is_(None))));
    if not row:fhir_not_found("CarePlan")
    owner=db.get(Patient,row.patient_id);result=care_plan_resource(db,row,owner.uuid);audit(db,user,"CarePlan",row.uuid);return result


@router.get("/Goal")
def search_goals(patient:str=Query(),status:str|None=None,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    owner=patient_or_404(db,patient_reference(patient));rows=list(db.scalars(select(CarePlan).where(CarePlan.patient_id==owner.id,CarePlan.plan_type=="goal").order_by(CarePlan.recorded_at.desc())));resources=[goal_resource(db,row,owner.uuid) for row in rows];resources=[item for item in resources if not status or item["lifecycleStatus"]==status];audit(db,user,"Goal",owner.uuid,search=True);return bundle("Goal",resources)


@router.get("/Goal/{resource_uuid}")
def read_goal(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    row=db.scalar(select(CarePlan).where(CarePlan.uuid==resource_uuid,CarePlan.plan_type=="goal"));
    if not row:fhir_not_found("Goal")
    owner=db.get(Patient,row.patient_id);result=goal_resource(db,row,owner.uuid);audit(db,user,"Goal",row.uuid);return result


@router.get("/CareTeam")
def search_care_teams(patient:str=Query(),status:str|None=None,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    owner=patient_or_404(db,patient_reference(patient));rows=list(db.scalars(select(CareTeam).where(CareTeam.patient_id==owner.id).order_by(CareTeam.created_at.desc())));resources=[care_team_resource(db,row,owner.uuid) for row in rows];resources=[item for item in resources if not status or item["status"]==status];audit(db,user,"CareTeam",owner.uuid,search=True);return bundle("CareTeam",resources)


@router.get("/CareTeam/{resource_uuid}")
def read_care_team(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    row=db.scalar(select(CareTeam).where(CareTeam.uuid==resource_uuid));
    if not row:fhir_not_found("CareTeam")
    owner=db.get(Patient,row.patient_id);result=care_team_resource(db,row,owner.uuid);audit(db,user,"CareTeam",row.uuid);return result


def immunization_resource(item: Immunization, patient_uuid: str) -> dict:
    return {"resourceType":"Immunization","id":item.uuid,"status":item.status,"vaccineCode":{"coding":[{"system":"http://hl7.org/fhir/sid/cvx","code":item.cvx_code,"display":item.vaccine_name}]},"patient":{"reference":f"Patient/{patient_uuid}"},"occurrenceDateTime":item.administered_at.isoformat(),**({"lotNumber":item.lot_number} if item.lot_number else {}),**({"manufacturer":{"display":item.manufacturer}} if item.manufacturer else {}),**({"note":[{"text":item.note}]} if item.note else {})}


def medication_request_resource(item: Prescription, patient_uuid: str) -> dict:
    return {"resourceType":"MedicationRequest","id":item.uuid,"status":item.status,"intent":"order","medicationCodeableConcept":{"coding":[{"system":"http://www.nlm.nih.gov/research/umls/rxnorm","code":item.rxnorm_code,"display":item.drug_name}] if item.rxnorm_code else [],"text":item.drug_name},"subject":{"reference":f"Patient/{patient_uuid}"},"authoredOn":item.prescribed_at.isoformat(),"dosageInstruction":[{"text":item.dosage_instructions}],"dispenseRequest":{"numberOfRepeatsAllowed":item.refills,**({"quantity":{"value":float(item.quantity)}} if item.quantity and item.quantity.replace(".","",1).isdigit() else {})},"substitution":{"allowedBoolean":item.substitutions_allowed}}


def read_clinical_resource(resource_uuid: str, category: str, resource_type: str, db: Session, user: User):
    item=db.scalar(select(ClinicalItem).where(ClinicalItem.uuid==resource_uuid,ClinicalItem.category==category))
    if not item:fhir_not_found(resource_type)
    patient=db.get(Patient,item.patient_id);resource=next(value for value in clinical_resources(db,patient,category) if value["id"]==item.uuid)
    audit(db,user,resource_type,item.uuid);return resource


@router.get("/Condition/{resource_uuid}")
def read_condition(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    return read_clinical_resource(resource_uuid,"problem","Condition",db,user)


@router.get("/AllergyIntolerance/{resource_uuid}")
def read_allergy(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    return read_clinical_resource(resource_uuid,"allergy","AllergyIntolerance",db,user)


@router.get("/MedicationStatement/{resource_uuid}")
def read_medication_statement(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    return read_clinical_resource(resource_uuid,"medication","MedicationStatement",db,user)


@router.get("/Immunization/{resource_uuid}")
def read_immunization(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    row=db.scalar(select(Immunization).where(Immunization.uuid==resource_uuid))
    if not row:fhir_not_found("Immunization")
    patient=db.get(Patient,row.patient_id);resource=immunization_resource(row,patient.uuid);audit(db,user,"Immunization",row.uuid);return resource


@router.get("/MedicationRequest/{resource_uuid}")
def read_medication_request(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    row=db.scalar(select(Prescription).where(Prescription.uuid==resource_uuid))
    if not row:fhir_not_found("MedicationRequest")
    patient=db.get(Patient,row.patient_id);resource=medication_request_resource(row,patient.uuid);audit(db,user,"MedicationRequest",row.uuid);return resource


@router.get("/Observation/{resource_id}")
def read_observation(resource_id:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    result=db.execute(select(LabResult,Patient.uuid).join(LabOrder,LabResult.order_id==LabOrder.id).join(Patient,LabOrder.patient_id==Patient.id).where(LabResult.uuid==resource_id)).first()
    if result:
        row,patient_uuid=result;resource=lab_observation_resource(row,patient_uuid);audit(db,user,"Observation",resource_id);return resource
    for field,code,name,unit in VITAL_CODES:
        suffix=f"-{field}"
        if resource_id.endswith(suffix):
            vital_uuid=resource_id[:-len(suffix)];vital_row=db.execute(select(VitalSet,Patient.uuid).join(Patient,VitalSet.patient_id==Patient.id).where(VitalSet.uuid==vital_uuid)).first()
            if vital_row and getattr(vital_row[0],field) is not None:
                resource=vital_observation_resource(vital_row[0],vital_row[1],field,code,name,unit);audit(db,user,"Observation",resource_id);return resource
    fhir_not_found("Observation")


APPOINTMENT_STATUS={"scheduled":"booked","confirmed":"booked","arrived":"arrived","checked-in":"checked-in","in-progress":"arrived","fulfilled":"fulfilled","completed":"fulfilled","cancelled":"cancelled","canceled":"cancelled","no-show":"noshow","entered-in-error":"entered-in-error","pending":"pending"}
ENCOUNTER_STATUS={"planned":"planned","arrived":"arrived","triaged":"triaged","open":"in-progress","in-progress":"in-progress","onleave":"onleave","closed":"finished","finished":"finished","cancelled":"cancelled","canceled":"cancelled","entered-in-error":"entered-in-error","unknown":"unknown"}


def appointment_resource(db: Session, item: Appointment, patient_uuid: str) -> dict:
    facility=db.get(Facility,item.facility_id) if item.facility_id else db.scalar(select(Facility).where(Facility.legacy_facility_id==item.legacy_facility_id)) if item.legacy_facility_id else None
    resource={"resourceType":"Appointment","id":item.uuid,"status":APPOINTMENT_STATUS.get(item.status,"proposed"),"start":item.starts_at.isoformat(),"end":item.ends_at.isoformat(),"participant":[{"actor":{"reference":f"Patient/{patient_uuid}"},"status":"accepted"}],**({"description":item.title} if item.title else {}),**({"reasonCode":[{"text":item.reason}]} if item.reason else {})}
    if facility:resource["participant"].append({"actor":{"reference":f"Location/{facility.uuid}","display":facility.name},"status":"accepted"})
    elif item.facility_name or item.location:resource["participant"].append({"actor":{"display":item.facility_name or item.location},"status":"accepted"})
    if item.provider_name:resource["participant"].append({"actor":{"display":item.provider_name},"status":"accepted"})
    return resource


def encounter_resource(db: Session, item: Encounter, patient_uuid: str) -> dict:
    appointment_uuid=db.scalar(select(Appointment.uuid).where(Appointment.id==item.appointment_id)) if item.appointment_id else None
    resource={"resourceType":"Encounter","id":item.uuid,"status":ENCOUNTER_STATUS.get(item.status,"unknown"),"class":{"system":"http://terminology.hl7.org/CodeSystem/v3-ActCode","code":"AMB" if item.type=="ambulatory" else item.type},"type":[{"text":item.type}],"subject":{"reference":f"Patient/{patient_uuid}"},"period":{"start":item.occurred_at.isoformat()},**({"reasonCode":[{"text":item.chief_complaint}]} if item.chief_complaint else {})}
    if appointment_uuid:resource["appointment"]=[{"reference":f"Appointment/{appointment_uuid}"}]
    return resource


def organization_resource(item: Facility) -> dict:
    telecom=[]
    for system,value in (("phone",item.phone),("fax",item.fax),("email",item.email),("url",item.website)):
        if value:telecom.append({"system":system,"value":value})
    return {"resourceType":"Organization","id":item.uuid,"active":item.active,"name":item.name,**({"identifier":[{"system":"http://hl7.org/fhir/sid/us-npi","value":item.npi}]} if item.npi else {}),**({"telecom":telecom} if telecom else {}),**({"address":[{key:value for key,value in (("line",[item.street] if item.street else None),("city",item.city),("state",item.state),("postalCode",item.postal_code),("country",item.country_code)) if value}]} if any((item.street,item.city,item.state,item.postal_code,item.country_code)) else {})}


def payer_organization_resource(item: Payer) -> dict:
    return {"resourceType":"Organization","id":item.uuid,"active":item.active,"type":[{"coding":[{"system":"http://terminology.hl7.org/CodeSystem/organization-type","code":"pay","display":"Payer"}]}],"name":item.name,**({"identifier":[{"system":"urn:openrm:payer-identifier","value":item.payer_identifier}]} if item.payer_identifier else {})}


def location_resource(item: Facility) -> dict:
    return {"resourceType":"Location","id":item.uuid,"status":"active" if item.active else "inactive","name":item.name,"mode":"instance","managingOrganization":{"reference":f"Organization/{item.uuid}"},**({"telecom":[{"system":system,"value":value} for system,value in (("phone",item.phone),("fax",item.fax),("email",item.email)) if value]} if item.phone or item.fax or item.email else {}),**({"address":{key:value for key,value in (("line",[item.street] if item.street else None),("city",item.city),("state",item.state),("postalCode",item.postal_code),("country",item.country_code)) if value}} if any((item.street,item.city,item.state,item.postal_code,item.country_code)) else {})}


def practitioner_resource(db: Session, item: Practitioner) -> dict:
    facility_uuid=db.scalar(select(Facility.uuid).where(Facility.id==item.primary_facility_id)) if item.primary_facility_id else None
    return {"resourceType":"Practitioner","id":item.uuid,"active":item.active,"name":[{"family":item.last_name,"given":[value for value in (item.first_name,item.middle_name) if value],**({"prefix":[item.title]} if item.title else {})}],**({"identifier":[{"system":"http://hl7.org/fhir/sid/us-npi","value":item.npi}]} if item.npi else {}),**({"telecom":[{"system":system,"value":value} for system,value in (("phone",item.phone),("email",item.email)) if value]} if item.phone or item.email else {}),**({"qualification":[{"code":{"text":item.specialty}}]} if item.specialty else {}),**({"extension":[{"url":"https://openrm.org/fhir/StructureDefinition/primary-organization","valueReference":{"reference":f"Organization/{facility_uuid}"}}]} if facility_uuid else {})}


def appointment_access(db: Session, user: User, item: Appointment):
    facility_id=item.facility_id or (db.scalar(select(Facility.id).where(Facility.legacy_facility_id==item.legacy_facility_id)) if item.legacy_facility_id else None)
    require_facility_access(db,user,facility_id)


@router.get("/Appointment")
def search_appointments(patient:str=Query(),status:str|None=None,db:Session=Depends(get_db),user:User=Depends(appointment_user)):
    owner=patient_or_404(db,patient_reference(patient));query=select(Appointment).where(Appointment.patient_id==owner.id);scope=facility_scope(db,user)
    if scope is not None:
        legacy_ids=list(db.scalars(select(Facility.legacy_facility_id).where(Facility.id.in_(scope),Facility.legacy_facility_id.is_not(None))));query=query.where(or_(Appointment.facility_id.in_(scope),Appointment.legacy_facility_id.in_(legacy_ids)))
    rows=list(db.scalars(query.order_by(Appointment.starts_at)));resources=[appointment_resource(db,row,owner.uuid) for row in rows];resources=[resource for resource in resources if not status or resource["status"]==status];audit(db,user,"Appointment",owner.uuid,search=True);return bundle("Appointment",resources)


@router.get("/Appointment/{resource_uuid}")
def read_appointment(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(appointment_user)):
    row=db.scalar(select(Appointment).where(Appointment.uuid==resource_uuid))
    if not row:fhir_not_found("Appointment")
    appointment_access(db,user,row);patient=db.get(Patient,row.patient_id);resource=appointment_resource(db,row,patient.uuid);audit(db,user,"Appointment",row.uuid);return resource


@router.get("/Encounter")
def search_encounters(patient:str=Query(),status:str|None=None,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    owner=patient_or_404(db,patient_reference(patient));rows=list(db.scalars(select(Encounter).where(Encounter.patient_id==owner.id).order_by(Encounter.occurred_at.desc())));resources=[encounter_resource(db,row,owner.uuid) for row in rows];resources=[resource for resource in resources if not status or resource["status"]==status];audit(db,user,"Encounter",owner.uuid,search=True);return bundle("Encounter",resources)


@router.get("/Encounter/{resource_uuid}")
def read_encounter(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    row=db.scalar(select(Encounter).where(Encounter.uuid==resource_uuid))
    if not row:fhir_not_found("Encounter")
    patient=db.get(Patient,row.patient_id);resource=encounter_resource(db,row,patient.uuid);audit(db,user,"Encounter",row.uuid);return resource


@router.get("/Organization")
def search_organizations(name:str|None=None,active:bool|None=None,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    facility_query=select(Facility);payer_query=select(Payer)
    if name:facility_query=facility_query.where(Facility.name.ilike(f"%{name}%"));payer_query=payer_query.where(Payer.name.ilike(f"%{name}%"))
    if active is not None:facility_query=facility_query.where(Facility.active.is_(active));payer_query=payer_query.where(Payer.active.is_(active))
    facilities=list(db.scalars(facility_query.order_by(Facility.name).limit(100)));payers=list(db.scalars(payer_query.order_by(Payer.name).limit(max(0,100-len(facilities)))));resources=[organization_resource(row) for row in facilities]+[payer_organization_resource(row) for row in payers];audit(db,user,"Organization",search=True);return bundle("Organization",resources)


@router.get("/Organization/{resource_uuid}")
def read_organization(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    row=db.scalar(select(Facility).where(Facility.uuid==resource_uuid))
    if row:audit(db,user,"Organization",row.uuid);return organization_resource(row)
    payer=db.scalar(select(Payer).where(Payer.uuid==resource_uuid))
    if not payer:fhir_not_found("Organization")
    audit(db,user,"Organization",payer.uuid);return payer_organization_resource(payer)


@router.get("/Location")
def search_locations(name:str|None=None,active:bool|None=None,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    query=select(Facility).where(Facility.service_location.is_(True))
    if name:query=query.where(Facility.name.ilike(f"%{name}%"))
    if active is not None:query=query.where(Facility.active.is_(active))
    rows=list(db.scalars(query.order_by(Facility.name).limit(100)));audit(db,user,"Location",search=True);return bundle("Location",[location_resource(row) for row in rows])


@router.get("/Location/{resource_uuid}")
def read_location(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    row=db.scalar(select(Facility).where(Facility.uuid==resource_uuid,Facility.service_location.is_(True)))
    if not row:fhir_not_found("Location")
    audit(db,user,"Location",row.uuid);return location_resource(row)


@router.get("/Practitioner")
def search_practitioners(family:str|None=None,given:str|None=None,identifier:str|None=None,active:bool|None=None,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    query=select(Practitioner)
    if family:query=query.where(Practitioner.last_name.ilike(f"%{family}%"))
    if given:query=query.where(Practitioner.first_name.ilike(f"%{given}%"))
    if identifier:query=query.where(Practitioner.npi==identifier.rsplit("|",1)[-1])
    if active is not None:query=query.where(Practitioner.active.is_(active))
    rows=list(db.scalars(query.order_by(Practitioner.last_name,Practitioner.first_name).limit(100)));audit(db,user,"Practitioner",search=True);return bundle("Practitioner",[practitioner_resource(db,row) for row in rows])


@router.get("/Practitioner/{resource_uuid}")
def read_practitioner(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    row=db.scalar(select(Practitioner).where(Practitioner.uuid==resource_uuid))
    if not row:fhir_not_found("Practitioner")
    audit(db,user,"Practitioner",row.uuid);return practitioner_resource(db,row)


def coverage_status(item: Coverage) -> str:
    today=date.today()
    if item.ends_on and item.ends_on < today:return "cancelled"
    if item.starts_on and item.starts_on > today:return "draft"
    return "active"


def coverage_resource(item: Coverage, patient_uuid: str, payer: Payer) -> dict:
    order={"primary":1,"secondary":2,"tertiary":3}.get(item.priority)
    classes=[]
    if item.group_number:classes.append({"type":{"coding":[{"system":"http://terminology.hl7.org/CodeSystem/coverage-class","code":"group"}]},"value":item.group_number})
    if item.plan_name:classes.append({"type":{"coding":[{"system":"http://terminology.hl7.org/CodeSystem/coverage-class","code":"plan"}]},"value":item.plan_name})
    return {"resourceType":"Coverage","id":item.uuid,"status":coverage_status(item),"beneficiary":{"reference":f"Patient/{patient_uuid}"},"subscriber":{"display":item.subscriber_name},"subscriberId":item.policy_number,"relationship":{"coding":[{"system":"http://terminology.hl7.org/CodeSystem/subscriber-relationship","code":item.relationship}]},"payor":[{"reference":f"Organization/{payer.uuid}","display":payer.name}],**({"order":order} if order else {}),**({"period":{key:value.isoformat() for key,value in (("start",item.starts_on),("end",item.ends_on)) if value}} if item.starts_on or item.ends_on else {}),**({"class":classes} if classes else {})}


def document_reference_resource(db: Session, item: Document, patient_uuid: str) -> dict:
    encounter_uuid=db.scalar(select(Encounter.uuid).where(Encounter.id==item.encounter_id)) if item.encounter_id else None
    digest=b64encode(bytes.fromhex(item.sha256)).decode()
    return {"resourceType":"DocumentReference","id":item.uuid,"status":"current","type":{"coding":[{"system":"urn:ietf:bcp:13","code":item.mime_type}],"text":item.name},"subject":{"reference":f"Patient/{patient_uuid}"},"date":item.uploaded_at.isoformat(),"content":[{"attachment":{"contentType":item.mime_type,"url":f"/fhir/Binary/{item.uuid}","title":item.name,"hash":digest}}],**({"context":{"encounter":[{"reference":f"Encounter/{encounter_uuid}"}]}} if encounter_uuid else {})}


def matches_fhir_date(value, search_value: str) -> bool:
    operator=search_value[:2] if search_value[:2] in {"eq","gt","ge","lt","le"} else "eq";raw=search_value[2:] if operator!="eq" or search_value.startswith("eq") else search_value
    try:target=date.fromisoformat(raw)
    except ValueError:raise HTTPException(status_code=400,detail={"resourceType":"OperationOutcome","issue":[{"severity":"error","code":"invalid","diagnostics":"date must use a supported FHIR prefix and YYYY-MM-DD"}]})
    actual=value.date();comparisons={"eq":actual==target,"gt":actual>target,"ge":actual>=target,"lt":actual<target,"le":actual<=target};return comparisons[operator]


@router.get("/Coverage")
def search_coverages(patient:str=Query(),status:str|None=None,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    owner=patient_or_404(db,patient_reference(patient));rows=db.execute(select(Coverage,Payer).join(Payer).where(Coverage.patient_id==owner.id).order_by(Coverage.priority)).all();resources=[coverage_resource(item,owner.uuid,payer) for item,payer in rows];resources=[resource for resource in resources if not status or resource["status"]==status];audit(db,user,"Coverage",owner.uuid,search=True);return bundle("Coverage",resources)


@router.get("/Coverage/{resource_uuid}")
def read_coverage(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    row=db.execute(select(Coverage,Patient.uuid,Payer).join(Patient,Coverage.patient_id==Patient.id).join(Payer,Coverage.payer_id==Payer.id).where(Coverage.uuid==resource_uuid)).first()
    if not row:fhir_not_found("Coverage")
    item,patient_uuid,payer=row;resource=coverage_resource(item,patient_uuid,payer);audit(db,user,"Coverage",item.uuid);return resource


@router.get("/DocumentReference")
def search_document_references(patient:str=Query(),document_type:str|None=Query(default=None,alias="type"),date_value:str|None=Query(default=None,alias="date"),db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    owner=patient_or_404(db,patient_reference(patient));query=select(Document).where(Document.patient_id==owner.id)
    if document_type:query=query.where(Document.mime_type==document_type.rsplit("|",1)[-1])
    rows=list(db.scalars(query.order_by(Document.uploaded_at.desc())));resources=[document_reference_resource(db,item,owner.uuid) for item in rows]
    if date_value:resources=[resource for resource,item in zip(resources,rows) if matches_fhir_date(item.uploaded_at,date_value)]
    audit(db,user,"DocumentReference",owner.uuid,search=True);return bundle("DocumentReference",resources)


@router.get("/DocumentReference/{resource_uuid}")
def read_document_reference(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    row=db.execute(select(Document,Patient.uuid).join(Patient,Document.patient_id==Patient.id).where(Document.uuid==resource_uuid)).first()
    if not row:fhir_not_found("DocumentReference")
    item,patient_uuid=row;resource=document_reference_resource(db,item,patient_uuid);audit(db,user,"DocumentReference",item.uuid);return resource


@router.get("/Binary/{resource_uuid}")
def read_binary(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    item=db.scalar(select(Document).where(Document.uuid==resource_uuid))
    if not item:fhir_not_found("Binary")
    audit(db,user,"Binary",item.uuid);safe_name=item.name.replace('"',"");return Response(item.content,media_type=item.mime_type,headers={"Content-Disposition":f'attachment; filename="{safe_name}"',"ETag":item.sha256})


SERVICE_REQUEST_STATUS={"pending":"active","routed":"active","in-progress":"active","complete":"completed","completed":"completed","canceled":"revoked","cancelled":"revoked","on-hold":"on-hold","draft":"draft","entered-in-error":"entered-in-error"}
DIAGNOSTIC_REPORT_STATUS={"pending":"registered","routed":"registered","in-progress":"preliminary","complete":"final","completed":"final","canceled":"cancelled","cancelled":"cancelled","entered-in-error":"entered-in-error"}


def lab_order_context(db: Session, item: LabOrder):
    patient_uuid=db.scalar(select(Patient.uuid).where(Patient.id==item.patient_id));encounter_uuid=db.scalar(select(Encounter.uuid).where(Encounter.id==item.encounter_id)) if item.encounter_id else None;return patient_uuid,encounter_uuid


def service_request_resource(db: Session, item: LabOrder, patient_uuid: str | None = None) -> dict:
    if patient_uuid is None:patient_uuid,encounter_uuid=lab_order_context(db,item)
    else:encounter_uuid=db.scalar(select(Encounter.uuid).where(Encounter.id==item.encounter_id)) if item.encounter_id else None
    status_value=SERVICE_REQUEST_STATUS.get(item.status,"unknown")
    return {"resourceType":"ServiceRequest","id":item.uuid,"meta":{"profile":["http://hl7.org/fhir/us/core/StructureDefinition/us-core-servicerequest"]},"status":status_value,"intent":"order","category":[{"coding":[{"system":"http://snomed.info/sct","code":"108252007","display":"Laboratory procedure"}]}],"priority":item.priority if item.priority in {"routine","urgent","asap","stat"} else "routine","code":{"coding":[{"system":"http://loinc.org","code":item.code,"display":item.name}],"text":item.name},"subject":{"reference":f"Patient/{patient_uuid}"},"authoredOn":item.ordered_at.isoformat(),**({"encounter":{"reference":f"Encounter/{encounter_uuid}"}} if encounter_uuid else {}),**({"patientInstruction":item.instructions} if item.instructions else {})}


def diagnostic_report_resource(db: Session, item: LabOrder, patient_uuid: str | None = None, results: list[LabResult] | None = None) -> dict:
    if patient_uuid is None:patient_uuid,encounter_uuid=lab_order_context(db,item)
    else:encounter_uuid=db.scalar(select(Encounter.uuid).where(Encounter.id==item.encounter_id)) if item.encounter_id else None
    if results is None:results=list(db.scalars(select(LabResult).where(LabResult.order_id==item.id).order_by(LabResult.observed_at)))
    status_value="corrected" if any(result.status=="corrected" for result in results) else DIAGNOSTIC_REPORT_STATUS.get(item.status,"unknown")
    effective=max((result.observed_at for result in results),default=item.ordered_at)
    return {"resourceType":"DiagnosticReport","id":item.uuid,"meta":{"profile":["http://hl7.org/fhir/us/core/StructureDefinition/us-core-diagnosticreport-lab"]},"status":status_value,"category":[{"coding":[{"system":"http://terminology.hl7.org/CodeSystem/v2-0074","code":"LAB","display":"Laboratory"}]}],"code":{"coding":[{"system":"http://loinc.org","code":item.code,"display":item.name}],"text":item.name},"subject":{"reference":f"Patient/{patient_uuid}"},"effectiveDateTime":effective.isoformat(),"issued":effective.isoformat(),"basedOn":[{"reference":f"ServiceRequest/{item.uuid}"}],"result":[{"reference":f"Observation/{result.uuid}","display":result.name} for result in results],**({"encounter":{"reference":f"Encounter/{encounter_uuid}"}} if encounter_uuid else {})}


@router.get("/ServiceRequest")
def search_service_requests(patient:str=Query(),status:str|None=None,code:str|None=None,authored:str|None=None,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    owner=patient_or_404(db,patient_reference(patient));query=select(LabOrder).where(LabOrder.patient_id==owner.id)
    if code:query=query.where(LabOrder.code==code.rsplit("|",1)[-1])
    rows=list(db.scalars(query.order_by(LabOrder.ordered_at.desc())));resources=[service_request_resource(db,item,owner.uuid) for item in rows]
    pairs=list(zip(resources,rows))
    if status:pairs=[pair for pair in pairs if pair[0]["status"]==status]
    if authored:pairs=[pair for pair in pairs if matches_fhir_date(pair[1].ordered_at,authored)]
    audit(db,user,"ServiceRequest",owner.uuid,search=True);return bundle("ServiceRequest",[pair[0] for pair in pairs])


@router.get("/ServiceRequest/{resource_uuid}")
def read_service_request(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    item=db.scalar(select(LabOrder).where(LabOrder.uuid==resource_uuid))
    if not item:fhir_not_found("ServiceRequest")
    resource=service_request_resource(db,item);audit(db,user,"ServiceRequest",item.uuid);return resource


@router.get("/DiagnosticReport")
def search_diagnostic_reports(patient:str=Query(),status:str|None=None,code:str|None=None,date_value:str|None=Query(default=None,alias="date"),db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    owner=patient_or_404(db,patient_reference(patient));query=select(LabOrder).join(LabResult).where(LabOrder.patient_id==owner.id).distinct()
    if code:query=query.where(LabOrder.code==code.rsplit("|",1)[-1])
    rows=list(db.scalars(query.order_by(LabOrder.ordered_at.desc())));resources=[diagnostic_report_resource(db,item,owner.uuid) for item in rows];pairs=list(zip(resources,rows))
    if status:pairs=[pair for pair in pairs if pair[0]["status"]==status]
    if date_value:pairs=[pair for pair in pairs if matches_fhir_date(max((result.observed_at for result in db.scalars(select(LabResult).where(LabResult.order_id==pair[1].id))),default=pair[1].ordered_at),date_value)]
    audit(db,user,"DiagnosticReport",owner.uuid,search=True);return bundle("DiagnosticReport",[pair[0] for pair in pairs])


@router.get("/DiagnosticReport/{resource_uuid}")
def read_diagnostic_report(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    item=db.scalar(select(LabOrder).where(LabOrder.uuid==resource_uuid))
    if not item or not db.scalar(select(LabResult.id).where(LabResult.order_id==item.id).limit(1)):fhir_not_found("DiagnosticReport")
    resource=diagnostic_report_resource(db,item);audit(db,user,"DiagnosticReport",item.uuid);return resource


QUESTIONNAIRE_LOINC={"PHQ-9":"44249-1","GAD-7":"69737-5"}


def questionnaire_resource(item: QuestionnaireDefinition) -> dict:
    questions=[]
    for question in item.questions:
        questions.append({"linkId":question["id"],"text":question["text"],"type":"integer","required":True,"extension":[{"url":"http://hl7.org/fhir/StructureDefinition/minValue","valueInteger":question.get("min",0)},{"url":"http://hl7.org/fhir/StructureDefinition/maxValue","valueInteger":question.get("max",3)}]})
    return {"resourceType":"Questionnaire","id":item.uuid,"url":f"https://openrm.org/fhir/Questionnaire/{item.uuid}","version":item.version,"name":item.code.replace("-",""),"title":item.title,"status":"active" if item.active else "retired","subjectType":["Patient"],"code":[{"system":"http://loinc.org","code":QUESTIONNAIRE_LOINC.get(item.code,item.code),"display":item.title}],"item":questions}


def questionnaire_response_resource(db: Session, item: QuestionnaireResponse, definition: QuestionnaireDefinition, patient_uuid: str) -> dict:
    encounter_uuid=db.scalar(select(Encounter.uuid).where(Encounter.id==item.encounter_id)) if item.encounter_id else None;author=db.get(User,item.author_id)
    question_text={question["id"]:question["text"] for question in definition.questions}
    answers=[{"linkId":link_id,"text":question_text.get(link_id,link_id),"answer":[{"valueInteger":value}]} for link_id,value in item.answers.items()]
    return {"resourceType":"QuestionnaireResponse","id":item.uuid,"meta":{"profile":["http://hl7.org/fhir/us/core/StructureDefinition/us-core-questionnaireresponse"]},"questionnaire":f"https://openrm.org/fhir/Questionnaire/{definition.uuid}|{definition.version}","status":"completed","subject":{"reference":f"Patient/{patient_uuid}"},"authored":item.authored_at.isoformat(),"item":answers,"extension":[{"url":"https://openrm.org/fhir/StructureDefinition/questionnaire-score","valueInteger":item.score},{"url":"https://openrm.org/fhir/StructureDefinition/questionnaire-interpretation","valueString":item.interpretation}],**({"encounter":{"reference":f"Encounter/{encounter_uuid}"}} if encounter_uuid else {}),**({"author":{"display":author.email}} if author else {})}


@router.get("/Questionnaire")
def search_questionnaires(code:str|None=None,title:str|None=None,status:str|None=None,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    query=select(QuestionnaireDefinition)
    if code:
        code_value=code.rsplit("|",1)[-1];matching=[name for name,loinc in QUESTIONNAIRE_LOINC.items() if code_value in {name,loinc}];query=query.where(QuestionnaireDefinition.code.in_(matching or [code_value]))
    if title:query=query.where(QuestionnaireDefinition.title.ilike(f"%{title}%"))
    if status in {"active","retired"}:query=query.where(QuestionnaireDefinition.active.is_(status=="active"))
    rows=list(db.scalars(query.order_by(QuestionnaireDefinition.code,QuestionnaireDefinition.version)));audit(db,user,"Questionnaire",search=True);return bundle("Questionnaire",[questionnaire_resource(item) for item in rows])


@router.get("/Questionnaire/{resource_uuid}")
def read_questionnaire(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    item=db.scalar(select(QuestionnaireDefinition).where(QuestionnaireDefinition.uuid==resource_uuid))
    if not item:fhir_not_found("Questionnaire")
    audit(db,user,"Questionnaire",item.uuid);return questionnaire_resource(item)


@router.get("/QuestionnaireResponse")
def search_questionnaire_responses(patient:str=Query(),questionnaire:str|None=None,authored:str|None=None,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    owner=patient_or_404(db,patient_reference(patient));query=select(QuestionnaireResponse,QuestionnaireDefinition).join(QuestionnaireDefinition).where(QuestionnaireResponse.patient_id==owner.id)
    if questionnaire:
        questionnaire_uuid=questionnaire.split("|",1)[0].rstrip("/").rsplit("/",1)[-1];query=query.where(QuestionnaireDefinition.uuid==questionnaire_uuid)
    rows=db.execute(query.order_by(QuestionnaireResponse.authored_at.desc())).all();pairs=[(questionnaire_response_resource(db,item,definition,owner.uuid),item) for item,definition in rows]
    if authored:pairs=[pair for pair in pairs if matches_fhir_date(pair[1].authored_at,authored)]
    audit(db,user,"QuestionnaireResponse",owner.uuid,search=True);return bundle("QuestionnaireResponse",[pair[0] for pair in pairs])


@router.get("/QuestionnaireResponse/{resource_uuid}")
def read_questionnaire_response(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    row=db.execute(select(QuestionnaireResponse,QuestionnaireDefinition,Patient.uuid).join(QuestionnaireDefinition,QuestionnaireResponse.questionnaire_id==QuestionnaireDefinition.id).join(Patient,QuestionnaireResponse.patient_id==Patient.id).where(QuestionnaireResponse.uuid==resource_uuid)).first()
    if not row:fhir_not_found("QuestionnaireResponse")
    item,definition,patient_uuid=row;resource=questionnaire_response_resource(db,item,definition,patient_uuid);audit(db,user,"QuestionnaireResponse",item.uuid);return resource


def fhir_gender(value: str | None) -> str | None:
    normalized=(value or "").lower();return normalized if normalized in {"male","female","other","unknown"} else None


def related_person_resource(item: PatientRelatedPerson, patient_uuid: str) -> dict:
    telecom=[{"system":system,"value":value} for system,value in (("phone",item.phone),("email",item.email)) if value]
    address={key:value for key,value in (("line",[item.address_line1] if item.address_line1 else None),("city",item.city),("state",item.state),("postalCode",item.postal_code),("country",item.country)) if value}
    extensions=[{"url":"https://openrm.org/fhir/StructureDefinition/related-person-role","valueCode":item.role_code},{"url":"https://openrm.org/fhir/StructureDefinition/primary-contact","valueBoolean":item.is_primary_contact},{"url":"https://openrm.org/fhir/StructureDefinition/emergency-contact","valueBoolean":item.is_emergency_contact},{"url":"https://openrm.org/fhir/StructureDefinition/can-make-medical-decisions","valueBoolean":item.can_make_medical_decisions},{"url":"https://openrm.org/fhir/StructureDefinition/can-receive-medical-information","valueBoolean":item.can_receive_medical_info}]
    gender=fhir_gender(item.sex)
    return {"resourceType":"RelatedPerson","id":item.uuid,"meta":{"profile":["http://hl7.org/fhir/us/core/StructureDefinition/us-core-relatedperson"]},"active":item.active,"patient":{"reference":f"Patient/{patient_uuid}"},"relationship":[{"coding":[{"system":"http://terminology.hl7.org/CodeSystem/v3-RoleCode","code":item.relationship_code}],"text":item.relationship_code}],"name":[{"family":item.last_name,"given":[value for value in (item.first_name,item.middle_name) if value]}],"extension":extensions,**({"telecom":telecom} if telecom else {}),**({"gender":gender} if gender else {}),**({"address":[address]} if address else {}),**({"period":{key:value.isoformat() for key,value in (("start",item.starts_at),("end",item.ends_at)) if value}} if item.starts_at or item.ends_at else {})}


def person_resource(item: Practitioner) -> dict:
    telecom=[{"system":system,"value":value} for system,value in (("phone",item.phone),("email",item.email)) if value]
    return {"resourceType":"Person","id":item.uuid,"active":item.active,"name":[{"family":item.last_name,"given":[value for value in (item.first_name,item.middle_name) if value],**({"prefix":[item.title]} if item.title else {})}],"link":[{"target":{"reference":f"Practitioner/{item.uuid}"},"assurance":"level4"}],**({"identifier":[{"system":"http://hl7.org/fhir/sid/us-npi","value":item.npi}]} if item.npi else {}),**({"telecom":telecom} if telecom else {})}


@router.get("/RelatedPerson")
def search_related_people(patient:str=Query(),name:str|None=None,relationship:str|None=None,active:bool|None=None,db:Session=Depends(get_db),user:User=Depends(patient_demographics_user)):
    owner=patient_or_404(db,patient_reference(patient));query=select(PatientRelatedPerson).where(PatientRelatedPerson.patient_id==owner.id)
    if name:query=query.where(or_(PatientRelatedPerson.first_name.ilike(f"%{name}%"),PatientRelatedPerson.last_name.ilike(f"%{name}%")))
    if relationship:query=query.where(PatientRelatedPerson.relationship_code==relationship.rsplit("|",1)[-1])
    if active is not None:query=query.where(PatientRelatedPerson.active.is_(active))
    rows=list(db.scalars(query.order_by(PatientRelatedPerson.priority,PatientRelatedPerson.last_name)));audit(db,user,"RelatedPerson",owner.uuid,search=True);return bundle("RelatedPerson",[related_person_resource(item,owner.uuid) for item in rows])


@router.get("/RelatedPerson/{resource_uuid}")
def read_related_person(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(patient_demographics_user)):
    row=db.execute(select(PatientRelatedPerson,Patient.uuid).join(Patient,PatientRelatedPerson.patient_id==Patient.id).where(PatientRelatedPerson.uuid==resource_uuid)).first()
    if not row:fhir_not_found("RelatedPerson")
    item,patient_uuid=row;resource=related_person_resource(item,patient_uuid);audit(db,user,"RelatedPerson",item.uuid);return resource


@router.get("/Person")
def search_people(name:str|None=None,identifier:str|None=None,active:bool|None=None,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    query=select(Practitioner)
    if name:query=query.where(or_(Practitioner.first_name.ilike(f"%{name}%"),Practitioner.last_name.ilike(f"%{name}%")))
    if identifier:query=query.where(Practitioner.npi==identifier.rsplit("|",1)[-1])
    if active is not None:query=query.where(Practitioner.active.is_(active))
    rows=list(db.scalars(query.order_by(Practitioner.last_name,Practitioner.first_name).limit(100)));audit(db,user,"Person",search=True);return bundle("Person",[person_resource(item) for item in rows])


@router.get("/Person/{resource_uuid}")
def read_person(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    item=db.scalar(select(Practitioner).where(Practitioner.uuid==resource_uuid))
    if not item:fhir_not_found("Person")
    audit(db,user,"Person",item.uuid);return person_resource(item)
