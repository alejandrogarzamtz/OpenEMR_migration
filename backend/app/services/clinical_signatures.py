import hashlib
import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ClinicalForm, ClinicalSignature, User


def canonical_json(value) -> str:
    def encode(item):
        if isinstance(item, datetime):
            if item.tzinfo is None: item = item.replace(tzinfo=timezone.utc)
            return item.astimezone(timezone.utc).isoformat().replace("+00:00","Z")
        return str(item)
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=encode)


def clinical_form_hash(form: ClinicalForm) -> str:
    payload = {"uuid":form.uuid,"patient_id":form.patient_id,"encounter_id":form.encounter_id,"form_type":form.form_type,"title":form.title,"content":form.content,"authored_at":form.authored_at}
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def signature_hash(payload: dict) -> str:
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def form_signatures(db: Session, form_id: int) -> list[ClinicalSignature]:
    return list(db.scalars(select(ClinicalSignature).where(ClinicalSignature.form_id == form_id).order_by(ClinicalSignature.signed_at, ClinicalSignature.id)))


def form_locked(db: Session, form_id: int) -> bool:
    return db.scalar(select(ClinicalSignature.id).where(ClinicalSignature.form_id == form_id, ClinicalSignature.is_lock.is_(True)).limit(1)) is not None


def create_signature(db: Session, form: ClinicalForm, user: User, *, lock: bool, attestation: str, amendment: str | None) -> ClinicalSignature:
    existing = form_signatures(db, form.id)
    content_digest = clinical_form_hash(form)
    previous = existing[-1].signature_hash if existing else None
    signed_at = datetime.now(timezone.utc)
    evidence = {"form_uuid":form.uuid,"encounter_id":form.encounter_id,"signer_id":user.id,"signer_name":user.email,"signer_role":user.role,"signed_at":signed_at,"auth_method":"password","is_lock":lock,"attestation":attestation,"amendment":amendment,"content_hash":content_digest,"previous_signature_hash":previous}
    item = ClinicalSignature(form_id=form.id, encounter_id=form.encounter_id, signer_id=user.id, signer_name=user.email, signer_role=user.role, signed_at=signed_at, auth_method="password", is_lock=lock, attestation=attestation, amendment=amendment, content_hash=content_digest, previous_signature_hash=previous, signature_hash=signature_hash(evidence))
    db.add(item); db.flush(); return item


def verify_signature_chain(form: ClinicalForm, signatures: list[ClinicalSignature]) -> list[bool]:
    current_content_hash = clinical_form_hash(form); previous = None; results = []
    for item in signatures:
        evidence = {"form_uuid":form.uuid,"encounter_id":item.encounter_id,"signer_id":item.signer_id,"signer_name":item.signer_name,"signer_role":item.signer_role,"signed_at":item.signed_at,"auth_method":item.auth_method,"is_lock":item.is_lock,"attestation":item.attestation,"amendment":item.amendment,"content_hash":item.content_hash,"previous_signature_hash":item.previous_signature_hash}
        valid = item.previous_signature_hash == previous and signature_hash(evidence) == item.signature_hash
        if item.is_lock: valid = valid and item.content_hash == current_content_hash
        results.append(valid); previous = item.signature_hash
    return results
