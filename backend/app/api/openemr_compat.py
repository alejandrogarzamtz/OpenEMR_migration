"""Compatibility contracts for the legacy OpenEMR Standard and Portal APIs."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from hashlib import sha256

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Appointment, AuditEvent, BackgroundService, ClinicalForm, ClinicalItem, Coverage, Document, Encounter, ExternalProcedure, Facility, IdentityAuditEvent, Immunization, InsuranceType, InventoryProduct, MessageThread, Patient, PatientEmployment, PatientTransaction, Payer, PortalAccount, Practitioner, Prescription, ReferenceOption, SecureMessage, User, VitalSet
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


def user_data(item:User)->dict:
    return {"uuid":item.uuid,"username":item.username,"email":item.email,"role":item.role,"active":item.active}


def payer_data(item:Payer)->dict:
    data=dict(item.legacy_payload or {});data.update(uuid=item.uuid,id=item.uuid,name=item.name,x12_receiver_id=item.payer_identifier,inactive=0 if item.active else 1)
    return data


@router.get("/apis/{site}/api/list/{list_name}")
def reference_list(site:str,list_name:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"lists","default");items=list(db.scalars(select(ReferenceOption).where(ReferenceOption.list_id==list_name).order_by(ReferenceOption.sequence,ReferenceOption.option_id)))
    data=[]
    for item in items:
        value=dict(item.legacy_payload or {});value.update(uuid=item.uuid,list_id=item.list_id,option_id=item.option_id,title=item.title,seq=item.sequence,activity=1 if item.active else 0);data.append(value)
    db.add(AuditEvent(actor_id=user.id,action="search",resource_type="reference_option",resource_id=list_name));db.commit();return response(data)


@router.get("/apis/{site}/api/user")
def users(site:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"admin","users");items=list(db.scalars(select(User).order_by(User.email)));db.add(AuditEvent(actor_id=user.id,action="search",resource_type="user"));db.commit();return response([user_data(item) for item in items])


@router.get("/apis/{site}/api/user/{user_uuid}")
def user_get(site:str,user_uuid:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"admin","users");item=db.scalar(select(User).where(User.uuid==user_uuid))
    if not item:raise HTTPException(status_code=404,detail="User not found")
    db.add(AuditEvent(actor_id=user.id,action="read",resource_type="user",resource_id=item.uuid));db.commit();return response(user_data(item))


@router.get("/apis/{site}/api/insurance_type")
def insurance_types(site:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"acct","bill");items=list(db.scalars(select(InsuranceType).order_by(InsuranceType.legacy_type_id)));db.add(AuditEvent(actor_id=user.id,action="search",resource_type="insurance_type"));db.commit();return response([{"id":item.legacy_type_id,"type":item.name,"claim_type":item.claim_type} for item in items])


@router.get("/apis/{site}/api/insurance_company")
def insurance_companies(site:str,name:str|None=None,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"acct","bill");query=select(Payer)
    if name:query=query.where(Payer.name.ilike(f"%{name}%"))
    items=list(db.scalars(query.order_by(Payer.name)));db.add(AuditEvent(actor_id=user.id,action="search",resource_type="insurance_company"));db.commit();return response([payer_data(item) for item in items])


def payer_by_identifier(db:Session,value:str)->Payer:
    item=db.scalar(select(Payer).where(Payer.uuid==value))
    if not item and value.isdigit():item=db.scalar(select(Payer).where(Payer.legacy_payer_id==int(value)))
    if not item:raise HTTPException(status_code=404,detail="Insurance company not found")
    return item


@router.get("/apis/{site}/api/insurance_company/{payer_id}")
def insurance_company(site:str,payer_id:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"acct","bill");item=payer_by_identifier(db,payer_id);db.add(AuditEvent(actor_id=user.id,action="read",resource_type="insurance_company",resource_id=item.uuid));db.commit();return response(payer_data(item))


@router.post("/apis/{site}/api/insurance_company",status_code=status.HTTP_201_CREATED)
def insurance_company_create(site:str,body:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"acct","bill","write")
    if not str(body.get("name") or "").strip():raise HTTPException(status_code=422,detail="name is required")
    item=Payer(name=str(body["name"]).strip(),payer_identifier=body.get("x12_receiver_id") or body.get("cms_id"),active=not bool(body.get("inactive",False)),legacy_payload=body);db.add(item);db.flush();db.add(AuditEvent(actor_id=user.id,action="create",resource_type="insurance_company",resource_id=item.uuid));db.commit();db.refresh(item);return response(payer_data(item))


@router.put("/apis/{site}/api/insurance_company/{payer_id}")
def insurance_company_update(site:str,payer_id:str,body:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"acct","bill","write");item=payer_by_identifier(db,payer_id)
    if "name" in body:
        if not str(body["name"]).strip():raise HTTPException(status_code=422,detail="name is required")
        item.name=str(body["name"]).strip()
    if "x12_receiver_id" in body or "cms_id" in body:item.payer_identifier=body.get("x12_receiver_id") or body.get("cms_id")
    if "inactive" in body:item.active=not bool(body["inactive"])
    item.legacy_payload={**(item.legacy_payload or {}),**body};db.add(AuditEvent(actor_id=user.id,action="update",resource_type="insurance_company",resource_id=item.uuid));db.commit();db.refresh(item);return response(payer_data(item))


def document_data(item:Document)->dict:
    return {"uuid":item.uuid,"id":item.uuid,"name":item.name,"mimetype":item.mime_type,"mime_type":item.mime_type,"hash":item.sha256,"date":jsonable_encoder(item.uploaded_at)}


@router.post("/apis/{site}/api/patient/{patient_uuid}/document",status_code=status.HTTP_201_CREATED)
async def document_create(site:str,patient_uuid:str,document:UploadFile=File(...),eid:str|None=None,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"patients","docs","write");patient=patient_by_uuid(db,patient_uuid);encounter=encounter_for_patient(db,patient,eid) if eid else None;content=await document.read(10*1024*1024+1)
    if not content:raise HTTPException(status_code=422,detail="Document is empty")
    if len(content)>10*1024*1024:raise HTTPException(status_code=413,detail="Document exceeds 10 MiB limit")
    item=Document(patient_id=patient.id,encounter_id=encounter.id if encounter else None,name=document.filename or "document",mime_type=document.content_type or "application/octet-stream",content=content,sha256=sha256(content).hexdigest());db.add(item);db.flush();db.add(AuditEvent(actor_id=user.id,action="create",resource_type="document",resource_id=item.uuid));db.commit();db.refresh(item);return response(document_data(item))


@router.get("/apis/{site}/api/patient/{patient_uuid}/document")
def documents(site:str,patient_uuid:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"patients","docs");patient=patient_by_uuid(db,patient_uuid);items=list(db.scalars(select(Document).where(Document.patient_id==patient.id).order_by(Document.uploaded_at.desc())));db.add(AuditEvent(actor_id=user.id,action="search",resource_type="document",resource_id=patient.uuid));db.commit();return response([document_data(item) for item in items])


@router.get("/apis/{site}/api/patient/{patient_uuid}/document/{document_uuid}")
def document_download(site:str,patient_uuid:str,document_uuid:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"patients","docs");patient=patient_by_uuid(db,patient_uuid);item=db.scalar(select(Document).where(Document.uuid==document_uuid,Document.patient_id==patient.id))
    if not item:raise HTTPException(status_code=404,detail="Document not found")
    db.add(AuditEvent(actor_id=user.id,action="read",resource_type="document",resource_id=item.uuid));db.commit();safe=item.name.replace('"',"");return Response(item.content,media_type=item.mime_type,headers={"Content-Disposition":f'attachment; filename="{safe}"',"ETag":item.sha256})


@router.get("/apis/{site}/api/patient/{patient_uuid}/employer")
def employers(site:str,patient_uuid:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"patients","demo");patient=patient_by_uuid(db,patient_uuid);items=list(db.scalars(select(PatientEmployment).where(PatientEmployment.patient_id==patient.id).order_by(PatientEmployment.active.desc(),PatientEmployment.created_at.desc())));db.add(AuditEvent(actor_id=user.id,action="read",resource_type="patient_employment",resource_id=patient.uuid));db.commit();return response(items)


def coverage_data(db:Session,item:Coverage)->dict:
    payer=db.get(Payer,item.payer_id);data=dict(item.legacy_payload or {});data.update(uuid=item.uuid,id=item.uuid,type=item.priority,priority=item.priority,provider=payer.uuid,payer_name=payer.name,payer_identifier=payer.payer_identifier,plan_name=item.plan_name,policy_number=item.policy_number,group_number=item.group_number,subscriber_name=item.subscriber_name,subscriber_relationship=item.relationship,date=jsonable_encoder(item.starts_on),date_end=jsonable_encoder(item.ends_on));return data


def coverage_values(db:Session,body:dict,existing:Coverage|None=None)->tuple[Payer,dict]:
    payer=None;provider=body.get("provider")
    if provider:payer=payer_by_identifier(db,str(provider))
    payer_name=body.get("payer_name") or body.get("provider_name")
    if not payer and payer_name:payer=db.scalar(select(Payer).where(Payer.name==payer_name))
    if not payer and payer_name:payer=Payer(name=payer_name,payer_identifier=body.get("payer_identifier"));db.add(payer);db.flush()
    if not payer and existing:payer=db.get(Payer,existing.payer_id)
    if not payer:raise HTTPException(status_code=422,detail="provider or payer_name is required")
    aliases={"type":"priority","subscriber_relationship":"relationship","date":"starts_on","date_end":"ends_on"};normalized={aliases.get(key,key):value for key,value in body.items()};fields=("priority","plan_name","policy_number","group_number","subscriber_name","relationship","starts_on","ends_on");values={key:normalized[key] for key in fields if key in normalized}
    for key in ("starts_on","ends_on"):
        if key in values:values[key]=date_value(values[key])
    if not existing:
        values.setdefault("priority","primary")
        for required in ("policy_number","subscriber_name"):
            if not values.get(required):raise HTTPException(status_code=422,detail=f"{required} is required")
        values.setdefault("relationship","self")
    return payer,values


@router.get("/apis/{site}/api/patient/{patient_uuid}/insurance")
def coverages(site:str,patient_uuid:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"patients","demo");patient=patient_by_uuid(db,patient_uuid);items=list(db.scalars(select(Coverage).where(Coverage.patient_id==patient.id).order_by(Coverage.priority)));db.add(AuditEvent(actor_id=user.id,action="search",resource_type="coverage",resource_id=patient.uuid));db.commit();return response([coverage_data(db,item) for item in items])


@router.get("/apis/{site}/api/patient/{patient_uuid}/insurance/$swap-insurance")
def coverage_swap(site:str,patient_uuid:str,type:str,uuid:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"patients","demo","write");patient=patient_by_uuid(db,patient_uuid);source=db.scalar(select(Coverage).where(Coverage.uuid==uuid,Coverage.patient_id==patient.id).with_for_update())
    if not source:raise HTTPException(status_code=404,detail="Coverage not found")
    target=db.scalar(select(Coverage).where(Coverage.patient_id==patient.id,Coverage.priority==type,Coverage.id!=source.id).with_for_update());old=source.priority;source.priority=type
    if target:target.priority=old
    db.add(AuditEvent(actor_id=user.id,action="swap",resource_type="coverage",resource_id=source.uuid,detail=f"priority={type}"));db.commit();db.refresh(source);return response(coverage_data(db,source))


@router.get("/apis/{site}/api/patient/{patient_uuid}/insurance/{coverage_uuid}")
def coverage_get(site:str,patient_uuid:str,coverage_uuid:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"patients","demo");patient=patient_by_uuid(db,patient_uuid);item=db.scalar(select(Coverage).where(Coverage.uuid==coverage_uuid,Coverage.patient_id==patient.id))
    if not item:raise HTTPException(status_code=404,detail="Coverage not found")
    db.add(AuditEvent(actor_id=user.id,action="read",resource_type="coverage",resource_id=item.uuid));db.commit();return response(coverage_data(db,item))


@router.post("/apis/{site}/api/patient/{patient_uuid}/insurance",status_code=status.HTTP_201_CREATED)
def coverage_create(site:str,patient_uuid:str,body:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"patients","demo","write");patient=patient_by_uuid(db,patient_uuid);payer,values=coverage_values(db,body);item=Coverage(patient_id=patient.id,payer_id=payer.id,legacy_payload=body,**values);db.add(item);db.flush();db.add(AuditEvent(actor_id=user.id,action="create",resource_type="coverage",resource_id=item.uuid));db.commit();db.refresh(item);return response(coverage_data(db,item))


@router.put("/apis/{site}/api/patient/{patient_uuid}/insurance/{coverage_uuid}")
def coverage_update(site:str,patient_uuid:str,coverage_uuid:str,body:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"patients","demo","write");patient=patient_by_uuid(db,patient_uuid);item=db.scalar(select(Coverage).where(Coverage.uuid==coverage_uuid,Coverage.patient_id==patient.id).with_for_update())
    if not item:raise HTTPException(status_code=404,detail="Coverage not found")
    payer,values=coverage_values(db,body,item);item.payer_id=payer.id
    for key,value in values.items():setattr(item,key,value)
    item.legacy_payload={**(item.legacy_payload or {}),**body};db.add(AuditEvent(actor_id=user.id,action="update",resource_type="coverage",resource_id=item.uuid));db.commit();db.refresh(item);return response(coverage_data(db,item))


def message_data(item:SecureMessage,thread:MessageThread)->dict:
    return {"uuid":item.uuid,"id":item.uuid,"thread_uuid":thread.uuid,"subject":thread.subject,"body":item.body,"status":thread.status,"date":jsonable_encoder(item.created_at)}


@router.post("/apis/{site}/api/patient/{patient_uuid}/message",status_code=status.HTTP_201_CREATED)
def message_create(site:str,patient_uuid:str,body:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"patients","notes","write");patient=patient_by_uuid(db,patient_uuid);text=str(body.get("body") or body.get("message") or "").strip()
    if not text:raise HTTPException(status_code=422,detail="body is required")
    thread=MessageThread(patient_id=patient.id,subject=str(body.get("subject") or "Clinical message")[:255],assigned_user_id=user.id,legacy_payload=body);db.add(thread);db.flush();item=SecureMessage(thread_id=thread.id,sender_kind="staff",sender_user_id=user.id,sender_name=user.email,body=text,read_by_staff_at=datetime.now(timezone.utc),legacy_payload=body);db.add(item);db.flush();db.add(AuditEvent(actor_id=user.id,action="create",resource_type="secure_message",resource_id=item.uuid));db.commit();db.refresh(item);return response(message_data(item,thread))


def message_for_patient(db:Session,patient:Patient,message_uuid:str)->tuple[SecureMessage,MessageThread]:
    row=db.execute(select(SecureMessage,MessageThread).join(MessageThread).where(SecureMessage.uuid==message_uuid,MessageThread.patient_id==patient.id,SecureMessage.deleted_at.is_(None))).first()
    if not row:raise HTTPException(status_code=404,detail="Message not found")
    return row


@router.put("/apis/{site}/api/patient/{patient_uuid}/message/{message_uuid}")
def message_update(site:str,patient_uuid:str,message_uuid:str,body:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"patients","notes","write");patient=patient_by_uuid(db,patient_uuid);item,thread=message_for_patient(db,patient,message_uuid);text=str(body.get("body") or body.get("message") or "").strip()
    if text:item.body=text
    if body.get("subject"):thread.subject=str(body["subject"])[:255]
    item.legacy_payload={**(item.legacy_payload or {}),**body};thread.updated_at=datetime.now(timezone.utc);db.add(AuditEvent(actor_id=user.id,action="update",resource_type="secure_message",resource_id=item.uuid));db.commit();db.refresh(item);return response(message_data(item,thread))


@router.delete("/apis/{site}/api/patient/{patient_uuid}/message/{message_uuid}")
def message_delete(site:str,patient_uuid:str,message_uuid:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"patients","notes","write");patient=patient_by_uuid(db,patient_uuid);item,thread=message_for_patient(db,patient,message_uuid);item.deleted_at=datetime.now(timezone.utc);thread.status="closed";thread.updated_at=item.deleted_at;db.add(AuditEvent(actor_id=user.id,action="delete",resource_type="secure_message",resource_id=item.uuid));db.commit();return response([])


def transaction_data(item:PatientTransaction)->dict:
    data=dict(item.legacy_payload or {});data.update(uuid=item.uuid,id=item.uuid,title=item.title,date=jsonable_encoder(item.occurred_at),body=item.body,status=item.status);return data


@router.get("/apis/{site}/api/patient/{patient_uuid}/transaction")
def transactions(site:str,patient_uuid:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"patients","trans");patient=patient_by_uuid(db,patient_uuid);items=list(db.scalars(select(PatientTransaction).where(PatientTransaction.patient_id==patient.id).order_by(PatientTransaction.occurred_at.desc())));db.add(AuditEvent(actor_id=user.id,action="search",resource_type="patient_transaction",resource_id=patient.uuid));db.commit();return response([transaction_data(item) for item in items])


@router.post("/apis/{site}/api/patient/{patient_uuid}/transaction",status_code=status.HTTP_201_CREATED)
def transaction_create(site:str,patient_uuid:str,body:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"patients","trans","write");patient=patient_by_uuid(db,patient_uuid);item=PatientTransaction(patient_id=patient.id,title=str(body.get("title") or "Transaction")[:255],occurred_at=datetime_value(body.get("date")),body=body.get("body"),status=body.get("status") or "active",legacy_payload=body);db.add(item);db.flush();db.add(AuditEvent(actor_id=user.id,action="create",resource_type="patient_transaction",resource_id=item.uuid));db.commit();db.refresh(item);return response(transaction_data(item))


@router.put("/apis/{site}/api/transaction/{transaction_uuid}")
def transaction_update(site:str,transaction_uuid:str,body:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"patients","trans","write");item=db.scalar(select(PatientTransaction).where(PatientTransaction.uuid==transaction_uuid).with_for_update())
    if not item:raise HTTPException(status_code=404,detail="Transaction not found")
    for key in ("title","body","status"):
        if key in body:setattr(item,key,body[key])
    if "date" in body:item.occurred_at=datetime_value(body["date"])
    item.legacy_payload={**(item.legacy_payload or {}),**body};db.add(AuditEvent(actor_id=user.id,action="update",resource_type="patient_transaction",resource_id=item.uuid));db.commit();db.refresh(item);return response(transaction_data(item))


def patient_from_body(db:Session,body:dict)->Patient:
    value=str(body.get("patient_uuid") or body.get("puuid") or body.get("patient_id") or "")
    item=db.scalar(select(Patient).where(Patient.uuid==value))
    if not item and value.isdigit():item=db.scalar(select(Patient).where(Patient.legacy_pid==int(value)))
    if not item:raise HTTPException(status_code=422,detail="A valid patient_uuid is required")
    return item


def prescription_data(db:Session,item:Prescription)->dict:
    patient=db.get(Patient,item.patient_id) if item.patient_id else None;data=jsonable_encoder(item);data.update(id=item.uuid,patient_uuid=patient.uuid if patient else None,drug=item.drug_name,date=data.get("prescribed_at"));return data


@router.post("/apis/{site}/api/prescription",status_code=status.HTTP_201_CREATED)
def prescription_create_compat(site:str,body:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"patients","med","write");patient=patient_from_body(db,body);drug=str(body.get("drug_name") or body.get("drug") or body.get("title") or "").strip();instructions=str(body.get("dosage_instructions") or body.get("dosage") or "").strip()
    if not drug or not instructions:raise HTTPException(status_code=422,detail="drug_name and dosage_instructions are required")
    item=Prescription(patient_id=patient.id,prescribed_at=datetime_value(body.get("prescribed_at") or body.get("date")),drug_name=drug,dosage_instructions=instructions,rxnorm_code=body.get("rxnorm_code"),quantity=body.get("quantity"),refills=int(body.get("refills") or 0),substitutions_allowed=bool(body.get("substitutions_allowed",True)),status=body.get("status") or "active",legacy_payload=body);db.add(item);db.flush();db.add(AuditEvent(actor_id=user.id,action="create",resource_type="prescription",resource_id=item.uuid));db.commit();db.refresh(item);return response(prescription_data(db,item))


@router.delete("/apis/{site}/api/prescription/{prescription_uuid}")
def prescription_delete_compat(site:str,prescription_uuid:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"patients","med","write");item=db.scalar(select(Prescription).where(Prescription.uuid==prescription_uuid).with_for_update())
    if not item:raise HTTPException(status_code=404,detail="Prescription not found")
    item.status="entered-in-error";db.add(AuditEvent(actor_id=user.id,action="delete",resource_type="prescription",resource_id=item.uuid));db.commit();return response([])


def background_data(item:BackgroundService)->dict:
    return {"name":item.name,"title":item.title,"active":item.active,"running":item.running_state,"next_run":jsonable_encoder(item.next_run),"execute_interval":item.execute_interval_minutes,"function":item.handler,"sort_order":item.sort_order}


@router.get("/apis/{site}/api/background_service")
def background_services(site:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"admin","super");items=list(db.scalars(select(BackgroundService).order_by(BackgroundService.sort_order,BackgroundService.name)));db.add(AuditEvent(actor_id=user.id,action="search",resource_type="background_service"));db.commit();return response([background_data(item) for item in items])


@router.get("/apis/{site}/api/background_service/{name}")
def background_service(site:str,name:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"admin","super");item=db.scalar(select(BackgroundService).where(BackgroundService.name==name))
    if not item:raise HTTPException(status_code=404,detail="Background service not found")
    db.add(AuditEvent(actor_id=user.id,action="read",resource_type="background_service",resource_id=item.name));db.commit();return response(background_data(item))


def trigger_background(db:Session,item:BackgroundService,user:User,action:str):
    now=datetime.now(timezone.utc);item.running_state=0;item.lock_expires_at=now+timedelta(minutes=5);item.next_run=now+timedelta(minutes=max(item.execute_interval_minutes,1));db.add(AuditEvent(actor_id=user.id,action=action,resource_type="background_service",resource_id=item.name))


@router.post("/apis/{site}/api/background_service/{name}/run")
def background_service_run(site:str,name:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);permission(user,"admin","super","write");item=db.scalar(select(BackgroundService).where(BackgroundService.name==name).with_for_update())
    if not item:raise HTTPException(status_code=404,detail="Background service not found")
    trigger_background(db,item,user,"run");db.commit();db.refresh(item);return response(background_data(item))


@router.post("/apis/{site}/api/background_service/$run")
def background_services_run_due(site:str,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site);now=datetime.now(timezone.utc);items=list(db.scalars(select(BackgroundService).where(BackgroundService.active.is_(True),BackgroundService.next_run<=now).with_for_update()))
    for item in items:trigger_background(db,item,user,"run-due")
    db.commit();return response([background_data(item) for item in items])


@router.get("/apis/{site}/api/{resource}")
@router.get("/apis/{site}/api/{resource}/{item_uuid}")
def global_clinical_resource(site:str,resource:str,item_uuid:str|None=None,db:Session=Depends(get_db),user:User=Depends(current_user)):
    default_site(site)
    if resource not in {"medical_problem","allergy","immunization","procedure","drug","prescription"}:raise HTTPException(status_code=404,detail="Clinical resource not found")
    permission(user,"patients","med")
    if resource not in {"medical_problem","allergy"}:
        model={"immunization":Immunization,"procedure":ExternalProcedure,"drug":InventoryProduct,"prescription":Prescription}[resource];query=select(model)
        if resource=="prescription":query=query.where(Prescription.status!="entered-in-error")
        if item_uuid:query=query.where(model.uuid==item_uuid)
        if item_uuid:
            item=db.scalar(query)
            if not item:raise HTTPException(status_code=404,detail=f"{resource.title()} not found")
            data=prescription_data(db,item) if resource=="prescription" else jsonable_encoder(item)
        else:
            items=list(db.scalars(query.order_by(model.id.desc()).limit(100)));data=[prescription_data(db,item) for item in items] if resource=="prescription" else jsonable_encoder(items)
        db.add(AuditEvent(actor_id=user.id,action="read" if item_uuid else "search",resource_type=resource,resource_id=item_uuid));db.commit();return response(data)
    query=select(ClinicalItem).where(ClinicalItem.category==CLINICAL_RESOURCES[resource],ClinicalItem.status!="entered-in-error")
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
