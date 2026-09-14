"""Add append-only, lossless social-history versions."""
from alembic import op
import sqlalchemy as sa

revision="20261015_0045";down_revision="20261014_0044";branch_labels=None;depends_on=None


def upgrade():
    op.create_table("social_histories",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),
        sa.Column("legacy_history_id",sa.Integer(),nullable=True,unique=True),
        sa.Column("patient_id",sa.Integer(),sa.ForeignKey("patients.id"),nullable=True),
        sa.Column("legacy_patient_id",sa.Integer(),nullable=False,server_default="0"),
        sa.Column("recorded_at",sa.DateTime(timezone=True),nullable=True),
        sa.Column("recorded_by_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=True),
        sa.Column("coffee",sa.Text(),nullable=True),sa.Column("tobacco",sa.Text(),nullable=True),
        sa.Column("alcohol",sa.Text(),nullable=True),sa.Column("sleep_patterns",sa.Text(),nullable=True),
        sa.Column("exercise_patterns",sa.Text(),nullable=True),sa.Column("seatbelt_use",sa.Text(),nullable=True),
        sa.Column("counseling",sa.Text(),nullable=True),sa.Column("hazardous_activities",sa.Text(),nullable=True),
        sa.Column("recreational_drugs",sa.Text(),nullable=True),sa.Column("additional_history",sa.Text(),nullable=True),
        sa.Column("legacy_payload",sa.JSON(),nullable=True))
    for column in ("uuid","patient_id","legacy_patient_id","recorded_at"):
        op.create_index(f"ix_social_histories_{column}","social_histories",[column],unique=column=="uuid")


def downgrade():op.drop_table("social_histories")
