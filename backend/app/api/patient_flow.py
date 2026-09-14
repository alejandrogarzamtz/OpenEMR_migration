from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Appointment, AuditEvent, Encounter, Patient, PatientFlowEpisode, PatientFlowEvent, User
from ..schemas import PatientFlowEpisodeOut, PatientFlowEventCreate, PatientFlowEventOut
from ..security import appointment_user, appointment_write_user

router = APIRouter(prefix="/api/v1", tags=["patient-flow"])


def latest_event(db: Session, episode_id: int) -> PatientFlowEvent | None:
    return db.scalar(select(PatientFlowEvent).where(PatientFlowEvent.episode_id == episode_id).order_by(PatientFlowEvent.sequence.desc()).limit(1))


def episode_out(db: Session, episode: PatientFlowEpisode, include_events: bool = False) -> PatientFlowEpisodeOut:
    patient = db.get(Patient, episode.patient_id)
    appointment = db.get(Appointment, episode.appointment_id) if episode.appointment_id else None
    encounter = db.get(Encounter, episode.encounter_id) if episode.encounter_id else None
    current = latest_event(db, episode.id)
    events = list(db.scalars(select(PatientFlowEvent).where(PatientFlowEvent.episode_id == episode.id).order_by(PatientFlowEvent.sequence))) if include_events else []
    return PatientFlowEpisodeOut(
        uuid=episode.uuid, patient_uuid=patient.uuid, patient_name=f"{patient.last_name}, {patient.first_name}",
        appointment_uuid=appointment.uuid if appointment else None, encounter_uuid=encounter.uuid if encounter else None,
        started_at=episode.started_at, current_status=current.status if current else None,
        current_room=current.room if current else None, current_since=current.started_at if current else None,
        random_drug_test=episode.random_drug_test, drug_screen_completed=episode.drug_screen_completed,
        events=[PatientFlowEventOut.model_validate(event) for event in events],
    )


@router.get("/patient-flow", response_model=list[PatientFlowEpisodeOut])
def list_patient_flow(
    starts_from: datetime | None = None, starts_before: datetime | None = None,
    current_status: str | None = Query(default=None, alias="status"),
    db: Session = Depends(get_db), user: User = Depends(appointment_user),
) -> list[PatientFlowEpisodeOut]:
    query = select(PatientFlowEpisode)
    if starts_from: query = query.where(PatientFlowEpisode.started_at >= starts_from)
    if starts_before: query = query.where(PatientFlowEpisode.started_at < starts_before)
    episodes = list(db.scalars(query.order_by(PatientFlowEpisode.started_at).limit(500)))
    result = [episode_out(db, episode) for episode in episodes]
    if current_status: result = [episode for episode in result if episode.current_status == current_status]
    db.add(AuditEvent(actor_id=user.id, action="search", resource_type="patient_flow")); db.commit()
    return result


@router.post("/appointments/{appointment_uuid}/patient-flow", response_model=PatientFlowEpisodeOut, status_code=status.HTTP_201_CREATED)
def start_patient_flow(
    appointment_uuid: str, body: PatientFlowEventCreate,
    db: Session = Depends(get_db), user: User = Depends(appointment_write_user),
) -> PatientFlowEpisodeOut:
    appointment = db.scalar(select(Appointment).where(Appointment.uuid == appointment_uuid))
    if not appointment: raise HTTPException(status_code=404, detail="Appointment not found")
    existing = db.scalar(select(PatientFlowEpisode).where(PatientFlowEpisode.appointment_id == appointment.id))
    if existing: raise HTTPException(status_code=409, detail="Patient flow already started")
    encounter = None
    if body.encounter_uuid:
        encounter = db.scalar(select(Encounter).where(Encounter.uuid == body.encounter_uuid, Encounter.patient_id == appointment.patient_id))
        if not encounter: raise HTTPException(status_code=404, detail="Encounter not found for appointment patient")
    now = datetime.now(timezone.utc)
    episode = PatientFlowEpisode(patient_id=appointment.patient_id, appointment_id=appointment.id, encounter_id=encounter.id if encounter else None, started_at=now)
    db.add(episode); db.flush()
    event = PatientFlowEvent(episode_id=episode.id, sequence=1, started_at=now, status=body.status, room=body.room, actor_id=user.id, actor_name=user.email)
    appointment.status = body.status; appointment.room = body.room
    db.add(event); db.add(AuditEvent(actor_id=user.id, action="create", resource_type="patient_flow", resource_id=episode.uuid)); db.commit(); db.refresh(episode)
    return episode_out(db, episode, include_events=True)


@router.get("/patient-flow/{episode_uuid}", response_model=PatientFlowEpisodeOut)
def get_patient_flow(episode_uuid: str, db: Session = Depends(get_db), user: User = Depends(appointment_user)) -> PatientFlowEpisodeOut:
    episode = db.scalar(
        select(PatientFlowEpisode)
        .where(PatientFlowEpisode.uuid == episode_uuid)
        .with_for_update()
    )
    if not episode: raise HTTPException(status_code=404, detail="Patient flow not found")
    db.add(AuditEvent(actor_id=user.id, action="read", resource_type="patient_flow", resource_id=episode.uuid)); db.commit()
    return episode_out(db, episode, include_events=True)


@router.post("/patient-flow/{episode_uuid}/events", response_model=PatientFlowEpisodeOut, status_code=status.HTTP_201_CREATED)
def transition_patient_flow(
    episode_uuid: str, body: PatientFlowEventCreate,
    db: Session = Depends(get_db), user: User = Depends(appointment_write_user),
) -> PatientFlowEpisodeOut:
    episode = db.scalar(select(PatientFlowEpisode).where(PatientFlowEpisode.uuid == episode_uuid))
    if not episode: raise HTTPException(status_code=404, detail="Patient flow not found")
    previous = latest_event(db, episode.id)
    if previous and previous.status == body.status and previous.room == body.room:
        raise HTTPException(status_code=409, detail="Patient flow status and room are unchanged")
    if body.encounter_uuid:
        encounter = db.scalar(select(Encounter).where(Encounter.uuid == body.encounter_uuid, Encounter.patient_id == episode.patient_id))
        if not encounter: raise HTTPException(status_code=404, detail="Encounter not found for patient")
        episode.encounter_id = encounter.id
    sequence = (previous.sequence if previous else 0) + 1
    event = PatientFlowEvent(episode_id=episode.id, sequence=sequence, started_at=datetime.now(timezone.utc), status=body.status, room=body.room, actor_id=user.id, actor_name=user.email)
    if episode.appointment_id:
        appointment = db.get(Appointment, episode.appointment_id)
        if appointment:
            appointment.status = body.status
            appointment.room = body.room
    db.add(event); db.add(AuditEvent(actor_id=user.id, action="transition", resource_type="patient_flow", resource_id=episode.uuid, detail=f"status={body.status};room={body.room or ''}")); db.commit(); db.refresh(episode)
    return episode_out(db, episode, include_events=True)
