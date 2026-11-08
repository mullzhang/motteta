import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest

from motteta.core.errors import MottetaError
from motteta.core.ledger import Ledger
from motteta.core.models import AddRecord, Candidate, Correction, HistoryBatch, Resolution


def test_idempotency_and_real_additional_purchase(ledger, record):
    first = ledger.add(record)
    replay = ledger.add(record)
    assert replay["record_ids"] == first["record_ids"]
    assert replay["created"] == 0
    ledger.add(record.model_copy(update={"request_id": "manual-2"}))
    assert ledger.status()["record_count"] == 2
    with pytest.raises(MottetaError, match="different content"):
        ledger.add(record.model_copy(update={"quantity": 2}))


def test_concurrent_retry_cannot_duplicate(ledger, record):
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: ledger.add(record), range(4)))
    assert len({r["record_ids"][0] for r in results}) == 1
    assert ledger.status()["record_count"] == 1


def test_dry_run_does_not_initialize_or_reserve_request(tmp_path, record):
    ledger = Ledger(tmp_path / "not-created")
    assert ledger.add(record, dry_run=True)["dry_run"]
    assert not ledger.db.directory.exists()
    ledger.db.initialize()
    assert ledger.add(record)["created"] == 1
    before = ledger.export("json")
    ledger.add(record.model_copy(update={"request_id": "preview"}), dry_run=True)
    # Export timestamps may differ; compare every table.
    assert json.loads(before)["tables"] == json.loads(ledger.export("json"))["tables"]


def test_imports_merge_observations_not_purchases(ledger, history_data):
    first = ledger.import_history(HistoryBatch.model_validate(history_data))
    assert first["created"] == 1
    assert ledger.import_history(HistoryBatch.model_validate(history_data))["already_exists"] == 1
    history_data["import_id"] = "import-2"
    history_data["records"][0]["order_state"] = "returned"
    history_data["records"][0]["possession_state"] = "disposed"
    history_data["records"][0]["evidence"][0]["observed_at"] = "2026-11-02T10:00:00+09:00"
    history_data["observed_at"] = "2026-11-02T11:00:00+09:00"
    assert ledger.import_history(HistoryBatch.model_validate(history_data))["updated"] == 1
    assert ledger.status()["record_count"] == 1
    history_data["import_id"] = "import-3"
    history_data["records"][0]["external"]["order_id"] = "another-order"
    history_data["records"][0]["quantity"] = 2
    assert ledger.import_history(HistoryBatch.model_validate(history_data))["created"] == 1
    assert sorted(r["quantity"] for r in ledger.search("架空")["records"]) == [1, 2]


def test_external_id_is_scoped_by_source_and_account(ledger, history_data):
    for index, account in enumerate(("personal", "business")):
        history_data["import_id"] = f"scope-{index}"
        history_data["account"] = account
        ledger.import_history(HistoryBatch.model_validate(history_data))
    history_data["source"]["id"] = "rakuten"
    history_data["import_id"] = "other-source"
    ledger.import_history(HistoryBatch.model_validate(history_data))
    assert ledger.status()["record_count"] == 3


def test_stale_import_and_manual_correction_are_preserved(ledger, history_data):
    first = ledger.import_history(HistoryBatch.model_validate(history_data))
    record_id = first["record_ids"][0]
    ledger.update(
        record_id,
        Correction(
            schema_version=1,
            request_id="fix",
            reason="Sold my copy",
            fields={"possession_state": "disposed"},
        ),
    )
    history_data["import_id"] = "later"
    history_data["records"][0]["evidence"][0]["observed_at"] = "2026-11-02T10:00:00+09:00"
    history_data["observed_at"] = "2026-11-02T11:00:00+09:00"
    ledger.import_history(HistoryBatch.model_validate(history_data))
    assert ledger.search("架空")["records"][0]["possession_state"] == "disposed"
    history_data["import_id"] = "stale"
    history_data["records"][0]["quantity"] = 9
    history_data["records"][0]["evidence"][0]["observed_at"] = "2026-10-30T10:00:00+09:00"
    ledger.import_history(HistoryBatch.model_validate(history_data))
    assert ledger.search("架空")["records"][0]["quantity"] == 1


def test_missing_order_is_not_cancellation_and_partial_is_visible(ledger, history_data):
    ledger.import_history(HistoryBatch.model_validate(history_data))
    history_data["import_id"] = "partial"
    history_data["observed_at"] = "2026-11-02T11:00:00+09:00"
    history_data["records"] = []
    history_data["coverage"].update(
        status="partial",
        checked_end="2026-10-20",
        unverified=["order-2"],
        resume={"date": "2026-10-20"},
    )
    assert (
        ledger.import_history(HistoryBatch.model_validate(history_data))["result"] == "needs_review"
    )
    assert ledger.search("架空")["records"][0]["order_state"] == "completed"
    source = ledger.status()["sources"][0]
    assert source["last_complete"] == "2026-11-01T11:00:00+09:00"
    assert source["last_attempt"]["coverage"]["status"] == "partial"


