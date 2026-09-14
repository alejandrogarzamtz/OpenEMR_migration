"""Add facilities, practitioners, warehouses, and scoped user access."""

from alembic import op
import sqlalchemy as sa

revision = "20260910_0010"
down_revision = "20260909_0009"
branch_labels = None
depends_on = None

TABLES = ("facilities", "warehouses", "practitioners", "user_facility_access", "practitioner_facility_access")


def upgrade():
    from app.db import Base
    from app import models  # noqa: F401
    bind = op.get_bind()
    for name in TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)
    columns = {column["name"] for column in sa.inspect(bind).get_columns("appointments")}
    if "facility_id" not in columns:
        op.add_column("appointments", sa.Column("facility_id", sa.Integer(), nullable=True))
        op.create_foreign_key("fk_appointments_facility_id", "appointments", "facilities", ["facility_id"], ["id"])
        op.create_index("ix_appointments_facility_id", "appointments", ["facility_id"])


def downgrade():
    from app.db import Base
    from app import models  # noqa: F401
    bind = op.get_bind()
    columns = {column["name"] for column in sa.inspect(bind).get_columns("appointments")}
    if "facility_id" in columns:
        op.drop_index("ix_appointments_facility_id", table_name="appointments")
        op.drop_constraint("fk_appointments_facility_id", "appointments", type_="foreignkey")
        op.drop_column("appointments", "facility_id")
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
