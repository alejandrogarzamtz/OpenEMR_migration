"""Preserve receivable payment-session provenance."""
from alembic import op
import sqlalchemy as sa

revision="20261021_0051";down_revision="20261020_0050";branch_labels=None;depends_on=None


def upgrade():
    columns=(
        sa.Column("legacy_session_id",sa.Integer()),
        sa.Column("payer_id",sa.Integer(),sa.ForeignKey("payers.id")),
        sa.Column("legacy_payer_id",sa.Integer()),
        sa.Column("payment_reference",sa.String(255)),
        sa.Column("check_date",sa.Date()),
        sa.Column("deposit_date",sa.Date()),
        sa.Column("payment_method",sa.String(31)),
    )
    for column in columns:op.add_column("receivable_activities",column)
    for name in ("legacy_session_id","payer_id","legacy_payer_id"):
        op.create_index(f"ix_receivable_activities_{name}","receivable_activities",[name])


def downgrade():
    for name in ("legacy_payer_id","payer_id","legacy_session_id"):
        op.drop_index(f"ix_receivable_activities_{name}",table_name="receivable_activities")
    for name in ("payment_method","deposit_date","check_date","payment_reference","legacy_payer_id","payer_id","legacy_session_id"):
        op.drop_column("receivable_activities",name)
