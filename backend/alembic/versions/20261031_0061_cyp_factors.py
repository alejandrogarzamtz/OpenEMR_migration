"""Preserve contraceptive couple-years-of-protection factors."""
from alembic import op
import sqlalchemy as sa

revision="20261031_0061";down_revision="20261030_0060";branch_labels=None;depends_on=None


def upgrade():
    inspector=sa.inspect(op.get_bind())
    if "cyp_factor" not in {column["name"] for column in inspector.get_columns("inventory_products")}:
        op.add_column("inventory_products",sa.Column("cyp_factor",sa.Numeric(8,4),nullable=False,server_default="0"))
    if "cyp_factor" not in {column["name"] for column in inspector.get_columns("service_codes")}:
        op.add_column("service_codes",sa.Column("cyp_factor",sa.Numeric(8,4),nullable=False,server_default="0"))


def downgrade():
    inspector=sa.inspect(op.get_bind())
    if "cyp_factor" in {column["name"] for column in inspector.get_columns("service_codes")}:op.drop_column("service_codes","cyp_factor")
    if "cyp_factor" in {column["name"] for column in inspector.get_columns("inventory_products")}:op.drop_column("inventory_products","cyp_factor")
