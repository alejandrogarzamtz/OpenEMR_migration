"""Preserve OpenEMR reference options and insurance types."""
from alembic import op
import sqlalchemy as sa

revision="20261105_0066";down_revision="20261104_0065";branch_labels=None;depends_on=None


def upgrade():
    op.create_table("reference_options",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),sa.Column("list_id",sa.String(100),nullable=False),sa.Column("option_id",sa.String(100),nullable=False),sa.Column("title",sa.String(255),nullable=False),sa.Column("sequence",sa.Integer(),nullable=False,server_default="0"),sa.Column("active",sa.Boolean(),nullable=False,server_default=sa.true()),sa.Column("legacy_payload",sa.JSON(),nullable=True),sa.UniqueConstraint("list_id","option_id",name="uq_reference_option"));op.create_index("ix_reference_options_uuid","reference_options",["uuid"],unique=True);op.create_index("ix_reference_options_list_id","reference_options",["list_id"])
    op.create_table("insurance_types",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("legacy_type_id",sa.Integer(),nullable=False),sa.Column("name",sa.String(255),nullable=False),sa.Column("claim_type",sa.String(30),nullable=True));op.create_index("ix_insurance_types_legacy_type_id","insurance_types",["legacy_type_id"],unique=True)
    op.add_column("payers",sa.Column("legacy_payload",sa.JSON(),nullable=True))


def downgrade():
    op.drop_column("payers","legacy_payload");op.drop_table("insurance_types");op.drop_table("reference_options")
