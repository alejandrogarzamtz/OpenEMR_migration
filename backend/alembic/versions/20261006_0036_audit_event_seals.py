"""Add independent integrity seals for staff and identity audit events."""

from datetime import datetime, timezone
import hashlib
import json

from alembic import op
import sqlalchemy as sa

revision = "20261006_0036"
down_revision = "20261005_0035"
branch_labels = None
depends_on = None


def audit_time(value) -> str:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def checksum(values: dict) -> str:
    canonical = json.dumps(values, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha3_512(canonical.encode()).hexdigest()


def upgrade():
    op.create_table(
        "audit_event_seals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("stream", sa.String(length=20), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("checksum", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("stream", "event_id", name="uq_audit_event_seal_stream_event"),
    )
    op.create_index("ix_audit_event_seals_stream", "audit_event_seals", ["stream"])
    op.create_index("ix_audit_event_seals_event_id", "audit_event_seals", ["event_id"])
    op.create_index("ix_audit_event_seals_created_at", "audit_event_seals", ["created_at"])
    bind = op.get_bind()
    now = datetime.now(timezone.utc)
    staff = bind.execute(sa.text("SELECT id, occurred_at, actor_id, action, resource_type, resource_id, detail FROM audit_events ORDER BY id")).mappings()
    identity = bind.execute(sa.text("SELECT id, occurred_at, identity_kind, user_id, portal_account_id, patient_id, action, resource_type, resource_id, detail FROM identity_audit_events ORDER BY id")).mappings()
    rows = []
    for item in staff:
        values = {key: item[key] for key in ("occurred_at", "actor_id", "action", "resource_type", "resource_id", "detail")}
        values["occurred_at"] = audit_time(values["occurred_at"])
        rows.append({"stream": "staff", "event_id": item["id"], "checksum": checksum(values), "created_at": now})
    for item in identity:
        values = {key: item[key] for key in ("occurred_at", "identity_kind", "user_id", "portal_account_id", "patient_id", "action", "resource_type", "resource_id", "detail")}
        values["occurred_at"] = audit_time(values["occurred_at"])
        rows.append({"stream": "identity", "event_id": item["id"], "checksum": checksum(values), "created_at": now})
    if rows:
        table = sa.table("audit_event_seals", sa.column("stream"), sa.column("event_id"), sa.column("checksum"), sa.column("created_at"))
        op.bulk_insert(table, rows)


def downgrade():
    op.drop_index("ix_audit_event_seals_created_at", table_name="audit_event_seals")
    op.drop_index("ix_audit_event_seals_event_id", table_name="audit_event_seals")
    op.drop_index("ix_audit_event_seals_stream", table_name="audit_event_seals")
    op.drop_table("audit_event_seals")
