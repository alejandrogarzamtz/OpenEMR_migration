"""Preserve standalone receivable sessions and prepayment balances."""
from alembic import op
import sqlalchemy as sa

revision="20261025_0055";down_revision="20261024_0054";branch_labels=None;depends_on=None


def upgrade():
    op.create_table("receivable_sessions",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),sa.Column("legacy_session_id",sa.Integer(),nullable=False),
        sa.Column("patient_id",sa.Integer(),sa.ForeignKey("patients.id")),sa.Column("legacy_patient_id",sa.Integer(),nullable=False),
        sa.Column("payer_id",sa.Integer(),sa.ForeignKey("payers.id")),sa.Column("legacy_payer_id",sa.Integer()),sa.Column("legacy_user_id",sa.Integer()),
        sa.Column("closed",sa.Boolean(),nullable=False),sa.Column("reference",sa.String(255)),sa.Column("check_date",sa.Date()),sa.Column("deposit_date",sa.Date()),
        sa.Column("pay_total",sa.Numeric(12,2),nullable=False),sa.Column("global_amount",sa.Numeric(12,2),nullable=False),sa.Column("payment_type",sa.String(31)),
        sa.Column("description",sa.Text()),sa.Column("adjustment_code",sa.String(31)),sa.Column("post_to_date",sa.Date()),sa.Column("payment_method",sa.String(31)),
        sa.Column("payment_method_label",sa.String(255)),sa.Column("created_at",sa.DateTime(timezone=True)),sa.Column("modified_at",sa.DateTime(timezone=True)),sa.Column("legacy_payload",sa.JSON()))
    for name in ("uuid","legacy_session_id","patient_id","legacy_patient_id","payer_id","legacy_payer_id","closed","check_date","adjustment_code"):
        op.create_index(f"ix_receivable_sessions_{name}","receivable_sessions",[name],unique=name in {"uuid","legacy_session_id"})


def downgrade():op.drop_table("receivable_sessions")
