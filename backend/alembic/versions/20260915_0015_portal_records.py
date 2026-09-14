"""Add controlled patient-portal record publication and identity audit."""

from alembic import op
import sqlalchemy as sa

revision = "20260915_0015"
down_revision = "20260914_0014"
branch_labels = None
depends_on = None

RELEASE_TABLES = ("lab_results", "documents", "clinical_forms")


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table in RELEASE_TABLES:
        existing = {column["name"] for column in inspector.get_columns(table)}
        if "released_to_patient_at" not in existing:
            op.add_column(table, sa.Column("released_to_patient_at", sa.DateTime(timezone=True), nullable=True))
            op.create_index(f"ix_{table}_released_to_patient_at", table, ["released_to_patient_at"])
        if "released_by_id" not in existing:
            op.add_column(table, sa.Column("released_by_id", sa.Integer(), nullable=True))
            op.create_foreign_key(f"fk_{table}_released_by_id_users", table, "users", ["released_by_id"], ["id"])

    from app import models  # noqa: F401
    from app.db import Base

    Base.metadata.tables["identity_audit_events"].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    from app import models  # noqa: F401
    from app.db import Base

    Base.metadata.tables["identity_audit_events"].drop(bind=bind, checkfirst=True)
    for table in reversed(RELEASE_TABLES):
        op.drop_constraint(f"fk_{table}_released_by_id_users", table, type_="foreignkey")
        op.drop_column(table, "released_by_id")
        op.drop_index(f"ix_{table}_released_to_patient_at", table_name=table)
        op.drop_column(table, "released_to_patient_at")
