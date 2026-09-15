"""Remaining OpenEMR FHIR R4 contracts and persisted Bulk Data export."""
from datetime import date, datetime, timedelta, timezone
import json

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from .db import get_db
from .fhir import (
    audit, bundle, clinical_resources, coverage_resource, diagnostic_report_resource,
    document_reference_resource, immunization_resource, lab_observation_resource,
    medication_request_resource, patient_or_404, patient_reference, patient_resource,
    practitioner_resource, service_request_resource,
)
from .models import (
    AuditEvent, BulkExportJob, Coverage, Document, ExternalProcedure, Facility,
    Immunization, InventoryProduct, InventoryTransaction, LabOrder, LabResult, Patient,
    Practitioner, Prescription, ReferenceOption, User,
)
from .security import clinical_user, clinical_write_user

router = APIRouter(prefix="/fhir", tags=["FHIR R4"])


def outcome(code: str, diagnostics: str, status_code: int = 400):
    raise HTTPException(status_code=status_code, detail={"resourceType":"OperationOutcome","issue":[{"severity":"error","code":code,"diagnostics":diagnostics}]})


def product_resource(item: InventoryProduct, resource_type: str = "Medication") -> dict:
    coding=[]
    if item.ndc_number:coding.append({"system":"http://hl7.org/fhir/sid/ndc","code":item.ndc_number,"display":item.name})
    if item.drug_code:coding.append({"system":"urn:openrm:drug-code","code":item.drug_code,"display":item.name})
    resource={"resourceType":resource_type,"id":item.uuid,"status":"active" if item.active else "inactive"}
    if resource_type=="Medication":resource["code"]={"coding":coding,"text":item.name};resource["form"]={"text":item.form} if item.form else {}
    else:resource.update({"deviceName":[{"name":item.name,"type":"user-friendly-name"}],"type":{"coding":coding,"text":item.name}})
    return resource


def media_resource(item: Document, patient_uuid: str) -> dict:
    kind="image" if item.mime_type.startswith("image/") else "video" if item.mime_type.startswith("video/") else "audio"
    return {"resourceType":"Media","id":item.uuid,"status":"completed","type":{"coding":[{"system":"http://terminology.hl7.org/CodeSystem/media-type","code":kind}]},"subject":{"reference":f"Patient/{patient_uuid}"},"createdDateTime":item.uploaded_at.isoformat(),"content":{"contentType":item.mime_type,"url":f"/fhir/Binary/{item.uuid}","title":item.name,"hash":item.sha256}}


def specimen_resource(item: LabOrder, patient_uuid: str) -> dict:
    resource={"resourceType":"Specimen","id":item.uuid,"status":"available" if item.collected_at else "unavailable","subject":{"reference":f"Patient/{patient_uuid}"},"type":{"text":item.specimen_type or "Specimen"},"request":[{"reference":f"ServiceRequest/{item.uuid}"}]}
    if item.collected_at:resource["collection"]={"collectedDateTime":item.collected_at.isoformat(),**({"bodySite":{"text":item.specimen_location}} if item.specimen_location else {}),**({"quantity":{"value":item.specimen_volume}} if item.specimen_volume else {})}
    return resource


def procedure_resource(item: ExternalProcedure, patient_uuid: str) -> dict:
    coding=[]
    if item.code:coding=[{"system":item.code_system or "urn:openrm:procedure-code","code":item.code,"display":item.code_text}]
    return {"resourceType":"Procedure","id":item.uuid,"status":"completed","code":{"coding":coding,"text":item.code_text or item.code or "Procedure"},"subject":{"reference":f"Patient/{patient_uuid}"},"performedDateTime":item.occurred_on.isoformat(),**({"location":{"display":item.facility_name}} if item.facility_name else {})}


def dispense_resource(item: InventoryTransaction, product: InventoryProduct, patient_uuid: str) -> dict:
    return {"resourceType":"MedicationDispense","id":item.uuid,"status":"completed","medicationReference":{"reference":f"Medication/{product.uuid}","display":product.name},"subject":{"reference":f"Patient/{patient_uuid}"},"whenHandedOver":item.occurred_on.isoformat(),"quantity":{"value":abs(item.quantity),"unit":product.unit or "unit"},**({"authorizingPrescription":[{"reference":f"MedicationRequest/{item.prescription_id}"}]} if item.prescription_id else {})}


