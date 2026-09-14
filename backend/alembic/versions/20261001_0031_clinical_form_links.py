"""Link clinical forms to documents and procedure results."""
from alembic import op
import sqlalchemy as sa

revision = "20261001_0031"
down_revision = "20260930_0030"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "clinical_form_document_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("legacy_link_id", sa.Integer(), nullable=True, unique=True),
        sa.Column("legacy_clinical_note_id", sa.Integer(), nullable=True),
        sa.Column("clinical_form_id", sa.Integer(), sa.ForeignKey("clinical_forms.id"), nullable=False),
        sa.Column("document_id", sa.Integer(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_by_name", sa.String(255), nullable=True),
        sa.UniqueConstraint("clinical_form_id", "document_id", "legacy_clinical_note_id", name="uq_clinical_form_document"),
    )
    op.create_table(
        "clinical_form_result_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("legacy_link_id", sa.Integer(), nullable=True, unique=True),
        sa.Column("legacy_clinical_note_id", sa.Integer(), nullable=True),
        sa.Column("clinical_form_id", sa.Integer(), sa.ForeignKey("clinical_forms.id"), nullable=False),
        sa.Column("lab_result_id", sa.Integer(), sa.ForeignKey("lab_results.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_by_name", sa.String(255), nullable=True),
        sa.UniqueConstraint("clinical_form_id", "lab_result_id", "legacy_clinical_note_id", name="uq_clinical_form_result"),
    )
    for table, columns in {
        "clinical_form_document_links": ("legacy_clinical_note_id", "clinical_form_id", "document_id"),
        "clinical_form_result_links": ("legacy_clinical_note_id", "clinical_form_id", "lab_result_id"),
    }.items():
        for column in columns:
            op.create_index(f"ix_{table}_{column}", table, [column])


def downgrade():
    op.drop_table("clinical_form_result_links")
    op.drop_table("clinical_form_document_links")
