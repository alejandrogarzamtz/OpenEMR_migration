"""Expand patient demographics and retain a lossless legacy payload."""

from alembic import op
import sqlalchemy as sa

revision = "20260906_0006"
down_revision = "20260905_0005"
branch_labels = None
depends_on = None

COLUMNS = {
    "middle_name": sa.Column("middle_name", sa.String(100), nullable=True),
    "preferred_name": sa.Column("preferred_name", sa.String(100), nullable=True),
    "suffix": sa.Column("suffix", sa.String(50), nullable=True),
    "gender_identity": sa.Column("gender_identity", sa.String(100), nullable=True),
    "sexual_orientation": sa.Column("sexual_orientation", sa.String(100), nullable=True),
    "pronouns": sa.Column("pronouns", sa.String(100), nullable=True),
    "language": sa.Column("language", sa.String(100), nullable=True),
    "race": sa.Column("race", sa.String(100), nullable=True),
    "ethnicity": sa.Column("ethnicity", sa.String(100), nullable=True),
    "address_line_1": sa.Column("address_line_1", sa.String(255), nullable=True),
    "address_line_2": sa.Column("address_line_2", sa.String(255), nullable=True),
    "city": sa.Column("city", sa.String(100), nullable=True),
    "state": sa.Column("state", sa.String(100), nullable=True),
    "postal_code": sa.Column("postal_code", sa.String(30), nullable=True),
    "country_code": sa.Column("country_code", sa.String(2), nullable=True),
    "portal_allowed": sa.Column("portal_allowed", sa.Boolean(), nullable=False, server_default=sa.false()),
    "allow_email": sa.Column("allow_email", sa.Boolean(), nullable=False, server_default=sa.false()),
    "allow_sms": sa.Column("allow_sms", sa.Boolean(), nullable=False, server_default=sa.false()),
    "deceased_at": sa.Column("deceased_at", sa.DateTime(timezone=True), nullable=True),
    "deceased_reason": sa.Column("deceased_reason", sa.String(255), nullable=True),
    "legacy_payload": sa.Column("legacy_payload", sa.JSON(), nullable=True),
}


def upgrade():
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("patients")}
    for name, column in COLUMNS.items():
        if name not in existing:
            op.add_column("patients", column)


def downgrade():
    existing = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("patients")}
    for name in reversed(COLUMNS):
        if name in existing:
            op.drop_column("patients", name)
