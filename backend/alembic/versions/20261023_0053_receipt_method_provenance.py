"""Preserve receipt-method reporting fields."""
from alembic import op
import sqlalchemy as sa

revision="20261023_0053";down_revision="20261022_0052";branch_labels=None;depends_on=None


def upgrade():
    for column in (sa.Column("payment_method_label",sa.String(255)),sa.Column("memo",sa.String(255)),sa.Column("follow_up_note",sa.Text()),sa.Column("reason_code",sa.String(255)),sa.Column("post_date",sa.Date()),sa.Column("payer_claim_number",sa.String(30))):op.add_column("receivable_activities",column)


def downgrade():
    for name in ("payer_claim_number","post_date","reason_code","follow_up_note","memo","payment_method_label"):op.drop_column("receivable_activities",name)
