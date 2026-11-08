from copy import deepcopy

import pytest

from motteta.core.ledger import Ledger
from motteta.core.models import AddRecord, Candidate, HistoryBatch


@pytest.fixture
def ledger(tmp_path):
    value = Ledger(tmp_path / "data")
    value.db.initialize()
    return value


@pytest.fixture
def record_data():
    return {
        "schema_version": 1,
        "request_id": "manual-1",
        "book": {
            "title": "架空の技術書",
            "authors": ["架空の著者"],
            "isbn": "9780000000002",
            "format": "print",
        },
        "source": {"id": "local-shop", "name": "架空書店", "kind": "physical"},
        "account": None,
        "acquisition_kind": "ownership_assertion",
        "quantity": 1,
        "acquired_on": None,
        "order_state": None,
        "possession_state": "owned",
        "evidence": [{"kind": "user_assertion", "observed_at": "2026-11-01T10:00:00+09:00"}],
    }


@pytest.fixture
def record(record_data):
    return AddRecord.model_validate(record_data)


@pytest.fixture
def candidate():
    return Candidate(schema_version=1, isbn="9780000000002", format="print")


@pytest.fixture
def history_data(record_data):
    item = deepcopy(record_data)
    for key in ("schema_version", "request_id", "source", "account"):
        item.pop(key)
    item.update(
        item_id="line-1",
        acquisition_kind="purchase",
        order_state="completed",
        external={"order_id": "order-1", "line_id": "stable-line-1"},
    )
    item["evidence"] = [{"kind": "purchase_history", "observed_at": "2026-11-01T10:00:00+09:00"}]
    return {
        "schema_version": 1,
        "import_id": "import-1",
        "source": {"id": "amazon-jp", "name": "Amazon.co.jp", "kind": "online"},
        "account": "personal",
        "observed_at": "2026-11-01T11:00:00+09:00",
        "records": [item],
        "coverage": {
            "requested_start": "2026-10-01",
            "requested_end": "2026-10-31",
            "checked_start": "2026-10-01",
            "checked_end": "2026-10-31",
            "status": "complete",
            "visited": ["orders:2026-10"],
        },
    }


@pytest.fixture
def history(history_data):
    return HistoryBatch.model_validate(history_data)
