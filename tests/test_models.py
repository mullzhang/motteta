from copy import deepcopy

import pytest
from pydantic import ValidationError

from motteta.core.models import AddRecord, Candidate, HistoryBatch, normalize_isbn


def test_isbn_normalization():
    assert normalize_isbn("0-13-235088-2") == "9780132350884"
    for value in ("9780000000001", "0132350880", "not-an-isbn"):
        with pytest.raises(ValueError):
            normalize_isbn(value)


@pytest.mark.parametrize("quantity", [0, -1, 1.5, True, "1"])
def test_quantity_is_positive_integer(record_data, quantity):
    record_data["quantity"] = quantity
    with pytest.raises(ValidationError):
        AddRecord.model_validate(record_data)


def test_unknown_values_and_partial_dates(record_data):
    for value in (None, "2020", "2020-02", "2020-02-29"):
        record_data["acquired_on"] = value
        assert AddRecord.model_validate(record_data).acquired_on == value
    record_data["acquired_on"] = "2020-02-30"
    with pytest.raises(ValidationError):
        AddRecord.model_validate(record_data)


def test_no_invented_states_or_fields(record_data):
    record_data["order_state"] = "completed"
    with pytest.raises(ValidationError):
        AddRecord.model_validate(record_data)
    record_data["order_state"] = None
    record_data["legacy_isbn"] = "9780000000002"
    with pytest.raises(ValidationError):
        AddRecord.model_validate(record_data)


def test_coverage_complete_cannot_hide_gaps(history_data):
    for patch in (
        {"unverified": ["order-2"]},
        {"checked_end": "2026-10-20"},
        {"resume": {"order": "order-2"}},
    ):
        data = deepcopy(history_data)
        data["coverage"].update(patch)
        with pytest.raises(ValidationError):
            HistoryBatch.model_validate(data)


def test_candidate_isbn_validation():
    assert Candidate(schema_version=1, format="print", isbn="0-13-235088-2").isbn == "9780132350884"
