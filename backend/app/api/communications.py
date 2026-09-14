from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import (
    AuditEvent,
    ClinicalTask,
    CommunicationDelivery,
    Encounter,
    MessageThread,
    Patient,
    PortalAccount,
    SecureMessage,
    User,
)
from ..schemas import (
    ClinicalTaskCreate,
    ClinicalTaskOut,
    CommunicationDeliveryOut,
    MessageCreate,
    MessageReply,
    MessageThreadOut,
    PortalAccountCreate,
    PortalAccountOut,
    PortalLogin,
    PortalPasswordChange,
    PortalToken,
    SecureMessageOut,
    Token,
)
from ..security import (
    administration_user,
    communication_user,
    communication_write_user,
    create_portal_token,
    current_portal_account,
    password_hash,
)
from ..services.patients import patient_by_uuid

router = APIRouter(prefix="/api/v1", tags=["communications"])


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def account_out(account: PortalAccount, patient: Patient) -> PortalAccountOut:
    return PortalAccountOut(
        uuid=account.uuid,
        patient_uuid=patient.uuid,
        username=account.username,
        active=account.active,
        force_password_reset=account.force_password_reset,
        last_login_at=account.last_login_at,
    )


def message_out(message: SecureMessage) -> SecureMessageOut:
    return SecureMessageOut(**{key: getattr(message, key) for key in SecureMessageOut.model_fields})


def thread_out(db: Session, thread: MessageThread, patient: Patient, include_messages: bool = True) -> MessageThreadOut:
    messages = []
    if include_messages:
        messages = list(db.scalars(select(SecureMessage).where(SecureMessage.thread_id == thread.id).order_by(SecureMessage.created_at)))
    return MessageThreadOut(
        uuid=thread.uuid,
        patient_uuid=patient.uuid,
        patient_name=f"{patient.first_name} {patient.last_name}",
        subject=thread.subject,
        status=thread.status,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
        messages=[message_out(item) for item in messages],
    )


def task_out(task: ClinicalTask, patient: Patient, encounter: Encounter | None, assigned: User | None) -> ClinicalTaskOut:
    return ClinicalTaskOut(
        uuid=task.uuid,
        patient_uuid=patient.uuid,
        encounter_uuid=encounter.uuid if encounter else None,
        assigned_user_uuid=assigned.uuid if assigned else None,
        method=task.method,
        comment=task.comment,
        status=task.status,
        due_at=task.due_at,
        completed_at=task.completed_at,
    )


def queue_patient_notice(db: Session, patient: Patient, message: SecureMessage) -> None:
    if not patient.allow_email or not patient.email:
        return
    db.add(
        CommunicationDelivery(
            patient_id=patient.id,
            message_id=message.id,
            channel="email",
            recipient=patient.email,
            subject="New secure message",
            body="A new secure message is available. Sign in to the patient portal to view it.",
            template_name="secure-message-notice",
        )
    )


