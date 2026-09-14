"""Add normalized external encounter and procedure records."""
from alembic import op
import sqlalchemy as sa

revision = "20261012_0042"
down_revision = "20261011_0041"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "external_encounters",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.String(36), nullable=False),
        sa.Column("legacy_external_encounter_id", sa.Integer(), nullable=True, unique=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("diagnosis", sa.String(255), nullable=True),
        sa.Column("provider_name", sa.String(255), nullable=True),
        sa.Column("facility_name", sa.String(255), nullable=True),
        sa.Column("legacy_provider_id", sa.String(255), nullable=True),
        sa.Column("legacy_facility_id", sa.String(255), nullable=True),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("legacy_payload", sa.JSON(), nullable=True),
    )
    op.create_table(
        "external_procedures",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("uuid", sa.String(36), nullable=False),
        sa.Column("legacy_external_procedure_id", sa.Integer(), nullable=True, unique=True),
        sa.Column("patient_id", sa.Integer(), sa.ForeignKey("patients.id"), nullable=False),
        sa.Column("occurred_on", sa.Date(), nullable=False),
        sa.Column("code_system", sa.String(20), nullable=True),
        sa.Column("code", sa.String(9), nullable=True),
        sa.Column("code_text", sa.Text(), nullable=True),
        sa.Column("legacy_encounter_id", sa.Integer(), nullable=True),
        sa.Column("facility_name", sa.String(255), nullable=True),
        sa.Column("legacy_facility_id", sa.String(255), nullable=True),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("legacy_payload", sa.JSON(), nullable=True),
    )
    for table in ("external_encounters", "external_procedures"):
        for column in ("uuid", "patient_id", "occurred_on", "external_id"):
            op.create_index(f"ix_{table}_{column}", table, [column], unique=column == "uuid")


def downgrade():
    op.drop_table("external_procedures")
    op.drop_table("external_encounters")
