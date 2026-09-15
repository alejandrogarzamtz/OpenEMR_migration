"""Preserve source fields used by multidimensional clinical reports."""
from alembic import op
import sqlalchemy as sa

revision="20261019_0049";down_revision="20261018_0048";branch_labels=None;depends_on=None


def upgrade():
    op.add_column("procedure_order_lines",sa.Column("standard_code",sa.String(255)))
    op.add_column("charges",sa.Column("billed_at",sa.DateTime(timezone=True)))
    op.add_column("charges",sa.Column("legacy_payload",sa.JSON()))
    op.create_index("ix_charges_billed_at","charges",["billed_at"])
    op.add_column("immunizations",sa.Column("dose_unit",sa.String(50)))
    op.add_column("immunizations",sa.Column("legacy_payload",sa.JSON()))


def downgrade():
    op.drop_column("immunizations","legacy_payload")
    op.drop_column("immunizations","dose_unit")
    op.drop_index("ix_charges_billed_at",table_name="charges")
    op.drop_column("charges","legacy_payload")
    op.drop_column("charges","billed_at")
    op.drop_column("procedure_order_lines","standard_code")
