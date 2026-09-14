"""Add explicit portal billing release and idempotent payment intents."""

from alembic import op
import sqlalchemy as sa

revision = "20260916_0016"
down_revision = "20260915_0015"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing = {column["name"] for column in inspector.get_columns("claims")}
    if "released_to_patient_at" not in existing:
        op.add_column("claims", sa.Column("released_to_patient_at", sa.DateTime(timezone=True), nullable=True))
        op.create_index("ix_claims_released_to_patient_at", "claims", ["released_to_patient_at"])
    if "released_by_id" not in existing:
        op.add_column("claims", sa.Column("released_by_id", sa.Integer(), nullable=True))
        op.create_foreign_key("fk_claims_released_by_id_users", "claims", "users", ["released_by_id"], ["id"])

    from app import models  # noqa: F401
    from app.db import Base

    Base.metadata.tables["payment_intents"].create(bind=bind, checkfirst=True)


def downgrade():
    bind = op.get_bind()
    from app import models  # noqa: F401
    from app.db import Base

    Base.metadata.tables["payment_intents"].drop(bind=bind, checkfirst=True)
    op.drop_constraint("fk_claims_released_by_id_users", "claims", type_="foreignkey")
    op.drop_column("claims", "released_by_id")
    op.drop_index("ix_claims_released_to_patient_at", table_name="claims")
    op.drop_column("claims", "released_to_patient_at")
