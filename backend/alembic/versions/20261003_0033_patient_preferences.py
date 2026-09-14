"""Add longitudinal patient clinical preferences."""
from alembic import op
import sqlalchemy as sa

revision = "20261003_0033"
down_revision = "20261002_0032"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "preference_value_sets", sa.Column("id",sa.Integer(),primary_key=True), sa.Column("legacy_value_set_id",sa.Integer(),nullable=True,unique=True),
        sa.Column("observation_code",sa.String(50),nullable=False), sa.Column("answer_code",sa.String(100),nullable=False), sa.Column("answer_system",sa.String(255),nullable=False),
        sa.Column("answer_display",sa.String(255),nullable=False), sa.Column("answer_definition",sa.Text(),nullable=True), sa.Column("sort_order",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("active",sa.Boolean(),nullable=False,server_default=sa.true()), sa.Column("legacy_payload",sa.JSON(),nullable=True),
        sa.UniqueConstraint("observation_code","answer_code","answer_system",name="uq_preference_value_answer"),
    )
    op.create_index("ix_preference_value_sets_observation_code","preference_value_sets",["observation_code"]);op.create_index("ix_preference_value_sets_active","preference_value_sets",["active"])
    op.create_table(
        "patient_preferences", sa.Column("id",sa.Integer(),primary_key=True), sa.Column("uuid",sa.String(36),nullable=False), sa.Column("category",sa.String(32),nullable=False),
        sa.Column("legacy_preference_id",sa.Integer(),nullable=True), sa.Column("patient_id",sa.Integer(),sa.ForeignKey("patients.id"),nullable=False),
        sa.Column("supersedes_id",sa.Integer(),sa.ForeignKey("patient_preferences.id"),nullable=True), sa.Column("observation_code",sa.String(50),nullable=False),
        sa.Column("observation_code_text",sa.String(255),nullable=True), sa.Column("value_type",sa.String(16),nullable=False), sa.Column("value_code",sa.String(100),nullable=True),
        sa.Column("value_code_system",sa.String(255),nullable=True), sa.Column("value_display",sa.String(255),nullable=True), sa.Column("value_text",sa.Text(),nullable=True),
        sa.Column("value_boolean",sa.Boolean(),nullable=True), sa.Column("effective_at",sa.DateTime(timezone=True),nullable=False), sa.Column("status",sa.String(20),nullable=False,server_default="final"),
        sa.Column("note",sa.Text(),nullable=True), sa.Column("amendment_reason",sa.String(255),nullable=True), sa.Column("active",sa.Boolean(),nullable=False,server_default=sa.true()),
        sa.Column("inactivated_reason",sa.String(255),nullable=True), sa.Column("recorded_by_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=True),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False), sa.Column("legacy_payload",sa.JSON(),nullable=True),
        sa.UniqueConstraint("category","legacy_preference_id",name="uq_patient_preference_legacy"),
    )
    for column in ("uuid","category","patient_id","supersedes_id","observation_code","value_type","effective_at","status","active"):op.create_index(f"ix_patient_preferences_{column}","patient_preferences",[column],unique=column=="uuid")


def downgrade():
    op.drop_table("patient_preferences");op.drop_table("preference_value_sets")
