"""Upgrade a clean database or adopt the pre-Alembic development baseline."""
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from .db import engine


def main():
    config = Config("alembic.ini")
    tables = set(inspect(engine).get_table_names())
    if tables and "alembic_version" not in tables:
        # Releases before the baseline used metadata.create_all. The baseline
        # exactly represents that schema, so adopting it is safe and preserves
        # existing development data.
        command.stamp(config, "head")
    else:
        command.upgrade(config, "head")


if __name__ == "__main__":
    main()