def portal_thread(db: Session, account: PortalAccount, thread_uuid: str) -> tuple[MessageThread, Patient]:
    row = db.execute(
        select(MessageThread, Patient)
        .join(Patient, Patient.id == MessageThread.patient_id)
        .where(MessageThread.uuid == thread_uuid, MessageThread.patient_id == account.patient_id)
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Message thread not found")
    return row


def portal_ready_account(account: PortalAccount = Depends(current_portal_account)) -> PortalAccount:
    if account.force_password_reset:
        raise HTTPException(status_code=403, detail="Password reset required")
    return account


@router.post("/patients/{patient_uuid}/portal-account", response_model=PortalAccountOut, status_code=status.HTTP_201_CREATED)
def create_portal_account(body: PortalAccountCreate, patient_uuid: str, db: Session = Depends(get_db), user: User = Depends(communication_write_user)):
    patient = patient_by_uuid(db, patient_uuid)
    if not patient.portal_allowed:
        raise HTTPException(status_code=409, detail="Patient portal access is not enabled")
    account = db.scalar(select(PortalAccount).where(PortalAccount.patient_id == patient.id))
    if account:
        account.username = body.username
        account.password_hash = password_hash.hash(body.temporary_password)
        account.active = True
        account.force_password_reset = True
        account.failed_attempts = 0
        account.locked_until = None
    else:
        account = PortalAccount(patient_id=patient.id, username=body.username, password_hash=password_hash.hash(body.temporary_password))
        db.add(account)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Portal username is already in use")
    db.add(AuditEvent(actor_id=user.id, action="create", resource_type="portal_account", resource_id=account.uuid))
    db.commit()
    db.refresh(account)
    return account_out(account, patient)


@router.get("/patients/{patient_uuid}/portal-account", response_model=PortalAccountOut)
def get_portal_account(patient_uuid: str, db: Session = Depends(get_db), user: User = Depends(communication_user)):
    patient = patient_by_uuid(db, patient_uuid)
    account = db.scalar(select(PortalAccount).where(PortalAccount.patient_id == patient.id))
    if not account:
        raise HTTPException(status_code=404, detail="Portal account not found")
    return account_out(account, patient)


@router.post("/portal/auth/token", response_model=PortalToken)
def portal_login(body: PortalLogin, db: Session = Depends(get_db)) -> PortalToken:
    account = db.scalar(select(PortalAccount).where(PortalAccount.username == body.username))
    current = now_utc()
    locked_until = account.locked_until if account else None
    if locked_until and locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=timezone.utc)
    if not account or not account.active or (locked_until and locked_until > current):
        raise HTTPException(status_code=401, detail="Invalid portal credentials")
    if not password_hash.verify(body.password, account.password_hash):
        account.failed_attempts += 1
        if account.failed_attempts >= 5:
            account.locked_until = current + timedelta(minutes=15)
            account.failed_attempts = 0
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid portal credentials")
    account.failed_attempts = 0
    account.locked_until = None
    account.last_login_at = current
    db.commit()
    return PortalToken(access_token=create_portal_token(account), force_password_reset=account.force_password_reset)


@router.post("/portal/password", status_code=status.HTTP_204_NO_CONTENT)
def change_portal_password(body: PortalPasswordChange, account: PortalAccount = Depends(current_portal_account), db: Session = Depends(get_db)):
    account.password_hash = password_hash.hash(body.new_password)
    account.force_password_reset = False
    account.failed_attempts = 0
    account.locked_until = None
    db.commit()


@router.get("/portal/me")
def portal_me(account: PortalAccount = Depends(portal_ready_account), db: Session = Depends(get_db)):
    patient = db.get(Patient, account.patient_id)
    return {"uuid": patient.uuid, "first_name": patient.first_name, "last_name": patient.last_name, "email": patient.email}


@router.get("/messages", response_model=list[MessageThreadOut])
def list_staff_threads(patient_uuid: str | None = None, thread_status: str | None = Query(default=None, pattern="^(open|closed)$"), db: Session = Depends(get_db), user: User = Depends(communication_user)):
    query = select(MessageThread, Patient).join(Patient, Patient.id == MessageThread.patient_id)
    if patient_uuid:
        query = query.where(Patient.uuid == patient_uuid)
    if thread_status:
        query = query.where(MessageThread.status == thread_status)
    rows = db.execute(query.order_by(MessageThread.updated_at.desc())).all()
    return [thread_out(db, thread, patient, include_messages=False) for thread, patient in rows]


@router.post("/patients/{patient_uuid}/messages", response_model=MessageThreadOut, status_code=status.HTTP_201_CREATED)
def create_staff_thread(body: MessageCreate, patient_uuid: str, db: Session = Depends(get_db), user: User = Depends(communication_write_user)):
    patient = patient_by_uuid(db, patient_uuid)
    thread = MessageThread(patient_id=patient.id, subject=body.subject, assigned_user_id=user.id)
    db.add(thread)
    db.flush()
    message = SecureMessage(thread_id=thread.id, sender_kind="staff", sender_user_id=user.id, sender_name=user.email, body=body.body, read_by_staff_at=now_utc())
    db.add(message)
    db.flush()
    queue_patient_notice(db, patient, message)
    db.add(AuditEvent(actor_id=user.id, action="create", resource_type="message_thread", resource_id=thread.uuid))
    db.commit()
    db.refresh(thread)
    return thread_out(db, thread, patient)


