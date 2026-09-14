from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Patient


def patient_by_uuid(db: Session, patient_uuid: str) -> Patient:
    patient = db.scalar(select(Patient).where(Patient.uuid == patient_uuid))
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")
    return patient

