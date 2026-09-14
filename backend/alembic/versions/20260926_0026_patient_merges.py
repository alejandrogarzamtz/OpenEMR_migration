"""Add immutable, reviewed patient chart merges."""
from alembic import op
import sqlalchemy as sa

revision = "20260926_0026"
down_revision = "20260925_0025"
branch_labels = None
depends_on = None

COLUMNS = {
    "merged_into_id": sa.Column("merged_into_id", sa.Integer(), sa.ForeignKey("patients.id"), nullable=True),
    "merged_at": sa.Column("merged_at", sa.DateTime(timezone=True), nullable=True),
    "merged_by_id": sa.Column("merged_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
    "merge_reason": sa.Column("merge_reason", sa.String(500), nullable=True),
}


def upgrade():
    bind = op.get_bind(); inspector = sa.inspect(bind)
    existing = {column["name"] for column in inspector.get_columns("patients")}
    for name, column in COLUMNS.items():
        if name not in existing: op.add_column("patients", column)
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("patients")}
    if "ix_patients_merged_into_id" not in indexes: op.create_index("ix_patients_merged_into_id", "patients", ["merged_into_id"])
    if "ix_patients_merged_at" not in indexes: op.create_index("ix_patients_merged_at", "patients", ["merged_at"])
    from app import models  # noqa: F401
    from app.db import Base
    Base.metadata.tables["patient_merges"].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    from app import models  # noqa: F401
    from app.db import Base
    Base.metadata.tables["patient_merges"].drop(bind=bind, checkfirst=True)
    indexes = {index["name"] for index in sa.inspect(bind).get_indexes("patients")}
    if "ix_patients_merged_at" in indexes: op.drop_index("ix_patients_merged_at", table_name="patients")
    if "ix_patients_merged_into_id" in indexes: op.drop_index("ix_patients_merged_into_id", table_name="patients")
    existing = {column["name"] for column in sa.inspect(bind).get_columns("patients")}
    for name in reversed(COLUMNS):
        if name in existing: op.drop_column("patients", name)
