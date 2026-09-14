from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditEvent, CarePlan, Encounter, User
from ..schemas import CarePlanCreate, CarePlanOut, CarePlanUpdate
from ..security import clinical_user
from ..services.clinical_signatures import encounter_locked
from ..services.patients import patient_by_uuid

router=APIRouter(prefix="/api/v1/patients",tags=["care-plans"])


def encounter_for_patient(db:Session,patient_id:int,encounter_uuid:str)->Encounter:
    encounter=db.scalar(select(Encounter).where(Encounter.uuid==encounter_uuid,Encounter.patient_id==patient_id))
    if not encounter:raise HTTPException(status_code=404,detail="Encounter not found for patient")
    return encounter


def output(item:CarePlan,encounter_uuid:str)->CarePlanOut:
    values={key:getattr(item,key) for key in ("uuid","recorded_at","code","code_text","description","external_id","plan_type","note_related_to","ends_at","reason_code","reason_description","reason_recorded_at","reason_ends_at","reason_status","status","target_date","engagement_category","active","created_at","updated_at")}
    for key in ("recorded_at","ends_at","reason_recorded_at","reason_ends_at","target_date","created_at","updated_at"):
        if values[key] is not None and values[key].tzinfo is None:
            values[key]=values[key].replace(tzinfo=timezone.utc)
    return CarePlanOut(encounter_uuid=encounter_uuid,**values)


@router.post("/{patient_uuid}/care-plans",response_model=CarePlanOut,status_code=201)
def create_care_plan(patient_uuid:str,body:CarePlanCreate,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    patient=patient_by_uuid(db,patient_uuid);encounter=encounter_for_patient(db,patient.id,body.encounter_uuid)
    if encounter_locked(db,encounter.id):raise HTTPException(status_code=423,detail="Encounter is electronically signed and locked")
    item=CarePlan(patient_id=patient.id,encounter_id=encounter.id,author_id=user.id,**body.model_dump(exclude={"encounter_uuid"}));db.add(item);db.flush()
    db.add(AuditEvent(actor_id=user.id,action="create",resource_type="care_plan",resource_id=item.uuid,detail=f"status={item.status}; code={item.code}"));db.commit();db.refresh(item)
    return output(item,encounter.uuid)


@router.get("/{patient_uuid}/care-plans",response_model=list[CarePlanOut])
def list_care_plans(patient_uuid:str,encounter_uuid:str|None=None,include_inactive:bool=False,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    patient=patient_by_uuid(db,patient_uuid);query=select(CarePlan,Encounter.uuid).join(Encounter).where(CarePlan.patient_id==patient.id)
    if encounter_uuid:query=query.where(Encounter.uuid==encounter_uuid)
    if not include_inactive:query=query.where(CarePlan.active.is_(True))
    rows=db.execute(query.order_by(CarePlan.recorded_at.desc(),CarePlan.id.desc())).all();db.add(AuditEvent(actor_id=user.id,action="search",resource_type="care_plan",resource_id=patient.uuid,detail=f"records={len(rows)}"));db.commit()
    return [output(item,e_uuid) for item,e_uuid in rows]


@router.put("/{patient_uuid}/care-plans/{plan_uuid}",response_model=CarePlanOut)
def update_care_plan(patient_uuid:str,plan_uuid:str,body:CarePlanUpdate,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    patient=patient_by_uuid(db,patient_uuid);row=db.execute(select(CarePlan,Encounter.uuid).join(Encounter).where(CarePlan.uuid==plan_uuid,CarePlan.patient_id==patient.id).with_for_update()).first()
    if not row:raise HTTPException(status_code=404,detail="Care plan not found")
    item,e_uuid=row
    if not item.active:raise HTTPException(status_code=409,detail="Inactive care plans cannot be edited")
    if encounter_locked(db,item.encounter_id):raise HTTPException(status_code=423,detail="Encounter is electronically signed and locked")
    for key,value in body.model_dump().items():setattr(item,key,value)
    item.updated_at=datetime.now(timezone.utc);db.add(AuditEvent(actor_id=user.id,action="update",resource_type="care_plan",resource_id=item.uuid,detail=f"status={item.status}; code={item.code}"));db.commit();db.refresh(item)
    return output(item,e_uuid)


@router.delete("/{patient_uuid}/care-plans/{plan_uuid}",status_code=status.HTTP_204_NO_CONTENT)
def inactivate_care_plan(patient_uuid:str,plan_uuid:str,reason:str=Query(min_length=3,max_length=255),db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    patient=patient_by_uuid(db,patient_uuid);item=db.scalar(select(CarePlan).where(CarePlan.uuid==plan_uuid,CarePlan.patient_id==patient.id).with_for_update())
    if not item:raise HTTPException(status_code=404,detail="Care plan not found")
    if not item.active:raise HTTPException(status_code=409,detail="Care plan is already inactive")
    if encounter_locked(db,item.encounter_id):raise HTTPException(status_code=423,detail="Encounter is electronically signed and locked")
    item.active=False;item.status="cancelled";item.updated_at=datetime.now(timezone.utc);db.add(AuditEvent(actor_id=user.id,action="inactivate",resource_type="care_plan",resource_id=item.uuid,detail=f"reason={reason}"));db.commit()
    return Response(status_code=204)
