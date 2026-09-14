"""Add structured patient previous-name history."""
from alembic import op
revision="20260920_0020"
down_revision="20260919_0019"
branch_labels=None
depends_on=None
def upgrade():
    from app import models  # noqa: F401
    from app.db import Base
    Base.metadata.tables["patient_name_history"].create(bind=op.get_bind(),checkfirst=True)
def downgrade():
    from app import models  # noqa: F401
    from app.db import Base
    Base.metadata.tables["patient_name_history"].drop(bind=op.get_bind(),checkfirst=True)
