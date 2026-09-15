"""Compatibility contracts for the legacy OpenEMR Standard and Portal APIs."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Appointment, AuditEvent, ClinicalForm, ClinicalItem, Encounter, Facility, IdentityAuditEvent, Patient, PortalAccount, Practitioner, User, VitalSet
from ..schemas import AppointmentCreate, FacilityCreate, PatientCreate, PractitionerCreate
from ..security import current_portal_account, current_user, user_has_permission
from ..services.patients import patient_by_uuid
from ..services.clinical_forms import ClinicalFormValidationError, validate_clinical_form_content
from ..services.clinical_signatures import encounter_locked, form_locked
from .administration import create_facility, create_practitioner, list_facilities, list_practitioners, update_facility
from .appointments import create_appointment, delete_appointment, get_appointment, list_appointments
from .patients import create_patient, get_patient, replace_patient

router=APIRouter(tags=["OpenEMR compatibility"])


def response(data):
    return {"validationErrors":[],"internalErrors":[],"data":jsonable_encoder(data)}


def default_site(site:str):
    if site!="default":raise HTTPException(status_code=404,detail="Only the default OpenEMR site is configured")


def permission(user:User,section:str,value:str,mode:str="read"):
    if not user_has_permission(user,section,value,mode):raise HTTPException(status_code=403,detail="Permission denied")


def legacy_patient_body(value:dict)->dict:
    aliases={"fname":"first_name","mname":"middle_name","lname":"last_name","DOB":"date_of_birth","postal_code":"postal_code","street":"address_line_1","street_line_2":"address_line_2","country_code":"country_code"}
    result={aliases.get(key,key):item for key,item in value.items()}
    if "sex" not in result:result["sex"]="unknown"
    return result


def legacy_patient(item:Patient)->dict:
    data=jsonable_encoder(item);data.update(fname=item.first_name,mname=item.middle_name,lname=item.last_name,DOB=item.date_of_birth)
    return data


def legacy_appointment_body(value:dict,patient_uuid:str)->dict:
    starts=value.get("starts_at") or value.get("pc_eventDate") or value.get("start")
    if starts and len(str(starts))==10:starts=f"{starts}T{value.get('pc_startTime','00:00:00')}"
    ends=value.get("ends_at") or value.get("end")
    if not ends and starts:
        start=datetime.fromisoformat(str(starts).replace("Z","+00:00"));ends=(start.replace(tzinfo=start.tzinfo or timezone.utc)+timedelta(minutes=30)).isoformat()
    return {"patient_uuid":patient_uuid,"starts_at":starts,"ends_at":ends,"status":value.get("status") or value.get("pc_apptstatus") or "scheduled","title":value.get("title") or value.get("pc_title"),"reason":value.get("reason"),"facility_uuid":value.get("facility_uuid"),"provider_name":value.get("provider_name"),"room":value.get("room")}


def datetime_value(value)->datetime:
    if isinstance(value,datetime):return value
    if value:
        try:return datetime.fromisoformat(str(value).replace("Z","+00:00"))
        except ValueError as error:raise HTTPException(status_code=422,detail="Invalid ISO date-time") from error
    return datetime.now(timezone.utc)


def date_value(value)->date|None:
    if value in (None,""):return None
    if isinstance(value,datetime):return value.date()
    if isinstance(value,date):return value
    try:return date.fromisoformat(str(value)[:10])
    except ValueError as error:raise HTTPException(status_code=422,detail="Invalid ISO date") from error


def encounter_for_patient(db:Session,patient:Patient,encounter_uuid:str)->Encounter:
    item=db.scalar(select(Encounter).where(Encounter.uuid==encounter_uuid,Encounter.patient_id==patient.id))
    if not item:raise HTTPException(status_code=404,detail="Encounter not found")
    return item


@router.get("/apis/{site}/api/version")
def version(site:str,user:User=Depends(current_user)):
    default_site(site);return response({"version":"0.1.0","api":"OpenEMR Standard API compatibility"})


@router.get("/apis/{site}/api/product")
def product(site:str,user:User=Depends(current_user)):
    default_site(site);return response({"name":"OpenRM","api_version":"v1","legacy_contract":"OpenEMR Standard API"})


@router.get("/apis/{site}/api/facility")
def facilities(site:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"admin","users");return response(list_facilities(True,db,user))


@router.get("/apis/{site}/api/facility/{facility_uuid}")
def facility(site:str,facility_uuid:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"admin","users");item=db.scalar(select(Facility).where(Facility.uuid==facility_uuid))
    if not item:raise HTTPException(status_code=404,detail="Facility not found")
    db.add(AuditEvent(actor_id=user.id,action="read",resource_type="facility",resource_id=item.uuid));db.commit();return response(item)


@router.post("/apis/{site}/api/facility",status_code=status.HTTP_201_CREATED)
def facility_create(site:str,body:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"admin","users","write");return response(create_facility(FacilityCreate.model_validate(body),db,user))


@router.put("/apis/{site}/api/facility/{facility_uuid}")
def facility_update(site:str,facility_uuid:str,body:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"admin","users","write");return response(update_facility(facility_uuid,FacilityCreate.model_validate(body),db,user))


@router.get("/apis/{site}/api/patient")
def patients(site:str,q:str|None=None,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"patients","demo");query=select(Patient).where(Patient.merged_at.is_(None))
    if q:query=query.where((Patient.first_name.ilike(f"%{q}%"))|(Patient.last_name.ilike(f"%{q}%")))
    rows=list(db.scalars(query.order_by(Patient.last_name,Patient.first_name).limit(100)));db.add(AuditEvent(actor_id=user.id,action="search",resource_type="patient"));db.commit();return response([legacy_patient(item) for item in rows])


@router.post("/apis/{site}/api/patient",status_code=status.HTTP_201_CREATED)
def patient_create(site:str,body:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"patients","demo","write");item=create_patient(PatientCreate.model_validate(legacy_patient_body(body)),db,user);return response(legacy_patient(item))


@router.get("/apis/{site}/api/patient/{patient_uuid}")
def patient(site:str,patient_uuid:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"patients","demo");return response(legacy_patient(get_patient(patient_uuid,db,user)))


@router.put("/apis/{site}/api/patient/{patient_uuid}")
def patient_update(site:str,patient_uuid:str,body:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"patients","demo","write");item=replace_patient(patient_uuid,PatientCreate.model_validate(legacy_patient_body(body)),db,user);return response(legacy_patient(item))


def encounter_data(db:Session,item:Encounter)->dict:
    patient=db.get(Patient,item.patient_id);return {**jsonable_encoder(item),"patient_uuid":patient.uuid}


@router.get("/apis/{site}/api/patient/{patient_uuid}/encounter")
def encounters(site:str,patient_uuid:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"encounters","auth_a");patient=patient_by_uuid(db,patient_uuid);items=list(db.scalars(select(Encounter).where(Encounter.patient_id==patient.id).order_by(Encounter.occurred_at.desc())));db.add(AuditEvent(actor_id=user.id,action="search",resource_type="encounter",resource_id=patient.uuid));db.commit();return response([encounter_data(db,item) for item in items])


@router.post("/apis/{site}/api/patient/{patient_uuid}/encounter",status_code=status.HTTP_201_CREATED)
def encounter_create(site:str,patient_uuid:str,body:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"encounters","auth_a","write");patient=patient_by_uuid(db,patient_uuid);item=Encounter(patient_id=patient.id,occurred_at=datetime_value(body.get("occurred_at") or body.get("date")),type=body.get("type","ambulatory"),status=body.get("status","open"),chief_complaint=body.get("chief_complaint") or body.get("reason"),clinical_note=body.get("clinical_note"));db.add(item);db.flush();db.add(AuditEvent(actor_id=user.id,action="create",resource_type="encounter",resource_id=item.uuid));db.commit();db.refresh(item);return response(encounter_data(db,item))


@router.get("/apis/{site}/api/patient/{patient_uuid}/encounter/{encounter_uuid}")
def encounter(site:str,patient_uuid:str,encounter_uuid:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"encounters","auth_a");patient=patient_by_uuid(db,patient_uuid);item=db.scalar(select(Encounter).where(Encounter.uuid==encounter_uuid,Encounter.patient_id==patient.id))
    if not item:raise HTTPException(status_code=404,detail="Encounter not found")
    db.add(AuditEvent(actor_id=user.id,action="read",resource_type="encounter",resource_id=item.uuid));db.commit();return response(encounter_data(db,item))


@router.put("/apis/{site}/api/patient/{patient_uuid}/encounter/{encounter_uuid}")
def encounter_update(site:str,patient_uuid:str,encounter_uuid:str,body:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"encounters","auth_a","write");patient=patient_by_uuid(db,patient_uuid);item=db.scalar(select(Encounter).where(Encounter.uuid==encounter_uuid,Encounter.patient_id==patient.id))
    if not item:raise HTTPException(status_code=404,detail="Encounter not found")
    for key in ("occurred_at","type","status","chief_complaint","clinical_note"):
        if key in body:setattr(item,key,datetime_value(body[key]) if key=="occurred_at" else body[key])
    db.add(AuditEvent(actor_id=user.id,action="update",resource_type="encounter",resource_id=item.uuid));db.commit();db.refresh(item);return response(encounter_data(db,item))


@router.get("/apis/{site}/api/practitioner")
def practitioners(site:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"admin","users");return response(list_practitioners(db,user))


@router.get("/apis/{site}/api/practitioner/{practitioner_uuid}")
def practitioner(site:str,practitioner_uuid:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"admin","users");item=db.scalar(select(Practitioner).where(Practitioner.uuid==practitioner_uuid))
    if not item:raise HTTPException(status_code=404,detail="Practitioner not found")
    db.add(AuditEvent(actor_id=user.id,action="read",resource_type="practitioner",resource_id=item.uuid));db.commit();return response(item)


@router.post("/apis/{site}/api/practitioner",status_code=status.HTTP_201_CREATED)
def practitioner_create(site:str,body:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"admin","users","write");normalized={"first_name":body.get("first_name") or body.get("fname"),"middle_name":body.get("middle_name") or body.get("mname"),"last_name":body.get("last_name") or body.get("lname"),**{key:value for key,value in body.items() if key not in {"fname","mname","lname"}}};return response(create_practitioner(PractitionerCreate.model_validate(normalized),db,user))


@router.put("/apis/{site}/api/practitioner/{practitioner_uuid}")
def practitioner_update(site:str,practitioner_uuid:str,body:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"admin","users","write");item=db.scalar(select(Practitioner).where(Practitioner.uuid==practitioner_uuid))
    if not item:raise HTTPException(status_code=404,detail="Practitioner not found")
    normalized={"first_name":body.get("first_name") or body.get("fname"),"middle_name":body.get("middle_name") or body.get("mname"),"last_name":body.get("last_name") or body.get("lname"),**{key:value for key,value in body.items() if key not in {"fname","mname","lname"}}};values=PractitionerCreate.model_validate(normalized).model_dump(exclude={"primary_facility_uuid"})
    for key,value in values.items():setattr(item,key,value)
    db.add(AuditEvent(actor_id=user.id,action="update",resource_type="practitioner",resource_id=item.uuid));db.commit();db.refresh(item);return response(item)


@router.get("/apis/{site}/api/appointment")
def appointments(site:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"patients","appt");return response(list_appointments(patient_uuid=None,starts_from=None,starts_before=None,appointment_status=None,provider_id=None,facility_id=None,limit=100,db=db,user=user))


@router.get("/apis/{site}/api/appointment/{appointment_uuid}")
@router.get("/apis/{site}/api/patient/{patient_uuid}/appointment/{appointment_uuid}")
def appointment(site:str,appointment_uuid:str,patient_uuid:str|None=None,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"patients","appt");item=get_appointment(appointment_uuid,db,user)
    if patient_uuid and item.patient_uuid!=patient_uuid:raise HTTPException(status_code=404,detail="Appointment not found for patient")
    return response(item)


@router.get("/apis/{site}/api/patient/{patient_uuid}/appointment")
def patient_appointments(site:str,patient_uuid:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"patients","appt");return response(list_appointments(patient_uuid=patient_uuid,starts_from=None,starts_before=None,appointment_status=None,provider_id=None,facility_id=None,limit=100,db=db,user=user))


@router.post("/apis/{site}/api/patient/{patient_uuid}/appointment",status_code=status.HTTP_201_CREATED)
def appointment_create(site:str,patient_uuid:str,body:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"patients","appt","write");return response(create_appointment(AppointmentCreate.model_validate(legacy_appointment_body(body,patient_uuid)),db,user))


@router.delete("/apis/{site}/api/patient/{patient_uuid}/appointment/{appointment_uuid}")
def appointment_delete(site:str,patient_uuid:str,appointment_uuid:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"patients","appt","write");item=get_appointment(appointment_uuid,db,user)
    if item.patient_uuid!=patient_uuid:raise HTTPException(status_code=404,detail="Appointment not found for patient")
    delete_appointment(appointment_uuid,db,user);return response([])


def soap_data(item:ClinicalForm)->dict:
    return {**jsonable_encoder(item.content),"uuid":item.uuid,"id":item.uuid,"title":item.title,"status":item.status,"date":jsonable_encoder(item.authored_at)}


def soap_content(body:dict)->dict:
    source=body.get("content") if isinstance(body.get("content"),dict) else body
    content={key:source[key] for key in ("subjective","objective","assessment","plan") if key in source}
    try:return validate_clinical_form_content("soap",content)
    except ClinicalFormValidationError as error:raise HTTPException(status_code=422,detail=str(error)) from error


def vital_data(item:VitalSet)->dict:
    data=jsonable_encoder(item);data.update(id=item.uuid,date=data["observed_at"],bps=data["systolic"],bpd=data["diastolic"],weight=data["weight_kg"],height=data["height_cm"],temperature=data["temperature_c"],pulse=data["heart_rate"],respiration=data["respiratory_rate"])
    return data


VITAL_ALIASES={"date":"observed_at","bps":"systolic","bpd":"diastolic","weight":"weight_kg","height":"height_cm","temperature":"temperature_c","pulse":"heart_rate","respiration":"respiratory_rate"}
VITAL_FIELDS=("observed_at","systolic","diastolic","weight_kg","height_cm","temperature_c","heart_rate","respiratory_rate","oxygen_saturation","note")


def vital_values(body:dict,*,partial:bool=False)->dict:
    normalized={VITAL_ALIASES.get(key,key):value for key,value in body.items()}
    values={key:normalized[key] for key in VITAL_FIELDS if key in normalized}
    if "observed_at" in values:values["observed_at"]=datetime_value(values["observed_at"])
    elif not partial:values["observed_at"]=datetime.now(timezone.utc)
    for key in ("systolic","diastolic","weight_kg","height_cm","temperature_c","heart_rate","respiratory_rate","oxygen_saturation"):
        if key in values:
            try:values[key]=Decimal(str(values[key])) if values[key] not in (None,"") else None
            except Exception as error:raise HTTPException(status_code=422,detail=f"{key} must be numeric") from error
    return values


def set_bmi(item:VitalSet):
    item.bmi=(item.weight_kg/((item.height_cm/Decimal("100"))**2)).quantize(Decimal("0.01")) if item.weight_kg and item.height_cm else None


@router.api_route("/apis/{site}/api/patient/{patient_uuid}/encounter/{encounter_uuid}/{resource}",methods=["GET","POST"])
@router.api_route("/apis/{site}/api/patient/{patient_uuid}/encounter/{encounter_uuid}/{resource}/{item_uuid}",methods=["GET","PUT"])
async def encounter_clinical_resource(site:str,patient_uuid:str,encounter_uuid:str,resource:str,request:Request,item_uuid:str|None=None,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site)
    if resource not in {"soap_note","vital"}:raise HTTPException(status_code=404,detail="Clinical resource not found")
    permission(user,"encounters","notes","write" if request.method in {"POST","PUT"} else "read")
    patient=patient_by_uuid(db,patient_uuid);encounter=encounter_for_patient(db,patient,encounter_uuid)
    if resource=="soap_note":
        query=select(ClinicalForm).where(ClinicalForm.patient_id==patient.id,ClinicalForm.encounter_id==encounter.id,ClinicalForm.form_type=="soap")
        if item_uuid:query=query.where(ClinicalForm.uuid==item_uuid)
        if request.method=="GET":
            if item_uuid:
                item=db.scalar(query)
                if not item:raise HTTPException(status_code=404,detail="SOAP note not found")
                data=soap_data(item)
            else:data=[soap_data(item) for item in db.scalars(query.order_by(ClinicalForm.authored_at.desc()))]
            db.add(AuditEvent(actor_id=user.id,action="read" if item_uuid else "search",resource_type="soap_note",resource_id=item_uuid or patient.uuid));db.commit();return response(data)
        body=await request.json()
        if request.method=="POST":
            if encounter_locked(db,encounter.id):raise HTTPException(status_code=423,detail="Encounter is electronically signed and locked")
            item=ClinicalForm(patient_id=patient.id,encounter_id=encounter.id,author_id=user.id,form_type="soap",title=body.get("title") or "SOAP Note",content=soap_content(body),status=body.get("status") or "draft",authored_at=datetime_value(body.get("authored_at") or body.get("date")))
            db.add(item);action="create"
        else:
            item=db.scalar(query.with_for_update())
            if not item:raise HTTPException(status_code=404,detail="SOAP note not found")
            if form_locked(db,item):raise HTTPException(status_code=423,detail="Clinical form is electronically signed and locked")
            item.content=soap_content(body)
            if "title" in body:item.title=body["title"]
            if "status" in body:item.status=body["status"]
            action="update"
        db.flush();db.add(AuditEvent(actor_id=user.id,action=action,resource_type="soap_note",resource_id=item.uuid));db.commit();db.refresh(item);return response(soap_data(item))
    query=select(VitalSet).where(VitalSet.patient_id==patient.id,VitalSet.encounter_id==encounter.id)
    if item_uuid:query=query.where(VitalSet.uuid==item_uuid)
    if request.method=="GET":
        if item_uuid:
            item=db.scalar(query)
            if not item:raise HTTPException(status_code=404,detail="Vital set not found")
            data=vital_data(item)
        else:data=[vital_data(item) for item in db.scalars(query.order_by(VitalSet.observed_at.desc()))]
        db.add(AuditEvent(actor_id=user.id,action="read" if item_uuid else "search",resource_type="vitals",resource_id=item_uuid or patient.uuid));db.commit();return response(data)
    if encounter_locked(db,encounter.id):raise HTTPException(status_code=423,detail="Encounter is electronically signed and locked")
    body=await request.json()
    if request.method=="POST":
        item=VitalSet(patient_id=patient.id,encounter_id=encounter.id,**vital_values(body));db.add(item);action="create"
    else:
        item=db.scalar(query.with_for_update())
        if not item:raise HTTPException(status_code=404,detail="Vital set not found")
        for key,value in vital_values(body,partial=True).items():setattr(item,key,value)
        action="update"
    set_bmi(item);db.flush();db.add(AuditEvent(actor_id=user.id,action=action,resource_type="vitals",resource_id=item.uuid));db.commit();db.refresh(item);return response(vital_data(item))


CLINICAL_RESOURCES={"medical_problem":"problem","allergy":"allergy","medication":"medication","surgery":"surgery","dental_issue":"dental"}
CLINICAL_FIELDS=("title","code_system","code","status","onset_date","end_date","severity","reaction","dosage","note")


def clinical_item_data(db:Session,item:ClinicalItem)->dict:
    patient=db.get(Patient,item.patient_id);data=jsonable_encoder(item);data.update(id=item.uuid,patient_uuid=patient.uuid,text=item.title)
    return data


def clinical_item_values(body:dict,*,partial:bool=False)->dict:
    normalized=dict(body)
    if "title" not in normalized:
        title=normalized.get("text") or normalized.get("diagnosis") or normalized.get("drug")
        if title is not None:normalized["title"]=title
    values={key:normalized[key] for key in CLINICAL_FIELDS if key in normalized}
    if not partial and not values.get("title"):raise HTTPException(status_code=422,detail="title is required")
    for key in ("onset_date","end_date"):
        if key in values:values[key]=date_value(values[key])
    return values


@router.get("/apis/{site}/api/{resource}")
@router.get("/apis/{site}/api/{resource}/{item_uuid}")
def global_clinical_resource(site:str,resource:str,item_uuid:str|None=None,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site)
    if resource not in {"medical_problem","allergy"}:raise HTTPException(status_code=404,detail="Clinical resource not found")
    permission(user,"patients","med");query=select(ClinicalItem).where(ClinicalItem.category==CLINICAL_RESOURCES[resource],ClinicalItem.status!="entered-in-error")
    if item_uuid:query=query.where(ClinicalItem.uuid==item_uuid)
    if item_uuid:
        item=db.scalar(query)
        if not item:raise HTTPException(status_code=404,detail="Clinical item not found")
        data=clinical_item_data(db,item)
    else:data=[clinical_item_data(db,item) for item in db.scalars(query.order_by(ClinicalItem.created_at.desc()).limit(100))]
    db.add(AuditEvent(actor_id=user.id,action="read" if item_uuid else "search",resource_type=resource,resource_id=item_uuid));db.commit();return response(data)


@router.api_route("/apis/{site}/api/patient/{patient_uuid}/{resource}",methods=["GET","POST"])
@router.api_route("/apis/{site}/api/patient/{patient_uuid}/{resource}/{item_uuid}",methods=["GET","PUT","DELETE"])
async def patient_clinical_resource(site:str,patient_uuid:str,resource:str,request:Request,item_uuid:str|None=None,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site)
    if resource not in CLINICAL_RESOURCES:raise HTTPException(status_code=404,detail="Clinical resource not found")
    permission(user,"patients","med","write" if request.method in {"POST","PUT","DELETE"} else "read")
    patient=patient_by_uuid(db,patient_uuid);category=CLINICAL_RESOURCES[resource];query=select(ClinicalItem).where(ClinicalItem.patient_id==patient.id,ClinicalItem.category==category,ClinicalItem.status!="entered-in-error")
    if item_uuid:query=query.where(ClinicalItem.uuid==item_uuid)
    if request.method=="GET":
        if item_uuid:
            item=db.scalar(query)
            if not item:raise HTTPException(status_code=404,detail="Clinical item not found")
            data=clinical_item_data(db,item)
        else:data=[clinical_item_data(db,item) for item in db.scalars(query.order_by(ClinicalItem.created_at.desc()))]
        db.add(AuditEvent(actor_id=user.id,action="read" if item_uuid else "search",resource_type=resource,resource_id=item_uuid or patient.uuid));db.commit();return response(data)
    if request.method=="DELETE":
        item=db.scalar(query.with_for_update())
        if not item:raise HTTPException(status_code=404,detail="Clinical item not found")
        item.status="entered-in-error";db.add(AuditEvent(actor_id=user.id,action="delete",resource_type=resource,resource_id=item.uuid));db.commit();return response([])
    body=await request.json()
    if request.method=="POST":
        item=ClinicalItem(patient_id=patient.id,category=category,legacy_payload=body,**clinical_item_values(body));db.add(item);action="create"
    else:
        item=db.scalar(query.with_for_update())
        if not item:raise HTTPException(status_code=404,detail="Clinical item not found")
        for key,value in clinical_item_values(body,partial=True).items():setattr(item,key,value)
        item.legacy_payload=body;action="update"
    db.flush();db.add(AuditEvent(actor_id=user.id,action=action,resource_type=resource,resource_id=item.uuid));db.commit();db.refresh(item);return response(clinical_item_data(db,item))


def portal_patient(db:Session,account:PortalAccount)->Patient:
    if account.force_password_reset:raise HTTPException(status_code=403,detail="Password reset required")
    patient=db.get(Patient,account.patient_id) if account.patient_id else None
    if not patient or not patient.portal_allowed:raise HTTPException(status_code=403,detail="A self patient portal identity is required")
    return patient


@router.get("/apis/{site}/portal/patient")
def portal_patient_get(site:str,db:Session=Depends(get_db),account:PortalAccount=Depends(current_portal_account)):
    default_site(site);patient=portal_patient(db,account);db.add(IdentityAuditEvent(identity_kind="portal",portal_account_id=account.id,patient_id=patient.id,action="read",resource_type="patient",resource_id=patient.uuid));db.commit();return response(legacy_patient(patient))


@router.get("/apis/{site}/portal/patient/encounter")
def portal_encounters(site:str,db:Session=Depends(get_db),account:PortalAccount=Depends(current_portal_account)):
    default_site(site);patient=portal_patient(db,account);items=list(db.scalars(select(Encounter).where(Encounter.patient_id==patient.id).order_by(Encounter.occurred_at.desc())));db.add(IdentityAuditEvent(identity_kind="portal",portal_account_id=account.id,patient_id=patient.id,action="search",resource_type="encounter"));db.commit();return response([encounter_data(db,item) for item in items])


@router.get("/apis/{site}/portal/patient/encounter/{encounter_uuid}")
def portal_encounter(site:str,encounter_uuid:str,db:Session=Depends(get_db),account:PortalAccount=Depends(current_portal_account)):
    default_site(site);patient=portal_patient(db,account);item=db.scalar(select(Encounter).where(Encounter.uuid==encounter_uuid,Encounter.patient_id==patient.id))
    if not item:raise HTTPException(status_code=404,detail="Encounter not found")
    db.add(IdentityAuditEvent(identity_kind="portal",portal_account_id=account.id,patient_id=patient.id,action="read",resource_type="encounter",resource_id=item.uuid));db.commit();return response(encounter_data(db,item))


@router.get("/apis/{site}/portal/patient/appointment")
def portal_appointments(site:str,db:Session=Depends(get_db),account:PortalAccount=Depends(current_portal_account)):
    default_site(site);patient=portal_patient(db,account);items=list(db.scalars(select(Appointment).where(Appointment.patient_id==patient.id).order_by(Appointment.starts_at)));db.add(IdentityAuditEvent(identity_kind="portal",portal_account_id=account.id,patient_id=patient.id,action="search",resource_type="appointment"));db.commit();return response(items)


@router.get("/apis/{site}/portal/patient/appointment/{appointment_uuid}")
def portal_appointment(site:str,appointment_uuid:str,db:Session=Depends(get_db),account:PortalAccount=Depends(current_portal_account)):
    default_site(site);patient=portal_patient(db,account);item=db.scalar(select(Appointment).where(Appointment.uuid==appointment_uuid,Appointment.patient_id==patient.id))
    if not item:raise HTTPException(status_code=404,detail="Appointment not found")
    db.add(IdentityAuditEvent(identity_kind="portal",portal_account_id=account.id,patient_id=patient.id,action="read",resource_type="appointment",resource_id=item.uuid));db.commit();return response(item)
