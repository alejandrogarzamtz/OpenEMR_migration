from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditEvent, SocialHistory, User
from ..schemas import SocialHistoryCreate, SocialHistoryOut
from ..security import clinical_user, clinical_write_user
from ..services.patients import patient_by_uuid

router=APIRouter(prefix="/api/v1/patients",tags=["social-history"])


def history_out(item: SocialHistory) -> SocialHistoryOut:
    fields=("coffee","tobacco","alcohol","sleep_patterns","exercise_patterns","seatbelt_use","counseling","hazardous_activities","recreational_drugs","additional_history")
    return SocialHistoryOut(uuid=item.uuid,legacy_history_id=item.legacy_history_id,legacy_patient_id=item.legacy_patient_id,recorded_at=item.recorded_at,source_payload=item.legacy_payload,**{field:getattr(item,field) for field in fields})


@router.get("/{patient_uuid}/social-history",response_model=list[SocialHistoryOut])
def list_social_history(patient_uuid: str,db: Session=Depends(get_db),user: User=Depends(clinical_user)):
    patient=patient_by_uuid(db,patient_uuid)
    items=list(db.scalars(select(SocialHistory).where(SocialHistory.patient_id==patient.id).order_by(SocialHistory.recorded_at.desc(),SocialHistory.id.desc())))
    db.add(AuditEvent(actor_id=user.id,action="search",resource_type="social_history",resource_id=patient.uuid,detail=f"versions={len(items)}"));db.commit()
    return [history_out(item) for item in items]


@router.post("/{patient_uuid}/social-history",response_model=SocialHistoryOut,status_code=status.HTTP_201_CREATED)
def create_social_history(patient_uuid: str,body: SocialHistoryCreate,db: Session=Depends(get_db),user: User=Depends(clinical_write_user)):
    patient=patient_by_uuid(db,patient_uuid);data=body.model_dump();data["recorded_at"]=data["recorded_at"] or datetime.now(timezone.utc)
    item=SocialHistory(patient_id=patient.id,legacy_patient_id=patient.legacy_pid or 0,recorded_by_id=user.id,**data)
    db.add(item);db.flush();db.add(AuditEvent(actor_id=user.id,action="create",resource_type="social_history",resource_id=item.uuid,detail=f"patient={patient.uuid}"));db.commit();db.refresh(item)
    return history_out(item)
