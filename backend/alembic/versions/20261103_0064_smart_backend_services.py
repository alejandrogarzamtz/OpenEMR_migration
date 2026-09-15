"""Add asymmetric SMART Backend Services clients and replay protection."""
from alembic import op
import sqlalchemy as sa

revision="20261103_0064";down_revision="20261102_0063";branch_labels=None;depends_on=None


def upgrade():
    op.create_table("smart_clients",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("uuid",sa.String(36),nullable=False),sa.Column("client_id",sa.String(100),nullable=False),sa.Column("name",sa.String(255),nullable=False),sa.Column("jwks",sa.JSON(),nullable=False),sa.Column("allowed_scopes",sa.JSON(),nullable=False),sa.Column("owner_user_id",sa.Integer(),sa.ForeignKey("users.id"),nullable=False),sa.Column("active",sa.Boolean(),nullable=False),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("revoked_at",sa.DateTime(timezone=True),nullable=True))
    for column in ("uuid","client_id","owner_user_id","active","revoked_at"):op.create_index(f"ix_smart_clients_{column}","smart_clients",[column],unique=column in {"uuid","client_id"})
    op.create_table("smart_assertion_replays",sa.Column("id",sa.Integer(),primary_key=True),sa.Column("smart_client_id",sa.Integer(),sa.ForeignKey("smart_clients.id"),nullable=False),sa.Column("jti",sa.String(255),nullable=False),sa.Column("expires_at",sa.DateTime(timezone=True),nullable=False),sa.UniqueConstraint("smart_client_id","jti",name="uq_smart_assertion_client_jti"))
    op.create_index("ix_smart_assertion_replays_smart_client_id","smart_assertion_replays",["smart_client_id"]);op.create_index("ix_smart_assertion_replays_expires_at","smart_assertion_replays",["expires_at"])
    op.add_column("auth_sessions",sa.Column("smart_client_id",sa.Integer(),sa.ForeignKey("smart_clients.id"),nullable=True));op.add_column("auth_sessions",sa.Column("smart_scopes",sa.JSON(),nullable=True));op.create_index("ix_auth_sessions_smart_client_id","auth_sessions",["smart_client_id"])


def downgrade():
    op.drop_index("ix_auth_sessions_smart_client_id",table_name="auth_sessions");op.drop_column("auth_sessions","smart_scopes");op.drop_column("auth_sessions","smart_client_id");op.drop_table("smart_assertion_replays");op.drop_table("smart_clients")
