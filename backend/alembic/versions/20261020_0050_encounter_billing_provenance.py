"""Preserve encounter, billing-code and receivable provenance."""
from alembic import op
import sqlalchemy as sa

revision="20261020_0050";down_revision="20261019_0049";branch_labels=None;depends_on=None


def upgrade():
    for column in (
        sa.Column("practitioner_id",sa.Integer(),sa.ForeignKey("practitioners.id")),
        sa.Column("legacy_provider_id",sa.Integer()),sa.Column("provider_name",sa.String(511)),
        sa.Column("facility_id",sa.Integer(),sa.ForeignKey("facilities.id")),
        sa.Column("legacy_facility_id",sa.Integer()),sa.Column("facility_name",sa.String(255)),
        sa.Column("authorized",sa.Boolean()),sa.Column("legacy_payload",sa.JSON()),
    ):op.add_column("encounters",column)
    for name in ("practitioner_id","legacy_provider_id","facility_id","legacy_facility_id"):
        op.create_index(f"ix_encounters_{name}","encounters",[name])
    op.add_column("charges",sa.Column("modifier",sa.String(12)))
    op.add_column("charges",sa.Column("authorized",sa.Boolean(),nullable=False,server_default=sa.true()))
    op.add_column("charges",sa.Column("billed",sa.Boolean(),nullable=False,server_default=sa.false()))
    op.add_column("charges",sa.Column("justification",sa.String(255)))
    op.add_column("charges",sa.Column("active",sa.Boolean(),nullable=False,server_default=sa.true()))
    op.create_index("ix_charges_billed","charges",["billed"])
    op.create_index("ix_charges_active","charges",["active"])
    op.add_column("clinical_forms",sa.Column("source_formdir",sa.String(255)))
    op.add_column("clinical_forms",sa.Column("registry_payload",sa.JSON()))
    op.create_index("ix_clinical_forms_source_formdir","clinical_forms",["source_formdir"])
    op.create_table("billing_code_types",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("key",sa.String(15),nullable=False),
        sa.Column("legacy_type_id",sa.Integer(),nullable=False),sa.Column("sequence",sa.Integer(),nullable=False),
        sa.Column("fee",sa.Boolean(),nullable=False),sa.Column("justification_type",sa.String(15)),
        sa.Column("diagnosis",sa.Boolean(),nullable=False),sa.Column("procedure",sa.Boolean(),nullable=False),
        sa.Column("active",sa.Boolean(),nullable=False),sa.Column("label",sa.String(31)),sa.Column("legacy_payload",sa.JSON()))
    op.create_index("ix_billing_code_types_key","billing_code_types",["key"],unique=True)
    op.create_index("ix_billing_code_types_legacy_type_id","billing_code_types",["legacy_type_id"],unique=True)
    op.create_index("ix_billing_code_types_active","billing_code_types",["active"])
    op.create_table("receivable_activities",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),
        sa.Column("patient_id",sa.Integer(),sa.ForeignKey("patients.id")),sa.Column("encounter_id",sa.Integer(),sa.ForeignKey("encounters.id")),
        sa.Column("legacy_patient_id",sa.Integer(),nullable=False),sa.Column("legacy_encounter_id",sa.Integer(),nullable=False),
        sa.Column("legacy_sequence",sa.Integer(),nullable=False),sa.Column("payer_type",sa.Integer(),nullable=False),
        sa.Column("account_code",sa.String(15),nullable=False),sa.Column("code_system",sa.String(12)),
        sa.Column("code",sa.String(20)),sa.Column("modifier",sa.String(12)),
        sa.Column("pay_amount",sa.Numeric(12,2),nullable=False),sa.Column("adjustment_amount",sa.Numeric(12,2),nullable=False),
        sa.Column("posted_at",sa.DateTime(timezone=True),nullable=False),sa.Column("deleted_at",sa.DateTime(timezone=True)),
        sa.Column("legacy_payload",sa.JSON()),sa.UniqueConstraint("legacy_patient_id","legacy_encounter_id","legacy_sequence",name="uq_receivable_legacy_activity"))
    for name in ("uuid","patient_id","encounter_id","legacy_patient_id","legacy_encounter_id","posted_at","deleted_at"):
        op.create_index(f"ix_receivable_activities_{name}","receivable_activities",[name],unique=name=="uuid")


def downgrade():
    op.drop_table("receivable_activities");op.drop_table("billing_code_types")
    op.execute("DROP INDEX IF EXISTS ix_clinical_forms_source_formdir")
    op.execute("ALTER TABLE clinical_forms DROP COLUMN IF EXISTS registry_payload")
    op.execute("ALTER TABLE clinical_forms DROP COLUMN IF EXISTS source_formdir")
    op.execute("DROP INDEX IF EXISTS ix_charges_active");op.drop_index("ix_charges_billed",table_name="charges")
    op.execute("ALTER TABLE charges DROP COLUMN IF EXISTS active")
    for name in ("justification","billed","authorized","modifier"):op.drop_column("charges",name)
    for name in ("practitioner_id","legacy_provider_id","facility_id","legacy_facility_id"):
        op.drop_index(f"ix_encounters_{name}",table_name="encounters")
    for name in ("legacy_payload","authorized","facility_name","legacy_facility_id","facility_id","provider_name","legacy_provider_id","practitioner_id"):
        op.drop_column("encounters",name)
