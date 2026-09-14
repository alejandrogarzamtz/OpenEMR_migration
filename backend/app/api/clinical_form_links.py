from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import AuditEvent, ClinicalForm, ClinicalFormDocumentLink, ClinicalFormResultLink, Document, LabOrder, LabResult, User
from ..schemas import ClinicalFormLinkOut, ClinicalFormLinksOut
from ..security import clinical_user
from ..services.clinical_signatures import form_locked
from ..services.patients import patient_by_uuid

router = APIRouter(prefix="/api/v1/patients", tags=["clinical-form-links"])


def scoped_form(db: Session, patient_id: int, form_uuid: str, *, lock: bool = False) -> ClinicalForm:
    query = select(ClinicalForm).where(ClinicalForm.uuid == form_uuid, ClinicalForm.patient_id == patient_id)
    item = db.scalar(query.with_for_update() if lock else query)
    if not item:
        raise HTTPException(status_code=404, detail="Clinical form not found")
    return item


def ensure_mutable(db: Session, item: ClinicalForm) -> None:
    if form_locked(db, item):
        raise HTTPException(status_code=423, detail="Clinical form is electronically signed and locked")


def links_out(db: Session, item: ClinicalForm) -> ClinicalFormLinksOut:
    documents = db.execute(select(ClinicalFormDocumentLink, Document).join(Document).where(ClinicalFormDocumentLink.clinical_form_id == item.id).order_by(ClinicalFormDocumentLink.created_at, ClinicalFormDocumentLink.id)).all()
    results = db.execute(select(ClinicalFormResultLink, LabResult).join(LabResult).where(ClinicalFormResultLink.clinical_form_id == item.id).order_by(ClinicalFormResultLink.created_at, ClinicalFormResultLink.id)).all()
    return ClinicalFormLinksOut(
        documents=[ClinicalFormLinkOut(uuid=target.uuid, label=target.name, linked_at=link.created_at, legacy_clinical_note_id=link.legacy_clinical_note_id) for link, target in documents],
        results=[ClinicalFormLinkOut(uuid=target.uuid, label=f"{target.name}: {target.value}{' ' + target.unit if target.unit else ''}", linked_at=link.created_at, legacy_clinical_note_id=link.legacy_clinical_note_id) for link, target in results],
    )


@router.get("/{patient_uuid}/clinical-forms/{form_uuid}/links", response_model=ClinicalFormLinksOut)
def list_links(patient_uuid: str, form_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid); item = scoped_form(db, patient.id, form_uuid); output = links_out(db, item)
    db.add(AuditEvent(actor_id=user.id, action="read", resource_type="clinical_form_links", resource_id=item.uuid, detail=f"documents={len(output.documents)}; results={len(output.results)}")); db.commit()
    return output


@router.post("/{patient_uuid}/clinical-forms/{form_uuid}/documents/{document_uuid}", response_model=ClinicalFormLinksOut, status_code=201)
def link_document(patient_uuid: str, form_uuid: str, document_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid); item = scoped_form(db, patient.id, form_uuid, lock=True); ensure_mutable(db, item)
    document = db.scalar(select(Document).where(Document.uuid == document_uuid, Document.patient_id == patient.id))
    if not document: raise HTTPException(status_code=404, detail="Document not found")
    if db.scalar(select(ClinicalFormDocumentLink.id).where(ClinicalFormDocumentLink.clinical_form_id == item.id, ClinicalFormDocumentLink.document_id == document.id)): raise HTTPException(status_code=409, detail="Document is already linked")
    db.add(ClinicalFormDocumentLink(clinical_form_id=item.id, document_id=document.id, created_by_id=user.id)); db.add(AuditEvent(actor_id=user.id, action="link", resource_type="clinical_form_document", resource_id=item.uuid, detail=f"document={document.uuid}")); db.commit()
    return links_out(db, item)


@router.delete("/{patient_uuid}/clinical-forms/{form_uuid}/documents/{document_uuid}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_document(patient_uuid: str, form_uuid: str, document_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid); item = scoped_form(db, patient.id, form_uuid, lock=True); ensure_mutable(db, item)
    link = db.scalar(select(ClinicalFormDocumentLink).join(Document).where(ClinicalFormDocumentLink.clinical_form_id == item.id, Document.uuid == document_uuid, Document.patient_id == patient.id))
    if not link: raise HTTPException(status_code=404, detail="Document link not found")
    db.delete(link); db.add(AuditEvent(actor_id=user.id, action="unlink", resource_type="clinical_form_document", resource_id=item.uuid, detail=f"document={document_uuid}")); db.commit(); return Response(status_code=204)


@router.post("/{patient_uuid}/clinical-forms/{form_uuid}/results/{result_uuid}", response_model=ClinicalFormLinksOut, status_code=201)
def link_result(patient_uuid: str, form_uuid: str, result_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid); item = scoped_form(db, patient.id, form_uuid, lock=True); ensure_mutable(db, item)
    result = db.scalar(select(LabResult).join(LabOrder).where(LabResult.uuid == result_uuid, LabOrder.patient_id == patient.id))
    if not result: raise HTTPException(status_code=404, detail="Result not found")
    if db.scalar(select(ClinicalFormResultLink.id).where(ClinicalFormResultLink.clinical_form_id == item.id, ClinicalFormResultLink.lab_result_id == result.id)): raise HTTPException(status_code=409, detail="Result is already linked")
    db.add(ClinicalFormResultLink(clinical_form_id=item.id, lab_result_id=result.id, created_by_id=user.id)); db.add(AuditEvent(actor_id=user.id, action="link", resource_type="clinical_form_result", resource_id=item.uuid, detail=f"result={result.uuid}")); db.commit()
    return links_out(db, item)


@router.delete("/{patient_uuid}/clinical-forms/{form_uuid}/results/{result_uuid}", status_code=status.HTTP_204_NO_CONTENT)
def unlink_result(patient_uuid: str, form_uuid: str, result_uuid: str, db: Session = Depends(get_db), user: User = Depends(clinical_user)):
    patient = patient_by_uuid(db, patient_uuid); item = scoped_form(db, patient.id, form_uuid, lock=True); ensure_mutable(db, item)
    link = db.scalar(select(ClinicalFormResultLink).join(LabResult).join(LabOrder).where(ClinicalFormResultLink.clinical_form_id == item.id, LabResult.uuid == result_uuid, LabOrder.patient_id == patient.id))
    if not link: raise HTTPException(status_code=404, detail="Result link not found")
    db.delete(link); db.add(AuditEvent(actor_id=user.id, action="unlink", resource_type="clinical_form_result", resource_id=item.uuid, detail=f"result={result_uuid}")); db.commit(); return Response(status_code=204)
