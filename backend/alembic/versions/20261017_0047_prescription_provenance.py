"""Preserve complete pharmacy and prescription provenance."""
from alembic import op
import sqlalchemy as sa

revision="20261017_0047";down_revision="20261016_0046";branch_labels=None;depends_on=None


def upgrade():
    op.add_column("pharmacies",sa.Column("transmit_method",sa.Integer(),nullable=False,server_default="1"))
    op.add_column("pharmacies",sa.Column("legacy_payload",sa.JSON()))
    op.add_column("prescriptions",sa.Column("legacy_patient_id",sa.Integer()))
    op.create_index("ix_prescriptions_legacy_patient_id","prescriptions",["legacy_patient_id"])
    columns=(
        ("modified_at",sa.DateTime(timezone=True),None),("filled_by_legacy_id",sa.Integer(),None),
        ("provider_legacy_id",sa.Integer(),None),("drug_legacy_id",sa.Integer(),None),("form_legacy_id",sa.Integer(),None),
        ("dosage",sa.String(100),None),("size",sa.String(25),None),("unit_legacy_id",sa.Integer(),None),
        ("route",sa.String(100),None),("interval_legacy_id",sa.Integer(),None),("per_refill",sa.Integer(),None),
        ("filled_date",sa.Date(),None),("medication_legacy_id",sa.Integer(),None),("note",sa.Text(),None),
        ("legacy_recorded_at",sa.DateTime(timezone=True),None),("legacy_user",sa.String(50),None),("site",sa.String(50),None),
        ("prescription_guid",sa.String(50),None),("erx_source",sa.Integer(),"0"),("erx_uploaded",sa.Boolean(),sa.false()),
        ("erx_drug_info",sa.Text(),None),("external_id",sa.String(20),None),("prn",sa.String(30),None),
        ("ntx",sa.Integer(),None),("rtx",sa.Integer(),None),("transaction_date",sa.Date(),None),
        ("usage_category",sa.String(100),None),("usage_category_title",sa.String(255),None),
        ("request_intent",sa.String(100),None),("request_intent_title",sa.String(255),None),
        ("diagnosis",sa.Text(),None),("created_by_legacy_id",sa.Integer(),None),("updated_by_legacy_id",sa.Integer(),None),
        ("legacy_payload",sa.JSON(),None),
    )
    for name,type_,default in columns:
        op.add_column("prescriptions",sa.Column(name,type_,nullable=default is None,server_default=default))
    op.alter_column("prescriptions","patient_id",existing_type=sa.Integer(),nullable=True)
    op.alter_column("prescriptions","prescribed_at",existing_type=sa.DateTime(timezone=True),nullable=True)


def downgrade():
    op.alter_column("prescriptions","prescribed_at",existing_type=sa.DateTime(timezone=True),nullable=False)
    op.alter_column("prescriptions","patient_id",existing_type=sa.Integer(),nullable=False)
    for name in ("legacy_payload","updated_by_legacy_id","created_by_legacy_id","diagnosis","request_intent_title","request_intent","usage_category_title","usage_category","transaction_date","rtx","ntx","prn","external_id","erx_drug_info","erx_uploaded","erx_source","prescription_guid","site","legacy_user","legacy_recorded_at","note","medication_legacy_id","filled_date","per_refill","interval_legacy_id","route","unit_legacy_id","size","dosage","form_legacy_id","drug_legacy_id","provider_legacy_id","filled_by_legacy_id","modified_at"):
        op.drop_column("prescriptions",name)
    op.drop_index("ix_prescriptions_legacy_patient_id",table_name="prescriptions")
    op.drop_column("prescriptions","legacy_patient_id")
    op.drop_column("pharmacies","legacy_payload");op.drop_column("pharmacies","transmit_method")
