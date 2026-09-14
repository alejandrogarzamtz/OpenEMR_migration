import importlib.util
from pathlib import Path


def test_historical_baseline_is_frozen_before_later_revisions():
    path = (
        Path(__file__).parents[1]
        / "alembic"
        / "versions"
        / "20260901_0001_baseline.py"
    )
    spec = importlib.util.spec_from_file_location("historical_baseline", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    assert set(module.metadata.tables) == {
        "users",
        "patients",
        "audit_events",
        "appointments",
        "encounters",
        "clinical_items",
        "lab_orders",
        "lab_results",
        "documents",
        "payers",
        "coverages",
        "claims",
        "charges",
        "claim_payments",
    }
    assert "facility_id" not in module.metadata.tables["appointments"].c
