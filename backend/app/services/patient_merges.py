from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from ..db import Base
from ..models import AuthSession, Patient, PatientConsent, PatientCustomFieldValue, PatientMerge, PatientPhoto, PatientRelatedPerson, PortalAccount, User
from .patient_duplicates import duplicate_score

SPECIAL_TABLES = {"patient_custom_field_values", "patient_related_persons", "patient_consents", "portal_accounts"}
RETAINED_ALIAS_TABLES = {"identity_audit_events", "inventory_transactions", "communication_deliveries"}


def json_value(value):
    if isinstance(value, (datetime, date)): return value.isoformat()
    if isinstance(value, Decimal): return str(value)
    if isinstance(value, bytes): return "<binary-preserved-in-source-record>"
    return value


def patient_tables():
    result = []
    for table in Base.metadata.sorted_tables:
        column = table.c.get("patient_id")
        if column is not None and any(foreign_key.target_fullname == "patients.id" for foreign_key in column.foreign_keys):
            result.append(table)
    return result


def overlap_values(db: Session, model, field, source_id: int, target_id: int) -> list[str]:
    source = set(db.scalars(select(field).where(model.patient_id == source_id, field.is_not(None))))
    target = set(db.scalars(select(field).where(model.patient_id == target_id, field.is_not(None))))
    return sorted(source & target)


def custom_value_conflicts(db: Session, source_id: int, target_id: int) -> list[dict]:
    source_rows = {row.definition_id: row for row in db.scalars(select(PatientCustomFieldValue).where(PatientCustomFieldValue.patient_id == source_id))}
    target_ids = set(db.scalars(select(PatientCustomFieldValue.definition_id).where(PatientCustomFieldValue.patient_id == target_id)))
    return [{"type": "custom-field", "source_value_uuid": row.uuid, "definition_id": definition_id, "source_value": row.value_text, "source_kind": row.source, "legacy_value": row.legacy_value, "source_updated_at": json_value(row.updated_at), "source_updated_by_id": row.updated_by_id, "resolution": "target-value-retained; source-value-preserved-in-merge-evidence"} for definition_id, row in source_rows.items() if definition_id in target_ids]


def portal_conflict(db: Session, source_id: int, target_id: int) -> list[dict]:
    source = db.scalar(select(PortalAccount).where(PortalAccount.patient_id == source_id))
    target = db.scalar(select(PortalAccount).where(PortalAccount.patient_id == target_id))
    if not source or not target: return []
    return [{"type": "portal-account", "source_account_uuid": source.uuid, "source_username": source.username, "target_account_uuid": target.uuid, "resolution": "source-account-disabled"}]


def merge_preview(db: Session, source: Patient, target: Patient) -> dict:
    score, fields = duplicate_score(source, target)
    counts = {}
    for table in patient_tables():
        if table.name == "patient_merges": continue
        count = db.scalar(select(func.count()).select_from(table).where(table.c.patient_id == source.id)) or 0
        if count: counts[table.name] = count
    conflicts = custom_value_conflicts(db, source.id, target.id) + portal_conflict(db, source.id, target.id)
    conflicts += [{"type": "related-person", "legacy_source": value, "resolution": "both-records-retained"} for value in overlap_values(db, PatientRelatedPerson, PatientRelatedPerson.legacy_source, source.id, target.id)]
    conflicts += [{"type": "consent", "legacy_field": value, "resolution": "both-records-retained"} for value in overlap_values(db, PatientConsent, PatientConsent.legacy_field, source.id, target.id)]
    conflicts += [{"type": "immutable-records", "table": name, "count": counts[name], "resolution": "retained-on-source-alias"} for name in sorted(RETAINED_ALIAS_TABLES) if counts.get(name)]
    return {"source": source, "target": target, "duplicate_score": score, "matched_fields": fields, "record_counts": counts, "conflicts": conflicts}


def merge_patients(db: Session, source: Patient, target: Patient, actor: User, reason: str) -> PatientMerge:
    preview = merge_preview(db, source, target)
    conflicts = list(preview["conflicts"])

    for model, field in ((PatientRelatedPerson, PatientRelatedPerson.legacy_source), (PatientConsent, PatientConsent.legacy_field)):
        overlaps = overlap_values(db, model, field, source.id, target.id)
        if overlaps:
            db.execute(update(model).where(model.patient_id == source.id, field.in_(overlaps)).values({field.key: None}))

    conflicting_custom_ids = [item["definition_id"] for item in conflicts if item["type"] == "custom-field"]
    if conflicting_custom_ids:
        db.execute(delete(PatientCustomFieldValue).where(PatientCustomFieldValue.patient_id == source.id, PatientCustomFieldValue.definition_id.in_(conflicting_custom_ids)))

    source_portal = db.scalar(select(PortalAccount).where(PortalAccount.patient_id == source.id))
    target_portal = db.scalar(select(PortalAccount).where(PortalAccount.patient_id == target.id))
    if source_portal and target_portal:
        source_portal.active = False
        source_portal.patient_id = None
        db.execute(update(AuthSession).where(AuthSession.portal_account_id == source_portal.id, AuthSession.revoked_at.is_(None)).values(revoked_at=datetime.now(timezone.utc), revoke_reason="patient-chart-merged"))
    elif source_portal:
        source_portal.patient_id = target.id

    moved_counts = {}
    for table in patient_tables():
        if table.name in SPECIAL_TABLES or table.name in RETAINED_ALIAS_TABLES or table.name == "patient_merges": continue
        result = db.execute(update(table).where(table.c.patient_id == source.id).values(patient_id=target.id))
        if result.rowcount: moved_counts[table.name] = result.rowcount
    for table in patient_tables():
        if table.name not in {"patient_custom_field_values", "patient_related_persons", "patient_consents"}: continue
        result = db.execute(update(table).where(table.c.patient_id == source.id).values(patient_id=target.id))
        if result.rowcount: moved_counts[table.name] = result.rowcount
    if source_portal:
        moved_counts["portal_accounts"] = 1

    active_photos = list(db.scalars(select(PatientPhoto).where(PatientPhoto.patient_id == target.id, PatientPhoto.active.is_(True)).order_by(PatientPhoto.is_primary.desc(), PatientPhoto.created_at.desc(), PatientPhoto.id.desc())))
    for index, photo in enumerate(active_photos): photo.is_primary = index == 0

    now = datetime.now(timezone.utc)
    source.merged_into_id = target.id
    source.merged_at = now
    source.merged_by_id = actor.id
    source.merge_reason = reason
    merge = PatientMerge(source_patient_id=source.id, target_patient_id=target.id, source_uuid=source.uuid, target_uuid=target.uuid, reason=reason, duplicate_score=preview["duplicate_score"], matched_fields=preview["matched_fields"], moved_counts=moved_counts, resolved_conflicts=[{key: json_value(value) for key, value in item.items()} for item in conflicts], merged_by_id=actor.id)
    db.add(merge)
    db.flush()
    return merge
