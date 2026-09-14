"""Add immunizations, vital signs, pharmacies and prescriptions.

This historical migration is deliberately frozen. Importing live ORM metadata
here made clean installations depend on the newest model and caused later
column migrations to fail with duplicate columns.
"""
from alembic import op
import sqlalchemy as sa

revision="20260902_0002";down_revision="20260901_0001";branch_labels=None;depends_on=None


def upgrade():
    op.create_table("immunizations",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),
        sa.Column("legacy_immunization_id",sa.Integer(),unique=True),sa.Column("patient_id",sa.Integer(),sa.ForeignKey("patients.id"),nullable=False),
        sa.Column("encounter_id",sa.Integer(),sa.ForeignKey("encounters.id")),sa.Column("administered_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("cvx_code",sa.String(64),nullable=False),sa.Column("vaccine_name",sa.String(255),nullable=False),
        sa.Column("manufacturer",sa.String(100)),sa.Column("lot_number",sa.String(50)),sa.Column("route",sa.String(100)),
        sa.Column("site",sa.String(100)),sa.Column("dose",sa.String(50)),sa.Column("status",sa.String(30),nullable=False),
        sa.Column("refusal_reason",sa.String(255)),sa.Column("note",sa.Text()))
    op.create_index("ix_immunizations_uuid","immunizations",["uuid"],unique=True)
    op.create_index("ix_immunizations_patient_id","immunizations",["patient_id"])
    op.create_table("vital_sets",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),
        sa.Column("legacy_vitals_id",sa.Integer(),unique=True),sa.Column("patient_id",sa.Integer(),sa.ForeignKey("patients.id"),nullable=False),
        sa.Column("encounter_id",sa.Integer(),sa.ForeignKey("encounters.id")),sa.Column("observed_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("systolic",sa.Numeric(8,2)),sa.Column("diastolic",sa.Numeric(8,2)),sa.Column("weight_kg",sa.Numeric(10,3)),
        sa.Column("height_cm",sa.Numeric(10,3)),sa.Column("temperature_c",sa.Numeric(8,2)),sa.Column("heart_rate",sa.Numeric(8,2)),
        sa.Column("respiratory_rate",sa.Numeric(8,2)),sa.Column("oxygen_saturation",sa.Numeric(6,2)),sa.Column("bmi",sa.Numeric(8,2)),sa.Column("note",sa.String(255)))
    op.create_index("ix_vital_sets_uuid","vital_sets",["uuid"],unique=True)
    op.create_index("ix_vital_sets_patient_id","vital_sets",["patient_id"])
    op.create_index("ix_vital_sets_observed_at","vital_sets",["observed_at"])
    op.create_table("pharmacies",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False,unique=True),
        sa.Column("legacy_pharmacy_id",sa.Integer(),unique=True),sa.Column("name",sa.String(255),nullable=False),
        sa.Column("ncpdp",sa.String(20)),sa.Column("npi",sa.String(20)),sa.Column("email",sa.String(255)))
    op.create_table("prescriptions",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),
        sa.Column("legacy_prescription_id",sa.Integer(),unique=True),sa.Column("patient_id",sa.Integer(),sa.ForeignKey("patients.id"),nullable=False),
        sa.Column("encounter_id",sa.Integer(),sa.ForeignKey("encounters.id")),sa.Column("pharmacy_id",sa.Integer(),sa.ForeignKey("pharmacies.id")),
        sa.Column("prescribed_at",sa.DateTime(timezone=True),nullable=False),sa.Column("start_date",sa.Date()),sa.Column("end_date",sa.Date()),
        sa.Column("drug_name",sa.String(150),nullable=False),sa.Column("rxnorm_code",sa.String(25)),sa.Column("dosage_instructions",sa.Text(),nullable=False),
        sa.Column("quantity",sa.String(31)),sa.Column("refills",sa.Integer(),nullable=False),sa.Column("substitutions_allowed",sa.Boolean(),nullable=False),
        sa.Column("indication",sa.Text()),sa.Column("status",sa.String(30),nullable=False))
    op.create_index("ix_prescriptions_uuid","prescriptions",["uuid"],unique=True)
    op.create_index("ix_prescriptions_patient_id","prescriptions",["patient_id"])


def downgrade():
    for table in ("prescriptions","pharmacies","vital_sets","immunizations"):op.drop_table(table)
