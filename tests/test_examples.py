from pathlib import Path

import pytest

from motteta.core.models import (
    AddRecord,
    Candidate,
    Correction,
    HistoryBatch,
    IdentityBinding,
    Resolution,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    "name,model",
    [
        ("ownership", AddRecord),
        ("candidate", Candidate),
        ("history", HistoryBatch),
        ("history-derived", HistoryBatch),
        ("identity-binding", IdentityBinding),
        ("correction", Correction),
        ("resolution", Resolution),
    ],
)
def test_published_examples_follow_runtime_contract(name, model):
    model.model_validate_json((ROOT / "examples" / (name + ".json")).read_text(encoding="utf-8"))
