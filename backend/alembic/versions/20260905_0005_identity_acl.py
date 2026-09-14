"""Add stable user identity, account state, and explicit ACL grants."""

from alembic import op
import sqlalchemy as sa
from uuid import uuid4

revision = "20260905_0005"
down_revision = "20260904_0004"
branch_labels = None
depends_on = None


def upgrade():
    # Revisions 0001-0004 in the discarded prototype used live metadata.
    # Guard this bridge revision so both an existing prototype database and a
    # fresh database can reach the same state. The replacement baseline will be
    # frozen once all legacy tables have explicit mappings.
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("users")}
    additions = {
        "uuid": sa.Column("uuid", sa.String(length=36), nullable=True),
        "legacy_user_id": sa.Column("legacy_user_id", sa.Integer(), nullable=True),
        "username": sa.Column("username", sa.String(length=255), nullable=True),
        "active": sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        "permissions": sa.Column("permissions", sa.JSON(), nullable=False, server_default="[]"),
    }
    for name, column in additions.items():
        if name not in columns:
            op.add_column("users", column)

    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("users")}
    if "ix_users_uuid" not in indexes:
        op.create_index("ix_users_uuid", "users", ["uuid"], unique=True)

    unique_sets = {
        tuple(constraint["column_names"])
        for constraint in sa.inspect(op.get_bind()).get_unique_constraints("users")
    }
    if ("legacy_user_id",) not in unique_sets:
        op.create_unique_constraint("uq_users_legacy_user_id", "users", ["legacy_user_id"])
    if ("username",) not in unique_sets:
        op.create_unique_constraint("uq_users_username", "users", ["username"])

    users = sa.table(
        "users",
        sa.column("id", sa.Integer()),
        sa.column("uuid", sa.String()),
        sa.column("role", sa.String()),
        sa.column("permissions", sa.JSON()),
    )
    connection = op.get_bind()
    for user_id, user_uuid in connection.execute(sa.select(users.c.id, users.c.uuid)):
        values = {"uuid": user_uuid or str(uuid4())}
        connection.execute(sa.update(users).where(users.c.id == user_id).values(**values))
    connection.execute(
        sa.update(users).where(users.c.role == "admin").values(permissions=["*:*:*"])
    )


def downgrade():
    inspector = sa.inspect(op.get_bind())
    for constraint in inspector.get_unique_constraints("users"):
        columns = tuple(constraint["column_names"])
        if columns in {("username",), ("legacy_user_id",)} and constraint["name"]:
            op.drop_constraint(constraint["name"], "users", type_="unique")
    indexes = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("users")}
    if "ix_users_uuid" in indexes:
        op.drop_index("ix_users_uuid", table_name="users")
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("users")}
    for name in ("permissions", "active", "username", "legacy_user_id", "uuid"):
        if name in columns:
            op.drop_column("users", name)
