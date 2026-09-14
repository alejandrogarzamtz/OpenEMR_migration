"""Add longitudinal patient practitioner and facility assignments."""
from alembic import op
import sqlalchemy as sa

revision="20261018_0048";down_revision="20261017_0047";branch_labels=None;depends_on=None


def upgrade():
    op.create_table("patient_provider_assignments",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),
        sa.Column("legacy_assignment_key",sa.String(100),unique=True),sa.Column("patient_id",sa.Integer(),sa.ForeignKey("patients.id")),
        sa.Column("legacy_patient_id",sa.Integer(),nullable=False),sa.Column("practitioner_id",sa.Integer(),sa.ForeignKey("practitioners.id")),
        sa.Column("legacy_practitioner_id",sa.Integer()),sa.Column("facility_id",sa.Integer(),sa.ForeignKey("facilities.id")),
        sa.Column("legacy_facility_id",sa.Integer()),sa.Column("role",sa.String(31),nullable=False),
        sa.Column("status",sa.String(31),nullable=False,server_default="active"),sa.Column("assigned_at",sa.DateTime(timezone=True)),
        sa.Column("ended_at",sa.DateTime(timezone=True)),sa.Column("practitioner_name",sa.String(511)),
        sa.Column("facility_name",sa.String(255)),sa.Column("source",sa.String(31),nullable=False,server_default="modern"),
        sa.Column("created_by_id",sa.Integer(),sa.ForeignKey("users.id")),sa.Column("legacy_payload",sa.JSON()))
    for column in ("uuid","patient_id","legacy_patient_id","practitioner_id","legacy_practitioner_id","facility_id","legacy_facility_id","role","status"):
        op.create_index(f"ix_patient_provider_assignments_{column}","patient_provider_assignments",[column],unique=column=="uuid")


def downgrade():op.drop_table("patient_provider_assignments")
