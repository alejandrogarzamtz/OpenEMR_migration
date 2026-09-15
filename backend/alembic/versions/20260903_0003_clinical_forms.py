"""Add normalized, signable clinical forms.

This historical revision is intentionally explicit. Importing live ORM metadata
here would make a clean migration create fields owned by later revisions.
"""
from alembic import op
import sqlalchemy as sa

revision="20260903_0003";down_revision="20260902_0002";branch_labels=None;depends_on=None


def upgrade():
    op.create_table("clinical_forms",
        sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),
        sa.Column("legacy_form_key",sa.String(100),unique=True),sa.Column("patient_id",sa.Integer(),sa.ForeignKey("patients.id"),nullable=False),
        sa.Column("encounter_id",sa.Integer(),sa.ForeignKey("encounters.id"),nullable=False),sa.Column("form_type",sa.String(80),nullable=False),
        sa.Column("title",sa.String(255),nullable=False),sa.Column("content",sa.JSON(),nullable=False),sa.Column("status",sa.String(30),nullable=False),
        sa.Column("authored_at",sa.DateTime(timezone=True),nullable=False),sa.Column("author_id",sa.Integer(),sa.ForeignKey("users.id")),
        sa.Column("signed_at",sa.DateTime(timezone=True)),sa.Column("signed_by_id",sa.Integer(),sa.ForeignKey("users.id")),
        sa.Column("released_to_patient_at",sa.DateTime(timezone=True)),sa.Column("released_by_id",sa.Integer(),sa.ForeignKey("users.id")))
    for name in ("uuid","patient_id","encounter_id","form_type","released_to_patient_at"):
        op.create_index(f"ix_clinical_forms_{name}","clinical_forms",[name],unique=name=="uuid")


def downgrade():op.drop_table("clinical_forms")