def test_ambiguous_history_identity_is_review_not_new_purchase(ledger, history_data):
    history_data["records"][0]["external"] = {"order_id": "order-1"}
    result = ledger.import_history(HistoryBatch.model_validate(history_data))
    assert result["needs_review"] == 1
    assert ledger.status()["record_count"] == 0
    resolved = ledger.resolve(
        result["review_ids"][0],
        Resolution(
            schema_version=1,
            request_id="accept",
            action="accept_record",
            reason="Confirmed a single purchase",
        ),
    )
    assert resolved["created"] == 1
    assert ledger.status()["record_count"] == 1


def test_manual_and_history_overlap_can_merge_without_losing_retry(ledger, record, history):
    manual_id = ledger.add(record)["record_ids"][0]
    imported = ledger.import_history(history)
    review = next(r for r in ledger.reviews()["reviews"] if r["kind"] == "possible_overlap")
    ledger.resolve(
        review["id"],
        Resolution(
            schema_version=1,
            request_id="merge-purchase",
            action="same_acquisition",
            target_record_id=manual_id,
            reason="Same receipt",
        ),
    )
    assert ledger.status()["record_count"] == 1
    assert ledger.import_history(history)["record_ids"] == [manual_id]
    assert imported["record_ids"][0] != manual_id


def test_ebook_bundle_and_confirmed_work_relationship(ledger, record_data, candidate):
    print_id = ledger.add(AddRecord.model_validate(record_data))["record_ids"][0]
    record_data["request_id"] = "ebook"
    record_data["book"].update(format="digital", isbn="9780000000019", file_formats=["pdf", "epub"])
    digital_id = ledger.add(AddRecord.model_validate(record_data))["record_ids"][0]
    review = next(r for r in ledger.reviews()["reviews"] if r["record_id"] == digital_id)
    assert all(m["kind"] != "related" for m in ledger.check(candidate)["matches"])
    ledger.resolve(
        review["id"],
        Resolution(
            schema_version=1,
            request_id="work",
            action="same_work",
            target_record_id=print_id,
            reason="Confirmed same work",
        ),
    )
    matches = ledger.check(candidate)["matches"]
    assert any(m["kind"] == "related" and m["record"]["id"] == digital_id for m in matches)
    assert ledger.status()["record_count"] == 2
    assert ledger.search("架空")["records"][1]["book"]["file_formats"] == ["pdf", "epub"]


def test_incomplete_volume_or_format_is_not_exact(ledger, record, candidate):
    ledger.add(record)
    for patch in ({"volume": "2"}, {"format": "unknown"}, {"format": "digital"}):
        result = ledger.check(candidate.model_copy(update=patch))
        # The ledger lacks a volume, so a supplied volume cannot establish exact identity.
        if patch.get("volume"):
            assert all(m["kind"] != "exact" for m in result["matches"])
        else:
            assert result["matches"][0]["kind"] == "possible"


def test_no_match_is_not_insufficient_identification(ledger):
    assert (
        ledger.check(Candidate(schema_version=1, isbn="9780000000019", format="print"))["result"]
        == "no_match"
    )
    assert (
        ledger.check(Candidate(schema_version=1, title="Missing", format="unknown"))["result"]
        == "unidentified"
    )


def test_import_rolls_back_on_late_failure(ledger, history_data):
    second = deepcopy(history_data["records"][0])
    second["item_id"] = "second"
    second["external"]["line_id"] = "second"
    second["book"]["edition_id"] = "does-not-exist"
    history_data["records"].append(second)
    with pytest.raises(MottetaError):
        ledger.import_history(HistoryBatch.model_validate(history_data))
    assert ledger.status()["record_count"] == 0
    assert ledger.status()["sources"] == []


def test_backup_restore_and_json_round_trip(ledger, record, tmp_path):
    ledger.add(record)
    expected = json.loads(ledger.export("json"))["tables"]
    backup = tmp_path / "backup.sqlite3"
    ledger.backup(backup)
    with pytest.raises(FileExistsError):
        ledger.backup(backup)
    restored = tmp_path / "restored"
    restored.mkdir()
    Ledger.restore(backup, restored / "ledger.sqlite3")
    assert json.loads(Ledger(restored).export("json"))["tables"] == expected
    exported = tmp_path / "export.json"
    exported.write_text(ledger.export("json"))
    restored_json = tmp_path / "restored-json"
    restored_json.mkdir()
    Ledger.restore(exported, restored_json / "ledger.sqlite3", "json")
    assert json.loads(Ledger(restored_json).export("json"))["tables"] == expected


