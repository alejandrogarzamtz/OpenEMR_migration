"""Replace placeholder screening items with the preserved legacy wording."""

from alembic import op
import sqlalchemy as sa

revision = "20261005_0035"
down_revision = "20261004_0034"
branch_labels = None
depends_on = None

definitions = {
    "PHQ-9": [
        "Little interest or pleasure in doing things",
        "Feeling down, depressed, or hopeless",
        "Trouble falling or staying asleep, or sleeping too much",
        "Feeling tired or having little energy",
        "Poor appetite or overeating",
        "Feeling bad about yourself - or that you are a failure or have let yourself or your family down",
        "Trouble concentrating on things, such as reading an article or watching videos",
        "Moving or speaking slowly noted by others or fidgety or restless more than usual",
        "Thoughts that you would be better off dead, or of hurting yourself",
    ],
    "GAD-7": [
        "Feeling nervous, anxious, or on edge",
        "Not being able to stop or control worrying",
        "Worrying too much about different things",
        "Trouble relaxing",
        "Being so restless that it's hard to sit still",
        "Becoming easily annoyed or irritable",
        "Feeling afraid as if something awful might happen",
    ],
}


def questions(items):
    return [
        {"id": f"q{index}", "text": text, "min": 0, "max": 3}
        for index, text in enumerate(items, start=1)
    ]


def upgrade():
    table = sa.table(
        "questionnaire_definitions",
        sa.column("code", sa.String),
        sa.column("version", sa.String),
        sa.column("questions", sa.JSON),
    )
    for code, items in definitions.items():
        op.execute(
            table.update()
            .where(table.c.code == code, table.c.version == "1")
            .values(questions=questions(items))
        )


def downgrade():
    table = sa.table(
        "questionnaire_definitions",
        sa.column("code", sa.String),
        sa.column("version", sa.String),
        sa.column("questions", sa.JSON),
    )
    for code, items in definitions.items():
        op.execute(
            table.update()
            .where(table.c.code == code, table.c.version == "1")
            .values(
                questions=[
                    {"id": f"q{index}", "text": f"{code} item {index}", "min": 0, "max": 3}
                    for index in range(1, len(items) + 1)
                ]
            )
        )
