"""Preserve legacy guardian and family demographics on related people."""
from alembic import op
import sqlalchemy as sa

revision = "20260924_0024"
down_revision = "20260923_0023"
branch_labels = None
depends_on = None

COLUMNS = {
    "sex": sa.Column("sex", sa.String(100), nullable=True),
    "address_line1": sa.Column("address_line1", sa.String(255), nullable=True),
    "city": sa.Column("city", sa.String(100), nullable=True),
    "state": sa.Column("state", sa.String(100), nullable=True),
    "postal_code": sa.Column("postal_code", sa.String(30), nullable=True),
    "country": sa.Column("country", sa.String(100), nullable=True),
    "legacy_source": sa.Column("legacy_source", sa.String(100), nullable=True),
    "legacy_payload": sa.Column("legacy_payload", sa.JSON(), nullable=True),
}


def upgrade():
    bind = op.get_bind(); inspector = sa.inspect(bind)
    existing = {column["name"] for column in inspector.get_columns("patient_related_persons")}
    for name, column in COLUMNS.items():
        if name not in existing: op.add_column("patient_related_persons", column)
    unique_sets = {tuple(item["column_names"]) for item in sa.inspect(bind).get_unique_constraints("patient_related_persons")}
    if ("patient_id", "legacy_source") not in unique_sets:
        op.create_unique_constraint("uq_patient_related_person_legacy_source", "patient_related_persons", ["patient_id", "legacy_source"])


def downgrade():
    bind = op.get_bind(); inspector = sa.inspect(bind)
    for constraint in inspector.get_unique_constraints("patient_related_persons"):
        if tuple(constraint["column_names"]) == ("patient_id", "legacy_source") and constraint["name"]:
            op.drop_constraint(constraint["name"], "patient_related_persons", type_="unique")
    existing = {column["name"] for column in sa.inspect(bind).get_columns("patient_related_persons")}
    for name in reversed(COLUMNS):
        if name in existing: op.drop_column("patient_related_persons", name)
