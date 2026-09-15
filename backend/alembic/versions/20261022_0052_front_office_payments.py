"""Preserve front-office receipt lines."""
from alembic import op
import sqlalchemy as sa

revision="20261022_0052";down_revision="20261021_0051";branch_labels=None;depends_on=None


def upgrade():
    op.create_table("front_office_payments",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),sa.Column("legacy_payment_id",sa.Integer(),nullable=False),
        sa.Column("patient_id",sa.Integer(),sa.ForeignKey("patients.id")),sa.Column("encounter_id",sa.Integer(),sa.ForeignKey("encounters.id")),
        sa.Column("legacy_patient_id",sa.Integer(),nullable=False),sa.Column("legacy_encounter_id",sa.Integer(),nullable=False),sa.Column("received_at",sa.DateTime(timezone=True),nullable=False),
        sa.Column("actor_name",sa.String(255)),sa.Column("method",sa.String(255)),sa.Column("source",sa.String(255)),
        sa.Column("current_amount",sa.Numeric(12,2),nullable=False),sa.Column("previous_amount",sa.Numeric(12,2),nullable=False),
        sa.Column("posted_current_amount",sa.Numeric(12,2),nullable=False),sa.Column("posted_previous_amount",sa.Numeric(12,2),nullable=False),sa.Column("legacy_payload",sa.JSON()))
    for name in ("uuid","legacy_payment_id","patient_id","encounter_id","legacy_patient_id","legacy_encounter_id","received_at","method"):
        op.create_index(f"ix_front_office_payments_{name}","front_office_payments",[name],unique=name in {"uuid","legacy_payment_id"})


def downgrade():op.drop_table("front_office_payments")
