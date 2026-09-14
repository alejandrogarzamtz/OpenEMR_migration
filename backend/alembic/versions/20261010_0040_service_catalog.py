"""Add normalized service-code catalog with multi-level prices."""
from alembic import op
import sqlalchemy as sa
revision="20261010_0040"
down_revision="20261009_0039"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("service_codes",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),sa.Column("legacy_code_id",sa.Integer(),nullable=True,unique=True),sa.Column("code_type_id",sa.Integer(),nullable=False),sa.Column("code",sa.String(20),nullable=False),sa.Column("modifier",sa.String(12),nullable=False,server_default=""),sa.Column("units",sa.Integer(),nullable=False,server_default="0"),sa.Column("description",sa.Text(),nullable=False),sa.Column("category_code",sa.String(31),nullable=True),sa.Column("category_title",sa.String(255),nullable=True),sa.Column("related_codes",sa.Text(),nullable=True),sa.Column("prices",sa.JSON(),nullable=False),sa.Column("active",sa.Boolean(),nullable=False,server_default=sa.true()),sa.Column("legacy_payload",sa.JSON(),nullable=True),sa.UniqueConstraint("code_type_id","code","modifier",name="uq_service_code_identity"))
    for column in ("uuid","code_type_id","code","category_code","active"):op.create_index(f"ix_service_codes_{column}","service_codes",[column],unique=column=="uuid")

def downgrade():op.drop_table("service_codes")
