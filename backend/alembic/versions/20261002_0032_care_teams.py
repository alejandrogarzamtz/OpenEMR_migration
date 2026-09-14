"""Add patient care teams and polymorphic members."""
from alembic import op
import sqlalchemy as sa

revision = "20261002_0032"
down_revision = "20261001_0031"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "care_teams", sa.Column("id",sa.Integer(),primary_key=True), sa.Column("uuid",sa.String(36),nullable=False),
        sa.Column("legacy_care_team_id",sa.Integer(),nullable=True,unique=True), sa.Column("patient_id",sa.Integer(),sa.ForeignKey("patients.id"),nullable=False),
        sa.Column("name",sa.String(255),nullable=False), sa.Column("status",sa.String(32),nullable=False,server_default="active"), sa.Column("note",sa.Text(),nullable=True), sa.Column("inactivated_reason",sa.String(255),nullable=True),
        sa.Column("created_by_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=True), sa.Column("updated_by_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=True),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False), sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False), sa.Column("legacy_payload",sa.JSON(),nullable=True),
    )
    op.create_index("ix_care_teams_uuid","care_teams",["uuid"],unique=True);op.create_index("ix_care_teams_patient_id","care_teams",["patient_id"]);op.create_index("ix_care_teams_status","care_teams",["status"])
    op.create_table(
        "care_team_members", sa.Column("id",sa.Integer(),primary_key=True), sa.Column("uuid",sa.String(36),nullable=False), sa.Column("legacy_member_id",sa.Integer(),nullable=True,unique=True),
        sa.Column("care_team_id",sa.Integer(),sa.ForeignKey("care_teams.id"),nullable=False), sa.Column("practitioner_id",sa.Integer(),sa.ForeignKey("practitioners.id"),nullable=True), sa.Column("facility_id",sa.Integer(),sa.ForeignKey("facilities.id"),nullable=True),
        sa.Column("legacy_user_id",sa.Integer(),nullable=True), sa.Column("legacy_facility_id",sa.Integer(),nullable=True), sa.Column("legacy_contact_id",sa.Integer(),nullable=True),
        sa.Column("member_type",sa.String(20),nullable=False), sa.Column("display_name",sa.String(255),nullable=False), sa.Column("role",sa.String(50),nullable=False), sa.Column("provider_since",sa.Date(),nullable=True),
        sa.Column("status",sa.String(32),nullable=False,server_default="active"), sa.Column("note",sa.Text(),nullable=True), sa.Column("inactivated_reason",sa.String(255),nullable=True),
        sa.Column("created_by_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=True), sa.Column("updated_by_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=True),
        sa.Column("created_at",sa.DateTime(timezone=True),nullable=False), sa.Column("updated_at",sa.DateTime(timezone=True),nullable=False), sa.Column("legacy_payload",sa.JSON(),nullable=True),
    )
    for column in ("uuid","care_team_id","practitioner_id","facility_id","member_type","role","status"):op.create_index(f"ix_care_team_members_{column}","care_team_members",[column],unique=column=="uuid")


def downgrade():
    op.drop_table("care_team_members");op.drop_table("care_teams")
