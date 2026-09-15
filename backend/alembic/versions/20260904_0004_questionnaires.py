"""Add versioned questionnaires and scored responses."""
from alembic import op
import sqlalchemy as sa

revision = "20260904_0004"
down_revision = "20260903_0003"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("questionnaire_definitions",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),sa.Column("code",sa.String(50),nullable=False),sa.Column("version",sa.String(30),nullable=False),sa.Column("title",sa.String(255),nullable=False),sa.Column("questions",sa.JSON(),nullable=False),sa.Column("active",sa.Boolean(),nullable=False))
    op.create_index("ix_questionnaire_definitions_uuid","questionnaire_definitions",["uuid"],unique=True);op.create_index("ix_questionnaire_definitions_code","questionnaire_definitions",["code"])
    op.create_table("questionnaire_responses",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),sa.Column("patient_id",sa.Integer(),sa.ForeignKey("patients.id"),nullable=False),sa.Column("encounter_id",sa.Integer(),sa.ForeignKey("encounters.id"),nullable=True),sa.Column("questionnaire_id",sa.Integer(),sa.ForeignKey("questionnaire_definitions.id"),nullable=False),sa.Column("answers",sa.JSON(),nullable=False),sa.Column("score",sa.Integer(),nullable=False),sa.Column("interpretation",sa.String(100),nullable=False),sa.Column("authored_at",sa.DateTime(timezone=True),nullable=False),sa.Column("author_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=False))
    for column in ("uuid","patient_id","questionnaire_id"):op.create_index(f"ix_questionnaire_responses_{column}","questionnaire_responses",[column],unique=column=="uuid")


def downgrade():
    op.drop_table("questionnaire_responses");op.drop_table("questionnaire_definitions")