@router.get("/Medication")
def search_medications(code:str|None=None,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    query=select(InventoryProduct)
    if code:query=query.where(or_(InventoryProduct.ndc_number==code.rsplit("|",1)[-1],InventoryProduct.drug_code==code.rsplit("|",1)[-1]))
    rows=list(db.scalars(query.limit(100)));audit(db,user,"Medication",search=True);return bundle("Medication",[product_resource(x) for x in rows])


@router.get("/Medication/{resource_uuid}")
def read_medication(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    item=db.scalar(select(InventoryProduct).where(InventoryProduct.uuid==resource_uuid))
    if not item:outcome("not-found","Medication not found",404)
    audit(db,user,"Medication",item.uuid);return product_resource(item)


@router.get("/Device")
def search_devices(db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    rows=list(db.scalars(select(InventoryProduct).where(InventoryProduct.consumable.is_(False)).limit(100)));audit(db,user,"Device",search=True);return bundle("Device",[product_resource(x,"Device") for x in rows])


@router.get("/Device/{resource_uuid}")
def read_device(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    item=db.scalar(select(InventoryProduct).where(InventoryProduct.uuid==resource_uuid,InventoryProduct.consumable.is_(False)))
    if not item:outcome("not-found","Device not found",404)
    audit(db,user,"Device",item.uuid);return product_resource(item,"Device")


@router.get("/MedicationDispense")
def search_dispenses(patient:str=Query(),db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    owner=patient_or_404(db,patient_reference(patient));rows=db.execute(select(InventoryTransaction,InventoryProduct).join(InventoryProduct).where(InventoryTransaction.patient_id==owner.id,InventoryTransaction.transaction_type.in_(["sale","dispense"]))).all();audit(db,user,"MedicationDispense",owner.uuid,search=True);return bundle("MedicationDispense",[dispense_resource(x,p,owner.uuid) for x,p in rows])


@router.get("/MedicationDispense/{resource_uuid}")
def read_dispense(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    row=db.execute(select(InventoryTransaction,InventoryProduct,Patient.uuid).join(InventoryProduct).join(Patient,InventoryTransaction.patient_id==Patient.id).where(InventoryTransaction.uuid==resource_uuid)).first()
    if not row:outcome("not-found","MedicationDispense not found",404)
    item,product,patient_uuid=row;audit(db,user,"MedicationDispense",item.uuid);return dispense_resource(item,product,patient_uuid)


@router.get("/Media")
def search_media(patient:str=Query(),db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    owner=patient_or_404(db,patient_reference(patient));rows=list(db.scalars(select(Document).where(Document.patient_id==owner.id,or_(Document.mime_type.like("image/%"),Document.mime_type.like("video/%"),Document.mime_type.like("audio/%")))));audit(db,user,"Media",owner.uuid,search=True);return bundle("Media",[media_resource(x,owner.uuid) for x in rows])


@router.get("/Media/{resource_uuid}")
def read_media(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    row=db.execute(select(Document,Patient.uuid).join(Patient).where(Document.uuid==resource_uuid)).first()
    if not row:outcome("not-found","Media not found",404)
    item,patient_uuid=row;audit(db,user,"Media",item.uuid);return media_resource(item,patient_uuid)


@router.get("/Specimen")
def search_specimens(patient:str=Query(),db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    owner=patient_or_404(db,patient_reference(patient));rows=list(db.scalars(select(LabOrder).where(LabOrder.patient_id==owner.id,LabOrder.specimen_type.is_not(None))));audit(db,user,"Specimen",owner.uuid,search=True);return bundle("Specimen",[specimen_resource(x,owner.uuid) for x in rows])


@router.get("/Specimen/{resource_uuid}")
def read_specimen(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    row=db.execute(select(LabOrder,Patient.uuid).join(Patient).where(LabOrder.uuid==resource_uuid,LabOrder.specimen_type.is_not(None))).first()
    if not row:outcome("not-found","Specimen not found",404)
    item,patient_uuid=row;audit(db,user,"Specimen",item.uuid);return specimen_resource(item,patient_uuid)


@router.get("/Procedure")
def search_procedures(patient:str=Query(),db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    owner=patient_or_404(db,patient_reference(patient));rows=list(db.scalars(select(ExternalProcedure).where(ExternalProcedure.patient_id==owner.id)));audit(db,user,"Procedure",owner.uuid,search=True);return bundle("Procedure",[procedure_resource(x,owner.uuid) for x in rows])


@router.get("/Procedure/{resource_uuid}")
def read_procedure(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    row=db.execute(select(ExternalProcedure,Patient.uuid).join(Patient).where(ExternalProcedure.uuid==resource_uuid)).first()
    if not row:outcome("not-found","Procedure not found",404)
    item,patient_uuid=row;audit(db,user,"Procedure",item.uuid);return procedure_resource(item,patient_uuid)


def provenance_resource(item: AuditEvent) -> dict:
    return {"resourceType":"Provenance","id":str(item.id),"recorded":item.occurred_at.isoformat(),"activity":{"coding":[{"system":"urn:openrm:audit-action","code":item.action}]},"target":[{"reference":f"{item.resource_type}/{item.resource_id}"}],"agent":[{"who":{"reference":f"Practitioner/{item.actor_id}"}}]}


@router.get("/Provenance")
def search_provenance(target:str|None=None,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    query=select(AuditEvent)
    if target:
        kind,_,identifier=target.partition("/");query=query.where(AuditEvent.resource_type==kind,AuditEvent.resource_id==identifier)
    rows=list(db.scalars(query.order_by(AuditEvent.id.desc()).limit(100)));return bundle("Provenance",[provenance_resource(x) for x in rows])


@router.get("/Provenance/{resource_id}")
def read_provenance(resource_id:int,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    item=db.get(AuditEvent,resource_id)
    if not item:outcome("not-found","Provenance not found",404)
    return provenance_resource(item)


def value_set_resource(list_id:str,rows:list[ReferenceOption])->dict:
    return {"resourceType":"ValueSet","id":list_id,"url":f"https://openrm.org/fhir/ValueSet/{list_id}","status":"active","name":list_id,"compose":{"include":[{"system":f"urn:openrm:list:{list_id}","concept":[{"code":x.option_id,"display":x.title} for x in rows if x.active]}]}}


@router.get("/ValueSet")
def search_value_sets(db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    rows=list(db.scalars(select(ReferenceOption).order_by(ReferenceOption.list_id,ReferenceOption.sequence)));groups={}
    for row in rows:groups.setdefault(row.list_id,[]).append(row)
    audit(db,user,"ValueSet",search=True);return bundle("ValueSet",[value_set_resource(key,value) for key,value in groups.items()])


@router.get("/ValueSet/{list_id}")
def read_value_set(list_id:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    rows=list(db.scalars(select(ReferenceOption).where(ReferenceOption.list_id==list_id).order_by(ReferenceOption.sequence)))
    if not rows:outcome("not-found","ValueSet not found",404)
    audit(db,user,"ValueSet",list_id);return value_set_resource(list_id,rows)


def group_resource(db:Session)->dict:
    count=db.scalar(select(func.count(Patient.id)).where(Patient.merged_at.is_(None))) or 0
    return {"resourceType":"Group","id":"all-patients","type":"person","actual":True,"active":True,"name":"All active patients","quantity":count}


@router.get("/Group")
def search_groups(db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    audit(db,user,"Group",search=True);return bundle("Group",[group_resource(db)])


@router.get("/Group/{group_id}")
def read_group(group_id:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    if group_id!="all-patients":outcome("not-found","Group not found",404)
    audit(db,user,"Group",group_id);return group_resource(db)


def role_resource(item:Practitioner,facility:Facility|None)->dict:
    return {"resourceType":"PractitionerRole","id":item.uuid,"active":item.active,"practitioner":{"reference":f"Practitioner/{item.uuid}"},**({"organization":{"reference":f"Organization/{facility.uuid}","display":facility.name}} if facility else {}),**({"specialty":[{"text":item.specialty}]} if item.specialty else {})}


@router.get("/PractitionerRole")
def search_roles(practitioner:str|None=None,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    query=select(Practitioner,Facility).outerjoin(Facility,Practitioner.primary_facility_id==Facility.id)
    if practitioner:query=query.where(Practitioner.uuid==practitioner.rsplit("/",1)[-1])
    rows=db.execute(query.limit(100)).all();audit(db,user,"PractitionerRole",search=True);return bundle("PractitionerRole",[role_resource(x,f) for x,f in rows])


@router.get("/PractitionerRole/{resource_uuid}")
def read_role(resource_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    row=db.execute(select(Practitioner,Facility).outerjoin(Facility,Practitioner.primary_facility_id==Facility.id).where(Practitioner.uuid==resource_uuid)).first()
    if not row:outcome("not-found","PractitionerRole not found",404)
    item,facility=row;audit(db,user,"PractitionerRole",item.uuid);return role_resource(item,facility)


def names(payload:dict)->tuple[str,str,str|None]:
    name=(payload.get("name") or [{}])[0];given=name.get("given") or []
    if not name.get("family") or not given:outcome("required","A family and given name are required")
    return given[0],name["family"],given[1] if len(given)>1 else None


def telecom(payload:dict,system:str)->str|None:
    return next((x.get("value") for x in payload.get("telecom",[]) if x.get("system")==system),None)


@router.post("/Patient",status_code=201)
def create_patient(payload:dict=Body(),db:Session=Depends(get_db),user:User=Depends(clinical_write_user)):
    if payload.get("resourceType")!="Patient":outcome("invalid","resourceType must be Patient")
    first,last,middle=names(payload)
    try:born=date.fromisoformat(payload["birthDate"])
    except (KeyError,ValueError):outcome("required","birthDate must be YYYY-MM-DD")
    item=Patient(first_name=first,middle_name=middle,last_name=last,date_of_birth=born,sex=payload.get("gender","unknown"),email=telecom(payload,"email"),phone=telecom(payload,"phone"));db.add(item);db.flush();db.add(AuditEvent(actor_id=user.id,action="fhir-create",resource_type="Patient",resource_id=item.uuid));db.commit();db.refresh(item);return JSONResponse(patient_resource(item),status_code=201,headers={"Location":f"/fhir/Patient/{item.uuid}"})


@router.put("/Patient/{resource_uuid}")
def update_patient(resource_uuid:str,payload:dict=Body(),db:Session=Depends(get_db),user:User=Depends(clinical_write_user)):
    item=patient_or_404(db,resource_uuid);first,last,middle=names(payload);item.first_name=first;item.last_name=last;item.middle_name=middle;item.email=telecom(payload,"email");item.phone=telecom(payload,"phone");item.sex=payload.get("gender",item.sex)
    if payload.get("birthDate"):item.date_of_birth=date.fromisoformat(payload["birthDate"])
    db.add(AuditEvent(actor_id=user.id,action="fhir-update",resource_type="Patient",resource_id=item.uuid));db.commit();return patient_resource(item)


def org_values(payload:dict)->dict:
    address=(payload.get("address") or [{}])[0];telecoms=payload.get("telecom",[])
    return {"name":payload.get("name") or "Unnamed organization","active":payload.get("active",True),"street":((address.get("line") or [None])[0]),"city":address.get("city"),"state":address.get("state"),"postal_code":address.get("postalCode"),"country_code":address.get("country"),"phone":next((x.get("value") for x in telecoms if x.get("system")=="phone"),None),"email":next((x.get("value") for x in telecoms if x.get("system")=="email"),None)}


@router.post("/Organization",status_code=201)
def create_organization(payload:dict=Body(),db:Session=Depends(get_db),user:User=Depends(clinical_write_user)):
    item=Facility(**org_values(payload));db.add(item);db.flush();db.add(AuditEvent(actor_id=user.id,action="fhir-create",resource_type="Organization",resource_id=item.uuid));db.commit();db.refresh(item);return JSONResponse({"resourceType":"Organization","id":item.uuid,"active":item.active,"name":item.name},status_code=201,headers={"Location":f"/fhir/Organization/{item.uuid}"})


@router.put("/Organization/{resource_uuid}")
def update_organization(resource_uuid:str,payload:dict=Body(),db:Session=Depends(get_db),user:User=Depends(clinical_write_user)):
    item=db.scalar(select(Facility).where(Facility.uuid==resource_uuid))
    if not item:outcome("not-found","Organization not found",404)
    for key,value in org_values(payload).items():setattr(item,key,value)
    db.add(AuditEvent(actor_id=user.id,action="fhir-update",resource_type="Organization",resource_id=item.uuid));db.commit();return {"resourceType":"Organization","id":item.uuid,"active":item.active,"name":item.name}


def practitioner_values(payload:dict)->dict:
    first,last,middle=names(payload);identifiers=payload.get("identifier",[])
    return {"first_name":first,"last_name":last,"middle_name":middle,"active":payload.get("active",True),"npi":next((x.get("value") for x in identifiers if "npi" in x.get("system","").lower()),None),"email":telecom(payload,"email"),"phone":telecom(payload,"phone")}


@router.post("/Practitioner",status_code=201)
def create_practitioner(payload:dict=Body(),db:Session=Depends(get_db),user:User=Depends(clinical_write_user)):
    item=Practitioner(**practitioner_values(payload));db.add(item);db.flush();db.add(AuditEvent(actor_id=user.id,action="fhir-create",resource_type="Practitioner",resource_id=item.uuid));db.commit();db.refresh(item);return JSONResponse(practitioner_resource(db,item),status_code=201,headers={"Location":f"/fhir/Practitioner/{item.uuid}"})


@router.put("/Practitioner/{resource_uuid}")
def update_practitioner(resource_uuid:str,payload:dict=Body(),db:Session=Depends(get_db),user:User=Depends(clinical_write_user)):
    item=db.scalar(select(Practitioner).where(Practitioner.uuid==resource_uuid))
    if not item:outcome("not-found","Practitioner not found",404)
    for key,value in practitioner_values(payload).items():setattr(item,key,value)
    db.add(AuditEvent(actor_id=user.id,action="fhir-update",resource_type="Practitioner",resource_id=item.uuid));db.commit();return practitioner_resource(db,item)


@router.post("/DocumentReference/$docref")
def docref(payload:dict=Body(),db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    parameters={x.get("name"):x for x in payload.get("parameter",[])};patient_value=(parameters.get("patient") or {}).get("valueId") or ((parameters.get("patient") or {}).get("valueReference") or {}).get("reference")
    if not patient_value:outcome("required","$docref requires the patient parameter")
    owner=patient_or_404(db,patient_reference(patient_value));rows=list(db.scalars(select(Document).where(Document.patient_id==owner.id).order_by(Document.uploaded_at.desc())));audit(db,user,"DocumentReference",owner.uuid,search=True);return bundle("DocumentReference",[document_reference_resource(db,x,owner.uuid) for x in rows])


OPERATIONS={"export":{"resourceType":"OperationDefinition","id":"export","url":"http://hl7.org/fhir/uv/bulkdata/OperationDefinition/export","status":"active","kind":"operation","code":"export","system":True,"type":False,"instance":False},"docref":{"resourceType":"OperationDefinition","id":"docref","url":"http://hl7.org/fhir/us/core/OperationDefinition/docref","status":"active","kind":"operation","code":"docref","system":False,"type":True,"instance":False}}


@router.get("/OperationDefinition")
def operation_definitions(user:User=Depends(clinical_user)):return bundle("OperationDefinition",list(OPERATIONS.values()))


@router.get("/OperationDefinition/{operation}")
def operation_definition(operation:str,user:User=Depends(clinical_user)):
    item=OPERATIONS.get(operation.removeprefix("$"))
    if not item:outcome("not-found","OperationDefinition not found",404)
    return item


def patient_export_resources(db:Session,owner:Patient)->dict[str,list[dict]]:
    result={"Patient":[patient_resource(owner)]}
    for resource_type,category in (("Condition","problem"),("AllergyIntolerance","allergy"),("MedicationStatement","medication")):result[resource_type]=clinical_resources(db,owner,category)
    result["Immunization"]=[immunization_resource(x,owner.uuid) for x in db.scalars(select(Immunization).where(Immunization.patient_id==owner.id))]
    result["MedicationRequest"]=[medication_request_resource(x,owner.uuid) for x in db.scalars(select(Prescription).where(Prescription.patient_id==owner.id))]
    result["DocumentReference"]=[document_reference_resource(db,x,owner.uuid) for x in db.scalars(select(Document).where(Document.patient_id==owner.id))]
    procedures=list(db.scalars(select(ExternalProcedure).where(ExternalProcedure.patient_id==owner.id)));result["Procedure"]=[procedure_resource(x,owner.uuid) for x in procedures]
    orders=list(db.scalars(select(LabOrder).where(LabOrder.patient_id==owner.id)));result["ServiceRequest"]=[service_request_resource(db,x,owner.uuid) for x in orders]
    observations=list(db.scalars(select(LabResult).join(LabOrder).where(LabOrder.patient_id==owner.id)));result["Observation"]=[lab_observation_resource(x,owner.uuid) for x in observations]
    return result


def start_export(db:Session,user:User,scope:str,scope_id:str|None,types:str|None,request:Request):
    if scope=="patient":patients=[patient_or_404(db,scope_id or "")]
    elif scope=="group":
        if scope_id!="all-patients":outcome("not-found","Group not found",404)
        patients=list(db.scalars(select(Patient).where(Patient.merged_at.is_(None))))
    else:patients=list(db.scalars(select(Patient).where(Patient.merged_at.is_(None))))
    selected={x.strip() for x in types.split(",")} if types else None;grouped={}
    for owner in patients:
        for kind,resources in patient_export_resources(db,owner).items():
            if selected is None or kind in selected:grouped.setdefault(kind,[]).extend(resources)
    job=BulkExportJob(requested_by_id=user.id,scope=scope,scope_id=scope_id,status="complete",transaction_time=datetime.now(timezone.utc),expires_at=datetime.now(timezone.utc)+timedelta(hours=24),output=[])
    db.add(job);db.flush();job.output=[{"type":kind,"url":f"{str(request.base_url).rstrip('/')}/fhir/bulk-files/{job.uuid}/{kind}.ndjson","count":len(resources),"content":"\n".join(json.dumps(x,separators=(",",":"),sort_keys=True) for x in resources)+("\n" if resources else "")} for kind,resources in grouped.items()];db.add(AuditEvent(actor_id=user.id,action="fhir-bulk-export",resource_type="BulkExportJob",resource_id=job.uuid));db.commit();return Response(status_code=202,headers={"Content-Location":f"/fhir/$bulkdata-status?_job={job.uuid}","Retry-After":"1"})


@router.get("/$export")
def system_export(request:Request,types:str|None=Query(default=None,alias="_type"),db:Session=Depends(get_db),user:User=Depends(clinical_user)):return start_export(db,user,"system",None,types,request)


@router.get("/Patient/$export")
def patient_export(request:Request,patient:str=Query(),types:str|None=Query(default=None,alias="_type"),db:Session=Depends(get_db),user:User=Depends(clinical_user)):return start_export(db,user,"patient",patient_reference(patient),types,request)


@router.get("/Group/{group_id}/$export")
def group_export(group_id:str,request:Request,types:str|None=Query(default=None,alias="_type"),db:Session=Depends(get_db),user:User=Depends(clinical_user)):return start_export(db,user,"group",group_id,types,request)


def export_job(db:Session,job_uuid:str,user:User)->BulkExportJob:
    job=db.scalar(select(BulkExportJob).where(BulkExportJob.uuid==job_uuid,BulkExportJob.requested_by_id==user.id,BulkExportJob.deleted_at.is_(None)))
    if not job:outcome("not-found","Bulk export job not found",404)
    expiry=job.expires_at if job.expires_at.tzinfo else job.expires_at.replace(tzinfo=timezone.utc)
    if expiry<datetime.now(timezone.utc):outcome("expired","Bulk export job expired",410)
    return job


@router.get("/$bulkdata-status")
def bulk_status(job_uuid:str=Query(alias="_job"),db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    job=export_job(db,job_uuid,user);return {"transactionTime":job.transaction_time.isoformat(),"request":job.scope,"requiresAccessToken":True,"output":[{k:v for k,v in item.items() if k!="content"} for item in job.output],"error":job.error}


@router.delete("/$bulkdata-status",status_code=202)
def cancel_export(job_uuid:str=Query(alias="_job"),db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    job=export_job(db,job_uuid,user);job.status="cancelled";job.deleted_at=datetime.now(timezone.utc);db.commit();return Response(status_code=202)


@router.get("/bulk-files/{job_uuid}/{resource_type}.ndjson")
def bulk_file(job_uuid:str,resource_type:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    job=export_job(db,job_uuid,user);item=next((x for x in job.output if x["type"]==resource_type),None)
    if not item:outcome("not-found","Bulk export file not found",404)
    return PlainTextResponse(item["content"],media_type="application/fhir+ndjson")