def test_csv_does_not_turn_titles_into_formulas(ledger, record_data):
    record_data["book"]["title"] = '=HYPERLINK("bad")'
    ledger.add(AddRecord.model_validate(record_data))
    assert "'=HYPERLINK" in ledger.export("csv")


def test_conflicting_product_and_isbn_do_not_reassign_confirmed_identity(ledger, record_data):
    product = {"namespace": "amazon", "scope": "amazon.co.jp", "value": "B0TEST0001"}
    record_data["book"]["identifiers"] = [product]
    first = ledger.add(AddRecord.model_validate(record_data))["record_ids"][0]
    record_data["request_id"] = "contradicting"
    record_data["book"].update(title="別の書籍", isbn="9780000000019")
    result = ledger.add(AddRecord.model_validate(record_data))
    assert result["needs_review"] == 1
    candidate = Candidate.model_validate(
        {"schema_version": 1, "format": "print", "identifiers": [product]}
    )
    assert all(m["kind"] == "possible" for m in ledger.check(candidate)["matches"])
    specific = candidate.model_copy(update={"isbn": "9780000000002"})
    assert [
        m["record"]["id"] for m in ledger.check(specific)["matches"] if m["kind"] == "exact"
    ] == [first]
    pending = Candidate(schema_version=1, format="print", isbn="9780000000019")
    assert ledger.check(pending)["matches"][0]["kind"] == "possible"


def test_same_edition_resolution_survives_later_history(ledger, record_data, history_data):
    record_data["book"]["isbn"] = None
    target_id = ledger.add(AddRecord.model_validate(record_data))["record_ids"][0]
    result = ledger.import_history(HistoryBatch.model_validate(history_data))
    review = next(r for r in ledger.reviews()["reviews"] if r["kind"] == "book_identity")
    ledger.resolve(
        review["id"],
        Resolution(
            schema_version=1,
            request_id="merge-edition",
            action="same_edition",
            target_record_id=target_id,
            reason="Confirmed same edition",
        ),
    )
    history_data["import_id"] = "new-snapshot"
    history_data["observed_at"] = "2026-11-02T11:00:00+09:00"
    history_data["records"][0]["evidence"][0]["observed_at"] = "2026-11-02T10:00:00+09:00"
    ledger.import_history(HistoryBatch.model_validate(history_data))
    records = ledger.search("架空")["records"]
    assert len({r["edition_id"] for r in records}) == 1
    assert result["record_ids"][0] in {r["id"] for r in records}


def test_order_state_remains_in_details_with_simple_record_label(ledger, history_data, candidate):
    history_data["records"][0].update(order_state="preordered", possession_state="unknown")
    ledger.import_history(HistoryBatch.model_validate(history_data))
    reserved = ledger.check(candidate)
    assert reserved["label"] == "記録あり"
    assert reserved["matches"][0]["record"]["order_state"] == "preordered"
    assert reserved["matches"][0]["record"]["possession_state"] == "unknown"
    history_data["import_id"] = "cancelled"
    history_data["observed_at"] = "2026-11-02T11:00:00+09:00"
    history_data["records"][0]["evidence"][0]["observed_at"] = "2026-11-02T10:00:00+09:00"
    history_data["records"][0]["order_state"] = "cancelled"
    ledger.import_history(HistoryBatch.model_validate(history_data))
    cancelled = ledger.check(candidate)
    assert cancelled["label"] == "記録あり"
    assert cancelled["matches"][0]["record"]["order_state"] == "cancelled"
    assert cancelled["matches"][0]["record"]["possession_state"] == "unknown"


def test_partial_dry_run_does_not_change_coverage(ledger, history_data):
    ledger.import_history(HistoryBatch.model_validate(history_data), dry_run=True)
    assert ledger.status()["sources"] == []
    assert ledger.status()["record_count"] == 0


def test_correction_replay_reports_no_new_write(ledger, record):
    record_id = ledger.add(record)["record_ids"][0]
    correction = Correction(
        schema_version=1,
        request_id="replay-fix",
        reason="Sold",
        fields={"possession_state": "disposed"},
    )
    assert ledger.update(record_id, correction)["updated"] == 1
    replay = ledger.update(record_id, correction)
    assert replay["updated"] == 0
    assert replay["already_exists"] == 1
