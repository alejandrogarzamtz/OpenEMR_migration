"""Preserve complete legacy insurance subscriber evidence."""
from alembic import op
import sqlalchemy as sa

revision="20261028_0058";down_revision="20261027_0057";branch_labels=None;depends_on=None


def upgrade():
    op.add_column("coverages",sa.Column("legacy_payload",sa.JSON(),nullable=True))


def downgrade():
    op.drop_column("coverages","legacy_payload")
