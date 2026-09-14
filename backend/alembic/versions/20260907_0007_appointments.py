"""Expand appointment scheduling, resource, reminder, and legacy data."""

from alembic import op
import sqlalchemy as sa

revision = "20260907_0007"
down_revision = "20260906_0006"
branch_labels = None
depends_on = None

COLUMNS = {
    "legacy_provider_id": sa.Column("legacy_provider_id", sa.Integer(), nullable=True),
    "legacy_facility_id": sa.Column("legacy_facility_id", sa.Integer(), nullable=True),
    "category_id": sa.Column("category_id", sa.Integer(), nullable=True),
    "title": sa.Column("title", sa.String(150), nullable=True),
    "legacy_status": sa.Column("legacy_status", sa.String(15), nullable=True),
    "facility_name": sa.Column("facility_name", sa.String(150), nullable=True),
    "room": sa.Column("room", sa.String(20), nullable=True),
    "location": sa.Column("location", sa.String(255), nullable=True),
    "contact_name": sa.Column("contact_name", sa.String(100), nullable=True),
    "contact_phone": sa.Column("contact_phone", sa.String(50), nullable=True),
    "contact_email": sa.Column("contact_email", sa.String(255), nullable=True),
    "language": sa.Column("language", sa.String(30), nullable=True),
    "all_day": sa.Column("all_day", sa.Boolean(), nullable=False, server_default=sa.false()),
    "recurrence_rule": sa.Column("recurrence_rule", sa.String(500), nullable=True),
    "recurrence_group": sa.Column("recurrence_group", sa.String(36), nullable=True),
    "send_sms": sa.Column("send_sms", sa.Boolean(), nullable=False, server_default=sa.false()),
    "send_email": sa.Column("send_email", sa.Boolean(), nullable=False, server_default=sa.false()),
    "legacy_payload": sa.Column("legacy_payload", sa.JSON(), nullable=True),
}


def upgrade():
    inspector = sa.inspect(op.get_bind())
    existing = {column["name"] for column in inspector.get_columns("appointments")}
    for name, column in COLUMNS.items():
        if name not in existing:
            op.add_column("appointments", column)
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("appointments")}
    for name, column in (
        ("ix_appointments_legacy_provider_id", "legacy_provider_id"),
        ("ix_appointments_legacy_facility_id", "legacy_facility_id"),
        ("ix_appointments_recurrence_group", "recurrence_group"),
    ):
        if name not in indexes:
            op.create_index(name, "appointments", [column])


def downgrade():
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("appointments")}
    for name in ("ix_appointments_recurrence_group", "ix_appointments_legacy_facility_id", "ix_appointments_legacy_provider_id"):
        if name in indexes:
            op.drop_index(name, table_name="appointments")
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("appointments")}
    for name in reversed(COLUMNS):
        if name in existing:
            op.drop_column("appointments", name)

