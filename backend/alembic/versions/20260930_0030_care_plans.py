"""Add relational longitudinal care plans."""
from alembic import op
import sqlalchemy as sa

revision = "20260930_0030"
down_revision = "20260929_0029"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "care_plans",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),
        sa.Column("legacy_form_id",sa.Integer(),nullable=True),sa.Column("legacy_row_key",sa.String(100),nullable=True),
        sa.Column("patient_id",sa.Integer(),sa.ForeignKey("patients.id"),nullable=False),sa.Column("encounter_id",sa.Integer(),sa.ForeignKey("encounters.id"),nullable=False),sa.Column("author_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=True),
        sa.Column("recorded_at",sa.DateTime(timezone=True),nullable=False),sa.Column("code",sa.String(255),nullable=True),sa.Column("code_text",sa.Text(),nullable=True),sa.Column("description",sa.Text(),nullable=False),
        sa.Column("external_id",sa.String(30),nullable=True),sa.Column("plan_type",sa.String(30),nullable=True),sa.Column("note_related_to",sa.Text(),nullable=True),sa.Column("ends_at",sa.DateTime(timezone=True),nullable=True),
        sa.Column("reason_code",sa.String(31),nullable=True),sa.Column("reason_description",sa.Text(),nullable=True),sa.Column("reason_recorded_at",sa.DateTime(timezone=True),nullable=True),sa.Column("reason_ends_at",sa.DateTime(timezone=True),nullable=True),sa.Column("reason_status",sa.String(31),nullable=True),
        sa.Column("status",sa.String(32),nullable=False,server_default="draft"),sa.Column("target_date",sa.DateTime(timezone=True),nullable=True),sa.Column("engagement_category",sa.String(100),nullable=True),sa.Column("active",sa.Boolean(),nullable=False,server_default=sa.true()),
        sa.Column("legacy_payload",sa.JSON(),nullable=True),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint("legacy_form_id","legacy_row_key",name="uq_care_plan_legacy_row"),
    )
    for name, columns in (("ix_care_plans_uuid",["uuid"]),("ix_care_plans_legacy_form_id",["legacy_form_id"]),("ix_care_plans_patient_id",["patient_id"]),("ix_care_plans_encounter_id",["encounter_id"]),("ix_care_plans_recorded_at",["recorded_at"]),("ix_care_plans_code",["code"]),("ix_care_plans_status",["status"]),("ix_care_plans_active",["active"])):
        op.create_index(name,"care_plans",columns,unique=name=="ix_care_plans_uuid")


def downgrade():
    op.drop_table("care_plans")
