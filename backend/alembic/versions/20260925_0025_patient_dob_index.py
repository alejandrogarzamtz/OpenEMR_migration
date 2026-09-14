"""Index patient birth dates for bounded duplicate review."""
from alembic import op
import sqlalchemy as sa

revision = "20260925_0025"
down_revision = "20260924_0024"
branch_labels = None
depends_on = None


def upgrade():
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("patients")}
    if "ix_patients_date_of_birth" not in indexes:
        op.create_index("ix_patients_date_of_birth", "patients", ["date_of_birth"])


def downgrade():
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("patients")}
    if "ix_patients_date_of_birth" in indexes:
        op.drop_index("ix_patients_date_of_birth", table_name="patients")
