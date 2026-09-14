"""Extend electronic signatures to whole encounters."""
from alembic import op
import sqlalchemy as sa

revision = "20260929_0029"
down_revision = "20260928_0028"
branch_labels = None
depends_on = None


def upgrade():
    bind=op.get_bind(); inspector=sa.inspect(bind)
    columns={column["name"]:column for column in inspector.get_columns("clinical_signatures")}
    if "target_type" not in columns: op.add_column("clinical_signatures",sa.Column("target_type",sa.String(20),nullable=False,server_default="form"))
    if not columns["form_id"]["nullable"]: op.alter_column("clinical_signatures","form_id",existing_type=sa.Integer(),nullable=True)
    indexes={index["name"] for index in sa.inspect(bind).get_indexes("clinical_signatures")}
    if "ix_clinical_signatures_target_type" not in indexes: op.create_index("ix_clinical_signatures_target_type","clinical_signatures",["target_type"])


def downgrade():
    bind=op.get_bind(); indexes={index["name"] for index in sa.inspect(bind).get_indexes("clinical_signatures")}
    if "ix_clinical_signatures_target_type" in indexes: op.drop_index("ix_clinical_signatures_target_type",table_name="clinical_signatures")
    if bind.dialect.name == "postgresql": op.execute("ALTER TABLE clinical_signatures DISABLE TRIGGER clinical_signatures_append_only")
    op.execute("DELETE FROM clinical_signatures WHERE form_id IS NULL")
    if bind.dialect.name == "postgresql": op.execute("ALTER TABLE clinical_signatures ENABLE TRIGGER clinical_signatures_append_only")
    op.alter_column("clinical_signatures","form_id",existing_type=sa.Integer(),nullable=False)
    if "target_type" in {column["name"] for column in sa.inspect(bind).get_columns("clinical_signatures")}: op.drop_column("clinical_signatures","target_type")
