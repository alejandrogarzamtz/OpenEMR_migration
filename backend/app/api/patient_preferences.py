from datetime import timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditEvent, PatientPreference, PreferenceValueSet, User
from ..schemas import PatientPreferenceAmend, PatientPreferenceCreate, PatientPreferenceOut, PreferenceValueSetOut
from ..security import clinical_user
from ..services.patients import patient_by_uuid

router=APIRouter(prefix="/api/v1/patients",tags=["patient-preferences"])

OBSERVATIONS={
    "treatment-intervention":[
        ("81329-5","Cardiopulmonary resuscitation preference"),("81330-3","Intubation preference"),("81331-1","Tube feeding preference"),
        ("81332-9","Intravenous fluids and support preference"),("81333-7","Antibiotics preference"),("75773-2","Goals, preferences, and priorities for medical treatment"),
        ("81336-0","Cardiopulmonary bypass preference"),("81337-8","Mechanical ventilation preference"),("81376-6","Organ donation preference"),("81378-2","Health care goals"),
    ],
    "care-experience":[
        ("95541-9","Care experience preference"),("81364-2","Religious or cultural belief preference"),("81365-9","Religious contact preference"),
        ("103980-9","Preferred pharmacy"),("81338-6","Narrative care preference"),("81342-8","Conditional care preference"),
        ("81343-6","End-of-life care preference"),("81362-6","Preferred location of care"),("81363-4","Preferred health professional"),
    ],
}


def output(db:Session,item:PatientPreference)->PatientPreferenceOut:
    supersedes=db.scalar(select(PatientPreference.uuid).where(PatientPreference.id==item.supersedes_id)) if item.supersedes_id else None
    values={key:getattr(item,key) for key in ("uuid","category","observation_code","observation_code_text","value_type","value_code","value_code_system","value_display","value_text","value_boolean","effective_at","status","note","amendment_reason","active","inactivated_reason","created_at")}
    for key in ("effective_at","created_at"):
        if values[key].tzinfo is None:values[key]=values[key].replace(tzinfo=timezone.utc)
    return PatientPreferenceOut(supersedes_uuid=supersedes,**values)


def preference_for_patient(db:Session,patient_id:int,preference_uuid:str,lock:bool=False)->PatientPreference:
    query=select(PatientPreference).where(PatientPreference.uuid==preference_uuid,PatientPreference.patient_id==patient_id)
    item=db.scalar(query.with_for_update() if lock else query)
    if not item:raise HTTPException(status_code=404,detail="Patient preference not found")
    return item


@router.get("/{patient_uuid}/preference-catalog")
def preference_catalog(patient_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    patient=patient_by_uuid(db,patient_uuid);answers=list(db.scalars(select(PreferenceValueSet).where(PreferenceValueSet.active.is_(True)).order_by(PreferenceValueSet.observation_code,PreferenceValueSet.sort_order,PreferenceValueSet.id)))
    grouped={};
    for item in answers:grouped.setdefault(item.observation_code,[]).append(PreferenceValueSetOut.model_validate(item,from_attributes=True).model_dump())
    db.add(AuditEvent(actor_id=user.id,action="read",resource_type="preference_catalog",resource_id=patient.uuid));db.commit()
    return {"observations":{category:[{"code":code,"display":display} for code,display in items] for category,items in OBSERVATIONS.items()},"answers":grouped}


@router.get("/{patient_uuid}/preferences",response_model=list[PatientPreferenceOut])
def list_preferences(patient_uuid:str,category:str|None=Query(default=None,pattern="^(treatment-intervention|care-experience)$"),include_history:bool=False,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    patient=patient_by_uuid(db,patient_uuid);query=select(PatientPreference).where(PatientPreference.patient_id==patient.id)
    if category:query=query.where(PatientPreference.category==category)
    if not include_history:query=query.where(PatientPreference.active.is_(True))
    items=list(db.scalars(query.order_by(PatientPreference.effective_at.desc(),PatientPreference.id.desc())));result=[output(db,item) for item in items]
    db.add(AuditEvent(actor_id=user.id,action="search",resource_type="patient_preference",resource_id=patient.uuid,detail=f"records={len(result)}; history={include_history}"));db.commit();return result


@router.post("/{patient_uuid}/preferences",response_model=PatientPreferenceOut,status_code=201)
def create_preference(patient_uuid:str,body:PatientPreferenceCreate,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    patient=patient_by_uuid(db,patient_uuid);item=PatientPreference(patient_id=patient.id,recorded_by_id=user.id,**body.model_dump());db.add(item);db.flush()
    db.add(AuditEvent(actor_id=user.id,action="create",resource_type="patient_preference",resource_id=item.uuid,detail=f"category={item.category}; observation={item.observation_code}"));db.commit();db.refresh(item);return output(db,item)


@router.post("/{patient_uuid}/preferences/{preference_uuid}/amend",response_model=PatientPreferenceOut,status_code=201)
def amend_preference(patient_uuid:str,preference_uuid:str,body:PatientPreferenceAmend,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    patient=patient_by_uuid(db,patient_uuid);previous=preference_for_patient(db,patient.id,preference_uuid,True)
    if not previous.active:raise HTTPException(status_code=409,detail="Only the current preference version can be amended")
    if body.category!=previous.category or body.observation_code!=previous.observation_code:raise HTTPException(status_code=409,detail="An amendment cannot change category or observation code")
    previous.active=False;previous.status="amended"
    item=PatientPreference(patient_id=patient.id,supersedes_id=previous.id,recorded_by_id=user.id,**body.model_dump());db.add(item);db.flush()
    db.add(AuditEvent(actor_id=user.id,action="amend",resource_type="patient_preference",resource_id=item.uuid,detail=f"supersedes={previous.uuid}; reason={item.amendment_reason}"));db.commit();db.refresh(item);return output(db,item)


@router.delete("/{patient_uuid}/preferences/{preference_uuid}",status_code=status.HTTP_204_NO_CONTENT)
def inactivate_preference(patient_uuid:str,preference_uuid:str,reason:str=Query(min_length=3,max_length=255),db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    patient=patient_by_uuid(db,patient_uuid);item=preference_for_patient(db,patient.id,preference_uuid,True)
    if not item.active:raise HTTPException(status_code=409,detail="Patient preference is already inactive")
    item.active=False;item.inactivated_reason=reason;db.add(AuditEvent(actor_id=user.id,action="inactivate",resource_type="patient_preference",resource_id=item.uuid,detail=f"reason={reason}"));db.commit();return Response(status_code=204)
