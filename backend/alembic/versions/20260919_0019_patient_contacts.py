"""Normalize patient addresses, telecoms, and related people."""

from alembic import op

revision = "20260919_0019"
down_revision = "20260918_0018"
branch_labels = None
depends_on = None

TABLES = ("patient_addresses", "patient_telecoms", "patient_related_persons")


def upgrade():
    from app import models  # noqa: F401
    from app.db import Base

    bind = op.get_bind()
    for name in TABLES:
        Base.metadata.tables[name].create(bind=bind, checkfirst=True)
    op.execute("""
        INSERT INTO patient_addresses
          (uuid, patient_id, use, type, line1, line2, city, state, postal_code,
           country_code, priority, active, is_primary)
        SELECT CAST(gen_random_uuid() AS VARCHAR), id, 'home', 'both',
               address_line_1, address_line_2, city, state, postal_code,
               country_code, 1, TRUE, TRUE
        FROM patients WHERE address_line_1 IS NOT NULL
    """)
    op.execute("""
        INSERT INTO patient_telecoms
          (uuid, patient_id, system, use, value, rank, active, is_primary)
        SELECT CAST(gen_random_uuid() AS VARCHAR), id, 'phone', 'home', phone,
               1, TRUE, TRUE FROM patients WHERE phone IS NOT NULL
    """)
    op.execute("""
        INSERT INTO patient_telecoms
          (uuid, patient_id, system, use, value, rank, active, is_primary)
        SELECT CAST(gen_random_uuid() AS VARCHAR), id, 'email', 'home', email,
               1, TRUE, TRUE FROM patients WHERE email IS NOT NULL
    """)


def downgrade():
    from app import models  # noqa: F401
    from app.db import Base

    bind = op.get_bind()
    for name in reversed(TABLES):
        Base.metadata.tables[name].drop(bind=bind, checkfirst=True)
