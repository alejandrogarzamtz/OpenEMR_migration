"""Add tamper-evident clinical form signatures."""
from alembic import op

revision = "20260928_0028"
down_revision = "20260927_0027"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    from app import models  # noqa: F401
    from app.db import Base
    Base.metadata.tables["clinical_signatures"].create(bind=bind, checkfirst=True)
    if bind.dialect.name == "postgresql":
        op.execute("""CREATE OR REPLACE FUNCTION reject_clinical_signature_mutation() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'clinical signatures are append-only'; END; $$ LANGUAGE plpgsql""")
        op.execute("""CREATE TRIGGER clinical_signatures_append_only BEFORE UPDATE OR DELETE ON clinical_signatures FOR EACH ROW EXECUTE FUNCTION reject_clinical_signature_mutation()""")


def downgrade():
    bind = op.get_bind()
    from app import models  # noqa: F401
    from app.db import Base
    Base.metadata.tables["clinical_signatures"].drop(bind=bind, checkfirst=True)
    if bind.dialect.name == "postgresql": op.execute("DROP FUNCTION IF EXISTS reject_clinical_signature_mutation()")
