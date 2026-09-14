from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditEvent, Facility, PatientProviderAssignment, Practitioner, User
from ..schemas import PatientProviderAssignmentCreate, PatientProviderAssignmentOut
from ..security import clinical_user, clinical_write_user
from ..services.patients import patient_by_uuid

router=APIRouter(prefix="/api/v1/patients",tags=["patient-providers"])


def assignment_out(item,practitioner_uuid=None,facility_uuid=None):
    fields=("uuid","role","status","assigned_at","ended_at","practitioner_name","facility_name","source","legacy_practitioner_id","legacy_facility_id")
    return PatientProviderAssignmentOut(practitioner_uuid=practitioner_uuid,facility_uuid=facility_uuid,**{key:getattr(item,key) for key in fields})


@router.get("/{patient_uuid}/provider-assignments/catalog")
def assignment_catalog(patient_uuid: str,db: Session=Depends(get_db),user: User=Depends(clinical_user)):
    patient_by_uuid(db,patient_uuid)
    practitioners=list(db.scalars(select(Practitioner).where(Practitioner.active.is_(True)).order_by(Practitioner.last_name,Practitioner.first_name)))
    facilities=list(db.scalars(select(Facility).where(Facility.active.is_(True)).order_by(Facility.name)))
    return {"practitioners":[{"uuid":x.uuid,"name":" ".join(filter(None,(x.first_name,x.last_name))),"primary_facility_id":x.primary_facility_id} for x in practitioners],"facilities":[{"uuid":x.uuid,"name":x.name} for x in facilities]}


@router.get("/{patient_uuid}/provider-assignments",response_model=list[PatientProviderAssignmentOut])
def list_assignments(patient_uuid: str,db: Session=Depends(get_db),user: User=Depends(clinical_user)):
    patient=patient_by_uuid(db,patient_uuid)
    rows=db.execute(select(PatientProviderAssignment,Practitioner.uuid,Facility.uuid).outerjoin(Practitioner,PatientProviderAssignment.practitioner_id==Practitioner.id).outerjoin(Facility,PatientProviderAssignment.facility_id==Facility.id).where(PatientProviderAssignment.patient_id==patient.id).order_by(PatientProviderAssignment.assigned_at.desc().nullslast(),PatientProviderAssignment.id.desc())).all()
    db.add(AuditEvent(actor_id=user.id,action="search",resource_type="patient_provider_assignment",resource_id=patient.uuid,detail=f"records={len(rows)}"));db.commit()
    return [assignment_out(item,practitioner_uuid,facility_uuid) for item,practitioner_uuid,facility_uuid in rows]


@router.post("/{patient_uuid}/provider-assignments",response_model=PatientProviderAssignmentOut,status_code=status.HTTP_201_CREATED)
def create_assignment(patient_uuid: str,body: PatientProviderAssignmentCreate,db: Session=Depends(get_db),user: User=Depends(clinical_write_user)):
    patient=patient_by_uuid(db,patient_uuid);practitioner=db.scalar(select(Practitioner).where(Practitioner.uuid==body.practitioner_uuid,Practitioner.active.is_(True)))
    if not practitioner:raise HTTPException(status_code=404,detail="Practitioner not found")
    facility=db.scalar(select(Facility).where(Facility.uuid==body.facility_uuid,Facility.active.is_(True))) if body.facility_uuid else db.get(Facility,practitioner.primary_facility_id) if practitioner.primary_facility_id else None
    if body.facility_uuid and not facility:raise HTTPException(status_code=404,detail="Facility not found")
    now=body.assigned_at or datetime.now(timezone.utc)
    previous=list(db.scalars(select(PatientProviderAssignment).where(PatientProviderAssignment.patient_id==patient.id,PatientProviderAssignment.role==body.role,PatientProviderAssignment.status=="active").with_for_update()))
    for item in previous:item.status="ended";item.ended_at=now
    name=" ".join(filter(None,(practitioner.first_name,practitioner.last_name)))
    item=PatientProviderAssignment(patient_id=patient.id,legacy_patient_id=patient.legacy_pid or 0,practitioner_id=practitioner.id,legacy_practitioner_id=practitioner.legacy_user_id,facility_id=facility.id if facility else None,legacy_facility_id=facility.legacy_facility_id if facility else None,role=body.role,status="active",assigned_at=now,practitioner_name=name,facility_name=facility.name if facility else None,source="modern",created_by_id=user.id)
    db.add(item);db.flush();db.add(AuditEvent(actor_id=user.id,action="create",resource_type="patient_provider_assignment",resource_id=item.uuid,detail=f"patient={patient.uuid};role={body.role};superseded={len(previous)}"));db.commit();db.refresh(item)
    return assignment_out(item,practitioner.uuid,facility.uuid if facility else None)


@router.delete("/{patient_uuid}/provider-assignments/{assignment_uuid}",status_code=status.HTTP_204_NO_CONTENT)
def end_assignment(patient_uuid: str,assignment_uuid: str,db: Session=Depends(get_db),user: User=Depends(clinical_write_user)):
    patient=patient_by_uuid(db,patient_uuid);item=db.scalar(select(PatientProviderAssignment).where(PatientProviderAssignment.uuid==assignment_uuid,PatientProviderAssignment.patient_id==patient.id).with_for_update())
    if not item:raise HTTPException(status_code=404,detail="Assignment not found")
    if item.status=="active":item.status="ended";item.ended_at=datetime.now(timezone.utc)
    db.add(AuditEvent(actor_id=user.id,action="end",resource_type="patient_provider_assignment",resource_id=item.uuid,detail=f"patient={patient.uuid}"));db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
