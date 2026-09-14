"""Add configurable external patient education resources."""
from alembic import op
import sqlalchemy as sa

revision="20261013_0043";down_revision="20261012_0042";branch_labels=None;depends_on=None

def upgrade():
    op.create_table("patient_education_resources",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),sa.Column("legacy_option_id",sa.String(100),nullable=True,unique=True),sa.Column("name",sa.String(255),nullable=False),sa.Column("url_template",sa.Text(),nullable=False),sa.Column("sequence",sa.Integer(),nullable=False,server_default="0"),sa.Column("active",sa.Boolean(),nullable=False,server_default=sa.true()),sa.Column("legacy_payload",sa.JSON(),nullable=True))
    op.create_index("ix_patient_education_resources_uuid","patient_education_resources",["uuid"],unique=True)
    op.create_index("ix_patient_education_resources_active","patient_education_resources",["active"])

def downgrade():op.drop_table("patient_education_resources")