@router.get("/messages/{thread_uuid}", response_model=MessageThreadOut)
def get_staff_thread(thread_uuid: str, db: Session = Depends(get_db), user: User = Depends(communication_user)):
    row = db.execute(select(MessageThread, Patient).join(Patient).where(MessageThread.uuid == thread_uuid)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Message thread not found")
    thread, patient = row
    db.execute(select(SecureMessage).where(SecureMessage.thread_id == thread.id))
    for message in db.scalars(select(SecureMessage).where(SecureMessage.thread_id == thread.id, SecureMessage.read_by_staff_at.is_(None))):
        message.read_by_staff_at = now_utc()
    db.commit()
    return thread_out(db, thread, patient)


@router.post("/messages/{thread_uuid}/replies", response_model=MessageThreadOut)
def staff_reply(body: MessageReply, thread_uuid: str, db: Session = Depends(get_db), user: User = Depends(communication_write_user)):
    row = db.execute(select(MessageThread, Patient).join(Patient).where(MessageThread.uuid == thread_uuid)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Message thread not found")
    thread, patient = row
    if thread.status != "open":
        raise HTTPException(status_code=409, detail="Message thread is closed")
    message = SecureMessage(thread_id=thread.id, sender_kind="staff", sender_user_id=user.id, sender_name=user.email, body=body.body, read_by_staff_at=now_utc())
    db.add(message)
    db.flush()
    thread.updated_at = now_utc()
    queue_patient_notice(db, patient, message)
    db.add(AuditEvent(actor_id=user.id, action="create", resource_type="secure_message", resource_id=message.uuid))
    db.commit()
    return thread_out(db, thread, patient)


@router.patch("/messages/{thread_uuid}/close", response_model=MessageThreadOut)
def close_thread(thread_uuid: str, db: Session = Depends(get_db), user: User = Depends(communication_write_user)):
    row = db.execute(select(MessageThread, Patient).join(Patient).where(MessageThread.uuid == thread_uuid)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Message thread not found")
    thread, patient = row
    thread.status = "closed"
    thread.updated_at = now_utc()
    db.add(AuditEvent(actor_id=user.id, action="update", resource_type="message_thread", resource_id=thread.uuid, detail="status=closed"))
    db.commit()
    return thread_out(db, thread, patient)


@router.get("/portal/messages", response_model=list[MessageThreadOut])
def list_portal_threads(account: PortalAccount = Depends(portal_ready_account), db: Session = Depends(get_db)):
    patient = db.get(Patient, account.patient_id)
    threads = db.scalars(select(MessageThread).where(MessageThread.patient_id == account.patient_id).order_by(MessageThread.updated_at.desc())).all()
    return [thread_out(db, thread, patient, include_messages=False) for thread in threads]


@router.post("/portal/messages", response_model=MessageThreadOut, status_code=status.HTTP_201_CREATED)
def create_portal_thread(body: MessageCreate, account: PortalAccount = Depends(portal_ready_account), db: Session = Depends(get_db)):
    patient = db.get(Patient, account.patient_id)
    thread = MessageThread(patient_id=patient.id, subject=body.subject)
    db.add(thread)
    db.flush()
    db.add(SecureMessage(thread_id=thread.id, sender_kind="patient", sender_portal_account_id=account.id, sender_name=f"{patient.first_name} {patient.last_name}", body=body.body, read_by_patient_at=now_utc()))
    db.commit()
    db.refresh(thread)
    return thread_out(db, thread, patient)


@router.get("/portal/messages/{thread_uuid}", response_model=MessageThreadOut)
def get_portal_thread(thread_uuid: str, account: PortalAccount = Depends(portal_ready_account), db: Session = Depends(get_db)):
    thread, patient = portal_thread(db, account, thread_uuid)
    for message in db.scalars(select(SecureMessage).where(SecureMessage.thread_id == thread.id, SecureMessage.read_by_patient_at.is_(None))):
        message.read_by_patient_at = now_utc()
    db.commit()
    return thread_out(db, thread, patient)


@router.post("/portal/messages/{thread_uuid}/replies", response_model=MessageThreadOut)
def portal_reply(body: MessageReply, thread_uuid: str, account: PortalAccount = Depends(portal_ready_account), db: Session = Depends(get_db)):
    thread, patient = portal_thread(db, account, thread_uuid)
    if thread.status != "open":
        raise HTTPException(status_code=409, detail="Message thread is closed")
    message = SecureMessage(thread_id=thread.id, sender_kind="patient", sender_portal_account_id=account.id, sender_name=f"{patient.first_name} {patient.last_name}", body=body.body, read_by_patient_at=now_utc())
    db.add(message)
    thread.updated_at = now_utc()
    db.commit()
    return thread_out(db, thread, patient)


@router.get("/tasks", response_model=list[ClinicalTaskOut])
def list_tasks(task_status: str | None = Query(default=None, pattern="^(open|completed|cancelled)$"), db: Session = Depends(get_db), user: User = Depends(communication_user)):
    query = select(ClinicalTask, Patient, Encounter, User).join(Patient, Patient.id == ClinicalTask.patient_id).outerjoin(Encounter, Encounter.id == ClinicalTask.encounter_id).outerjoin(User, User.id == ClinicalTask.assigned_to_id)
    if task_status:
        query = query.where(ClinicalTask.status == task_status)
    return [task_out(*row) for row in db.execute(query.order_by(ClinicalTask.due_at, ClinicalTask.id.desc())).all()]


@router.post("/tasks", response_model=ClinicalTaskOut, status_code=status.HTTP_201_CREATED)
def create_task(body: ClinicalTaskCreate, db: Session = Depends(get_db), user: User = Depends(communication_write_user)):
    patient = patient_by_uuid(db, body.patient_uuid)
    encounter = None
    if body.encounter_uuid:
        encounter = db.scalar(select(Encounter).where(Encounter.uuid == body.encounter_uuid, Encounter.patient_id == patient.id))
        if not encounter:
            raise HTTPException(status_code=404, detail="Encounter not found for patient")
    assigned = db.scalar(select(User).where(User.uuid == body.assigned_user_uuid)) if body.assigned_user_uuid else user
    if body.assigned_user_uuid and not assigned:
        raise HTTPException(status_code=404, detail="Assigned user not found")
    task = ClinicalTask(patient_id=patient.id, encounter_id=encounter.id if encounter else None, created_by_id=user.id, assigned_to_id=assigned.id, method=body.method, comment=body.comment, due_at=body.due_at)
    db.add(task)
    db.flush()
    db.add(AuditEvent(actor_id=user.id, action="create", resource_type="clinical_task", resource_id=task.uuid))
    db.commit()
    db.refresh(task)
    return task_out(task, patient, encounter, assigned)


@router.patch("/tasks/{task_uuid}/complete", response_model=ClinicalTaskOut)
def complete_task(task_uuid: str, db: Session = Depends(get_db), user: User = Depends(communication_write_user)):
    row = db.execute(select(ClinicalTask, Patient, Encounter, User).join(Patient, Patient.id == ClinicalTask.patient_id).outerjoin(Encounter, Encounter.id == ClinicalTask.encounter_id).outerjoin(User, User.id == ClinicalTask.assigned_to_id).where(ClinicalTask.uuid == task_uuid)).first()
    if not row:
        raise HTTPException(status_code=404, detail="Clinical task not found")
    task, patient, encounter, assigned = row
    task.status = "completed"
    task.completed_at = now_utc()
    db.add(AuditEvent(actor_id=user.id, action="update", resource_type="clinical_task", resource_id=task.uuid, detail="status=completed"))
    db.commit()
    return task_out(task, patient, encounter, assigned)


@router.get("/communications/outbox", response_model=list[CommunicationDeliveryOut])
def list_outbox(delivery_status: str | None = Query(default=None, pattern="^(pending|sent|failed)$"), db: Session = Depends(get_db), user: User = Depends(administration_user)):
    query = select(CommunicationDelivery)
    if delivery_status:
        query = query.where(CommunicationDelivery.status == delivery_status)
    return list(db.scalars(query.order_by(CommunicationDelivery.queued_at.desc()).limit(500)))


@router.post("/communications/outbox/{delivery_uuid}/retry", response_model=CommunicationDeliveryOut)
def retry_delivery(delivery_uuid: str, db: Session = Depends(get_db), user: User = Depends(administration_user)):
    delivery = db.scalar(select(CommunicationDelivery).where(CommunicationDelivery.uuid == delivery_uuid))
    if not delivery:
        raise HTTPException(status_code=404, detail="Delivery not found")
    if delivery.status == "sent":
        raise HTTPException(status_code=409, detail="Sent delivery cannot be retried")
    delivery.status = "pending"
    delivery.failed_at = None
    delivery.error_message = None
    delivery.queued_at = now_utc()
    db.add(AuditEvent(actor_id=user.id, action="update", resource_type="communication_delivery", resource_id=delivery.uuid, detail="status=pending"))
    db.commit()
    db.refresh(delivery)
    return delivery
