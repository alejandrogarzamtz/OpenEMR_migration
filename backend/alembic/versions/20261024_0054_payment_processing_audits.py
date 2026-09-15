"""Preserve payment gateway audit and reversal provenance."""
from alembic import op
import sqlalchemy as sa

revision="20261024_0054";down_revision="20261023_0053";branch_labels=None;depends_on=None


def upgrade():
    op.create_table("payment_processing_audits",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),sa.Column("legacy_uuid_hex",sa.String(32),nullable=False),
        sa.Column("service",sa.String(50)),sa.Column("patient_id",sa.Integer(),sa.ForeignKey("patients.id")),sa.Column("legacy_patient_id",sa.Integer(),nullable=False),
        sa.Column("success",sa.Boolean(),nullable=False),sa.Column("action_name",sa.String(50)),sa.Column("amount_text",sa.String(20)),sa.Column("amount",sa.Numeric(12,2)),
        sa.Column("ticket",sa.String(100)),sa.Column("transaction_id",sa.String(100)),sa.Column("occurred_at",sa.DateTime(timezone=True)),
        sa.Column("map_legacy_uuid_hex",sa.String(32)),sa.Column("map_transaction_id",sa.String(100)),sa.Column("reverted",sa.Boolean(),nullable=False),
        sa.Column("revert_action_name",sa.String(50)),sa.Column("revert_transaction_id",sa.String(100)),sa.Column("reverted_at",sa.DateTime(timezone=True)),
        sa.Column("audit_ciphertext",sa.Text()),sa.Column("revert_audit_ciphertext",sa.Text()),sa.Column("audit_payload",sa.JSON()),sa.Column("revert_audit_payload",sa.JSON()),sa.Column("payload_readable",sa.Boolean(),nullable=False),sa.Column("legacy_payload",sa.JSON()))
    for name in ("uuid","legacy_uuid_hex","service","patient_id","legacy_patient_id","success","action_name","ticket","transaction_id","occurred_at","map_legacy_uuid_hex","reverted"):
        op.create_index(f"ix_payment_processing_audits_{name}","payment_processing_audits",[name],unique=name in {"uuid","legacy_uuid_hex"})


def downgrade():op.drop_table("payment_processing_audits")
