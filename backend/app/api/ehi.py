from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditEvent, User
from ..security import clinical_user
from ..services.ehi_export import ccda_document, ehi_zip
from ..services.patients import patient_by_uuid

router=APIRouter(prefix="/api/v1/patients",tags=["EHI export"])


@router.get("/{patient_uuid}/ccda")
def export_ccda(patient_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    patient=patient_by_uuid(db,patient_uuid);content=ccda_document(db,patient);db.add(AuditEvent(actor_id=user.id,action="ccda-export",resource_type="Patient",resource_id=patient.uuid));db.commit();return Response(content,media_type="application/xml",headers={"Content-Disposition":f'attachment; filename="{patient.uuid}-ccda.xml"'})


@router.get("/{patient_uuid}/ehi-export")
def export_ehi(patient_uuid:str,db:Session=Depends(get_db),user:User=Depends(clinical_user)):
    patient=patient_by_uuid(db,patient_uuid);content=ehi_zip(db,patient);db.add(AuditEvent(actor_id=user.id,action="ehi-export",resource_type="Patient",resource_id=patient.uuid));db.commit();return Response(content,media_type="application/zip",headers={"Content-Disposition":f'attachment; filename="{patient.uuid}-ehi.zip"'})
