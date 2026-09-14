import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ClinicalForm, ClinicalFormDocumentLink, ClinicalFormResultLink, ClinicalSignature, Document, Encounter, LabResult, User


def canonical_json(value) -> str:
    def encode(item):
        if isinstance(item, datetime):
            if item.tzinfo is None: item = item.replace(tzinfo=timezone.utc)
            return item.astimezone(timezone.utc).isoformat().replace("+00:00","Z")
        return str(item)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=encode)


def clinical_form_hash(form: ClinicalForm, db: Session | None = None) -> str:
    payload = {"uuid":form.uuid,"patient_id":form.patient_id,"encounter_id":form.encounter_id,"form_type":form.form_type,"title":form.title,"content":form.content,"authored_at":form.authored_at}
    if db is not None:
        payload["linked_documents"] = sorted(db.scalars(select(Document.uuid).join(ClinicalFormDocumentLink).where(ClinicalFormDocumentLink.clinical_form_id == form.id)))
        payload["linked_results"] = sorted(db.scalars(select(LabResult.uuid).join(ClinicalFormResultLink).where(ClinicalFormResultLink.clinical_form_id == form.id)))
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def signature_hash(payload: dict) -> str:
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def form_signatures(db: Session, form_id: int) -> list[ClinicalSignature]:
    return list(db.scalars(select(ClinicalSignature).where(ClinicalSignature.target_type == "form", ClinicalSignature.form_id == form_id).order_by(ClinicalSignature.signed_at, ClinicalSignature.id)))


def encounter_signatures(db: Session, encounter_id: int) -> list[ClinicalSignature]:
    return list(db.scalars(select(ClinicalSignature).where(ClinicalSignature.target_type == "encounter", ClinicalSignature.encounter_id == encounter_id).order_by(ClinicalSignature.signed_at, ClinicalSignature.id)))


def encounter_locked(db: Session, encounter_id: int) -> bool:
    return db.scalar(select(ClinicalSignature.id).where(ClinicalSignature.target_type == "encounter", ClinicalSignature.encounter_id == encounter_id, ClinicalSignature.is_lock.is_(True)).limit(1)) is not None


def form_locked(db: Session, form: ClinicalForm) -> bool:
    own_lock = db.scalar(select(ClinicalSignature.id).where(ClinicalSignature.target_type == "form", ClinicalSignature.form_id == form.id, ClinicalSignature.is_lock.is_(True)).limit(1)) is not None
    return own_lock or encounter_locked(db, form.encounter_id)


def encounter_hash(db: Session, encounter: Encounter) -> str:
    forms=list(db.scalars(select(ClinicalForm).where(ClinicalForm.encounter_id==encounter.id).order_by(ClinicalForm.id)))
    payload={"uuid":encounter.uuid,"patient_id":encounter.patient_id,"occurred_at":encounter.occurred_at,"type":encounter.type,"status":encounter.status,"chief_complaint":encounter.chief_complaint,"clinical_note":encounter.clinical_note,"forms":[{"uuid":form.uuid,"hash":clinical_form_hash(form,db)} for form in forms]}
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def create_signature(db: Session, form: ClinicalForm, user: User, *, lock: bool, attestation: str, amendment: str | None) -> ClinicalSignature:
    existing = form_signatures(db, form.id)
    content_digest = clinical_form_hash(form, db)
    previous = existing[-1].signature_hash if existing else None
    signed_at = datetime.now(timezone.utc)
    evidence = {"form_uuid":form.uuid,"encounter_id":form.encounter_id,"signer_id":user.id,"signer_name":user.email,"signer_role":user.role,"signed_at":signed_at,"auth_method":"password","is_lock":lock,"attestation":attestation,"amendment":amendment,"content_hash":content_digest,"previous_signature_hash":previous}
    item = ClinicalSignature(target_type="form", form_id=form.id, encounter_id=form.encounter_id, signer_id=user.id, signer_name=user.email, signer_role=user.role, signed_at=signed_at, auth_method="password", is_lock=lock, attestation=attestation, amendment=amendment, content_hash=content_digest, previous_signature_hash=previous, signature_hash=signature_hash(evidence))
    db.add(item); db.flush(); return item


def verify_signature_chain(db: Session, form: ClinicalForm, signatures: list[ClinicalSignature]) -> list[bool]:
    current_content_hash = clinical_form_hash(form, db); previous = None; results = []
    for item in signatures:
        evidence = {"form_uuid":form.uuid,"encounter_id":item.encounter_id,"signer_id":item.signer_id,"signer_name":item.signer_name,"signer_role":item.signer_role,"signed_at":item.signed_at,"auth_method":item.auth_method,"is_lock":item.is_lock,"attestation":item.attestation,"amendment":item.amendment,"content_hash":item.content_hash,"previous_signature_hash":item.previous_signature_hash}
        valid = item.previous_signature_hash == previous and signature_hash(evidence) == item.signature_hash
        if item.is_lock: valid = valid and item.content_hash == current_content_hash
        results.append(valid); previous = item.signature_hash
    return results


def create_encounter_signature(db: Session, encounter: Encounter, user: User, *, lock: bool, attestation: str, amendment: str | None) -> ClinicalSignature:
    existing=encounter_signatures(db,encounter.id); previous=existing[-1].signature_hash if existing else None; signed_at=datetime.now(timezone.utc); content_digest=encounter_hash(db,encounter)
    evidence={"encounter_uuid":encounter.uuid,"signer_id":user.id,"signer_name":user.email,"signer_role":user.role,"signed_at":signed_at,"auth_method":"password","is_lock":lock,"attestation":attestation,"amendment":amendment,"content_hash":content_digest,"previous_signature_hash":previous}
    item=ClinicalSignature(target_type="encounter",encounter_id=encounter.id,signer_id=user.id,signer_name=user.email,signer_role=user.role,signed_at=signed_at,auth_method="password",is_lock=lock,attestation=attestation,amendment=amendment,content_hash=content_digest,previous_signature_hash=previous,signature_hash=signature_hash(evidence));db.add(item);db.flush();return item


def verify_encounter_signature_chain(db: Session, encounter: Encounter, signatures: list[ClinicalSignature]) -> list[bool]:
    current=encounter_hash(db,encounter);previous=None;results=[]
    for item in signatures:
        evidence={"encounter_uuid":encounter.uuid,"signer_id":item.signer_id,"signer_name":item.signer_name,"signer_role":item.signer_role,"signed_at":item.signed_at,"auth_method":item.auth_method,"is_lock":item.is_lock,"attestation":item.attestation,"amendment":item.amendment,"content_hash":item.content_hash,"previous_signature_hash":item.previous_signature_hash}
        valid=item.previous_signature_hash==previous and signature_hash(evidence)==item.signature_hash
        if item.is_lock:valid=valid and item.content_hash==current
        results.append(valid);previous=item.signature_hash
    return results
