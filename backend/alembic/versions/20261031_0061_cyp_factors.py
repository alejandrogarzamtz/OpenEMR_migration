"""Preserve contraceptive couple-years-of-protection factors."""
from alembic import op
import sqlalchemy as sa

revision="20261031_0061";down_revision="20261030_0060";branch_labels=None;depends_on=None


def upgrade():
    op.add_column("inventory_products",sa.Column("cyp_factor",sa.Numeric(8,4),nullable=False,server_default="0"))
    op.add_column("service_codes",sa.Column("cyp_factor",sa.Numeric(8,4),nullable=False,server_default="0"))


def downgrade():
    op.drop_column("service_codes","cyp_factor")
    op.drop_column("inventory_products","cyp_factor")
