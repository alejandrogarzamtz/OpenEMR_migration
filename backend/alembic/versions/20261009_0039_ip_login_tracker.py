"""Add IP-scoped login failure and manual blocking state."""
from alembic import op
import sqlalchemy as sa

revision="20261009_0039"
down_revision="20261008_0038"
branch_labels=None
depends_on=None

def upgrade():
    op.create_table("ip_login_trackers",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("ip_string",sa.String(64),nullable=False),sa.Column("total_failed_logins",sa.Integer(),nullable=False,server_default="0"),sa.Column("applicable_failed_logins",sa.Integer(),nullable=False,server_default="0"),sa.Column("last_failed_login",sa.DateTime(timezone=True),nullable=True),sa.Column("force_block",sa.Boolean(),nullable=False,server_default=sa.false()),sa.Column("skip_timing_protection",sa.Boolean(),nullable=False,server_default=sa.false()))
    op.create_index("ix_ip_login_trackers_ip_string","ip_login_trackers",["ip_string"],unique=True)
    op.create_index("ix_ip_login_trackers_last_failed_login","ip_login_trackers",["last_failed_login"])
    op.create_index("ix_ip_login_trackers_force_block","ip_login_trackers",["force_block"])

def downgrade():
    op.drop_table("ip_login_trackers")
