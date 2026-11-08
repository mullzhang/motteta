import hashlib
import json
import subprocess
import sys
from copy import deepcopy

import pytest
from pydantic import ValidationError

from motteta.core.errors import MottetaError
from motteta.core.ledger import Ledger, encode
from motteta.core.models import (
    AddRecord,
    Correction,
    HistoryBatch,
    IdentityBinding,
    Resolution,
)


@pytest.fixture
def derived_data(history_data):
    data = deepcopy(history_data)
    data["source"] = {"id": "example-books", "name": "架空の書店", "kind": "online"}
    data["account"] = "test-account"
    item = data["records"][0]
    product = {"namespace": "example-books", "scope": "books.example.invalid", "value": "item-1"}
    item["book"].update(isbn=None, identifiers=[product], format="digital")
    reference = "https://books.example.invalid/orders/order-1"
    item["evidence"][0]["reference"] = reference
    item["external"] = {
        "order_id": "order-1",
        "line_id": None,
        "holding_id": None,
        "derived_identity": {
            "scheme": "order_product_format_v1",
            "product": deepcopy(product),
            "format": "digital",
            "order_complete": True,
            "matching_line_count": 1,
            "observed_at": item["evidence"][0]["observed_at"],
            "reference": reference,
            "note": "注文全体の購入明細を確認し、対象商品と形態に対応する明細は1件。",
        },
    }
    return data


def refreshed(data, import_id="fresh", observed_at="2026-11-02T10:00:00+09:00"):
    data = deepcopy(data)
    data["import_id"] = import_id
    data["observed_at"] = observed_at
    for item in data["records"]:
        item["evidence"][0]["observed_at"] = observed_at
        item["external"]["derived_identity"]["observed_at"] = observed_at
    return data


def binding(data, request_id="bind-1"):
    external = data["records"][0]["external"]
    return IdentityBinding(
        schema_version=1,
        request_id=request_id,
        reason="注文内の一意性と既存購入との一致を確認したため。",
        source_id=data["source"]["id"],
        account=data["account"],
        order_id=external["order_id"],
        derived_identity=external["derived_identity"],
    )


def accepted_purchase(ledger, data):
    missing = deepcopy(data)
    missing["records"][0]["external"].pop("derived_identity")
    result = ledger.import_history(HistoryBatch.model_validate(missing))
    accepted = ledger.resolve(
        result["review_ids"][0],
        Resolution(
            schema_version=1,
            request_id="accept-1",
            action="accept_record",
            reason="この1件の購入を確認済み。",
        ),
    )
    return accepted["record_ids"][0]


def tables(ledger):
    return json.loads(ledger.export("json"))["tables"]


def test_legacy_external_serialization_and_replay_are_unchanged(ledger, history_data):
    history_data["records"][0]["external"]["line_id"] = None
    batch = HistoryBatch.model_validate(history_data)
    legacy = batch.model_dump(mode="json")
    assert legacy["records"][0]["external"] == {
        "order_id": "order-1",
        "line_id": None,
        "holding_id": None,
    }
    first = ledger.import_history(batch)
    with ledger.db.connect() as conn:
        row = conn.execute(
            "SELECT payload_hash FROM requests WHERE id='history:import-1'"
        ).fetchone()
        assert row[0] == hashlib.sha256(encode(legacy).encode()).hexdigest()
        saved = json.loads(conn.execute("SELECT payload FROM reviews").fetchone()[0])["record"]
    assert AddRecord.model_validate(saved).model_dump(mode="json") == saved
    before = tables(ledger)
    replay = ledger.import_history(batch)
    assert replay["replayed"] and replay["review_ids"] == first["review_ids"]
    assert tables(ledger) == before


def test_new_observation_uses_verified_key_without_new_purchase(ledger, derived_data):
    first = ledger.import_history(HistoryBatch.model_validate(derived_data))
    fresh = refreshed(derived_data)
    second = ledger.import_history(HistoryBatch.model_validate(fresh))
    assert first["created"] == 1
    assert second["updated"] == 1 and second["created"] == second["needs_review"] == 0
    assert second["record_ids"] == first["record_ids"]
    assert ledger.status()["record_count"] == 1
    assert len(tables(ledger)["external_refs"]) == 1


def test_state_and_quantity_are_not_part_of_purchase_identity(ledger, derived_data):
    first = ledger.import_history(HistoryBatch.model_validate(derived_data))
    fresh = refreshed(derived_data)
    fresh["records"][0].update(quantity=2, order_state="returned", possession_state="disposed")
    second = ledger.import_history(HistoryBatch.model_validate(fresh))
    assert second["record_ids"] == first["record_ids"] and second["updated"] == 1
    assert ledger.status()["record_count"] == 1
    assert ledger.search("架空")["records"][0]["quantity"] == 2


@pytest.mark.parametrize("official", [{"line_id": "site-line-1"}, {"holding_id": "site-holding-1"}])
def test_site_issued_identity_remains_primary(ledger, derived_data, official):
    item = derived_data["records"][0]
    item["external"].update(official)
    item["external"]["derived_identity"].update(order_complete=False, matching_line_count=None)
    first = ledger.import_history(HistoryBatch.model_validate(derived_data))
    second = ledger.import_history(HistoryBatch.model_validate(refreshed(derived_data)))
    assert first["created"] == 1 and second["record_ids"] == first["record_ids"]
    key = json.loads(tables(ledger)["external_refs"][0]["key"])
    assert key[2] == ("holding" if "holding_id" in official else "order")


def test_json_key_components_cannot_collide_by_delimiters(ledger, derived_data):
    for index, (account, order) in enumerate(
        [("account", "part:order"), ("account:part", "order")]
    ):
        data = deepcopy(derived_data)
        data["import_id"] = f"escaped-{index}"
        data["account"] = account
        data["records"][0]["external"]["order_id"] = order
        ledger.import_history(HistoryBatch.model_validate(data))
    assert ledger.status()["record_count"] == 2
    assert len(tables(ledger)["external_refs"]) == 2


@pytest.mark.parametrize(
    "proof",
    [
        {"order_complete": False},
        {"matching_line_count": None},
        {"matching_line_count": 0},
        {"matching_line_count": 2},
    ],
)
def test_incomplete_or_ambiguous_order_is_review_even_after_binding(ledger, derived_data, proof):
    ledger.import_history(HistoryBatch.model_validate(derived_data))
    fresh = refreshed(derived_data)
    fresh["records"][0]["external"]["derived_identity"].update(proof)
    result = ledger.import_history(HistoryBatch.model_validate(fresh))
    assert result["needs_review"] == 1 and result["created"] == result["updated"] == 0
    assert ledger.reviews()["reviews"][0]["kind"] == "missing_identity"
    assert ledger.status()["record_count"] == 1
    with pytest.raises(ValidationError):
        binding(fresh)


@pytest.mark.parametrize(
    "change",
    [
        {"order_complete": "true"},
        {"matching_line_count": True},
        {"matching_line_count": "1"},
        {"matching_line_count": -1},
        {"observed_at": "2026-10-30T10:00:00+09:00"},
        {"reference": "https://books.example.invalid/another-order"},
        {"format": "print"},
        {
            "product": {
                "namespace": "example-books",
                "scope": "books.example.invalid",
                "value": "other",
            }
        },
    ],
)
def test_unsubstantiated_derived_identity_is_invalid(derived_data, change):
    derived_data["records"][0]["external"]["derived_identity"].update(change)
    with pytest.raises(ValidationError):
        HistoryBatch.model_validate(derived_data)


def test_uniqueness_cannot_be_claimed_for_two_lines(derived_data):
    other = deepcopy(derived_data["records"][0])
    other["item_id"] = "another-line"
    other["external"].pop("derived_identity")
    derived_data["records"].append(other)
    with pytest.raises(ValidationError, match="ambiguous"):
        HistoryBatch.model_validate(derived_data)


@pytest.mark.parametrize("field", ["source", "account", "order", "product", "format"])
def test_derived_identity_scope_keeps_distinct_purchases(ledger, derived_data, field):
    first = ledger.import_history(HistoryBatch.model_validate(derived_data))
    fresh = refreshed(derived_data)
    item = fresh["records"][0]
    if field == "source":
        fresh["source"]["id"] = "another-source"
    elif field == "account":
        fresh["account"] = "another-account"
    elif field == "order":
        item["external"]["order_id"] = "order-2"
    elif field == "product":
        item["book"]["identifiers"][0]["value"] = "item-2"
        item["external"]["derived_identity"]["product"]["value"] = "item-2"
    else:
        item["book"]["format"] = item["external"]["derived_identity"]["format"] = "print"
    result = ledger.import_history(HistoryBatch.model_validate(fresh))
    assert result["created"] == 1 and result["record_ids"] != first["record_ids"]
    assert ledger.status()["record_count"] == 2


def test_explicit_binding_preserves_purchase_and_is_idempotent(ledger, derived_data, tmp_path):
    record_id = accepted_purchase(ledger, derived_data)
    before = tables(ledger)
    proposal = binding(derived_data)
    preview = ledger.bind_identity(record_id, proposal, dry_run=True)
    assert preview["dry_run"] and preview["updated"] == 1
    assert tables(ledger) == before
    result = ledger.bind_identity(record_id, proposal)
    after = tables(ledger)
    assert result["record_ids"] == [record_id] and result["created"] == 0
    assert after["acquisitions"] == before["acquisitions"]
    assert after["editions"] == before["editions"]
    assert len(after["observations"]) == len(before["observations"]) + 1
    audit = [json.loads(r["payload"]) for r in after["observations"]]
    assert (
        next(r for r in audit if r.get("operation") == "bind_identity")["reason"] == proposal.reason
    )
    assert ledger.bind_identity(record_id, proposal)["replayed"]
    assert tables(ledger) == after
    assert (
        ledger.bind_identity(record_id, binding(derived_data, "bind-again"))["already_exists"] == 1
    )
    with pytest.raises(MottetaError, match="different content"):
        ledger.bind_identity(record_id, proposal.model_copy(update={"reason": "変更した理由"}))
    fresh = refreshed(derived_data)
    imported = ledger.import_history(HistoryBatch.model_validate(fresh))
    assert (
        imported["record_ids"] == [record_id]
        and imported["created"] == imported["needs_review"] == 0
    )
    assert ledger.status()["record_count"] == 1

    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(ledger.export("json"))
    restored_dir = tmp_path / "restored"
    restored_dir.mkdir()
    Ledger.restore(snapshot, restored_dir / "ledger.sqlite3", "json")
    restored = Ledger(restored_dir)
    assert tables(restored) == tables(ledger)
    fresh = refreshed(derived_data, "after-restore")
    assert restored.import_history(HistoryBatch.model_validate(fresh))["record_ids"] == [record_id]


def test_unbound_existing_purchase_stages_review_then_links(ledger, derived_data):
    record_id = accepted_purchase(ledger, derived_data)
    fresh = refreshed(derived_data)
    result = ledger.import_history(HistoryBatch.model_validate(fresh))
    review_id = result["review_ids"][0]
    review = ledger.reviews()["reviews"][0]
    assert result["created"] == 0 and result["needs_review"] == 1
    assert review["payload"]["candidate_record_ids"] == [record_id]
    assert review["payload"]["reason"] == "derived_identity_not_bound"
    with pytest.raises(MottetaError, match="same_acquisition"):
        ledger.resolve(
            review_id,
            Resolution(
                schema_version=1, request_id="no-duplicate", action="accept_record", reason="試験"
            ),
        )
    resolved = ledger.resolve(
        review_id,
        Resolution(
            schema_version=1,
            request_id="link-review",
            action="same_acquisition",
            target_record_id=record_id,
            reason="注文、商品、形態が同じ購入であることを確認。",
        ),
    )
    assert resolved["record_ids"] == [record_id] and resolved["created"] == 0
    assert ledger.reviews()["reviews"] == []
    assert ledger.import_history(HistoryBatch.model_validate(fresh))["needs_review"] == 0
    later = ledger.import_history(HistoryBatch.model_validate(refreshed(derived_data, "later")))
    assert later["record_ids"] == [record_id] and later["created"] == later["needs_review"] == 0
    assert ledger.status()["record_count"] == 1


@pytest.mark.parametrize("field", ["source_id", "account", "order_id", "product", "format"])
def test_binding_rejects_target_mismatch_without_changes(ledger, derived_data, field):
    record_id = accepted_purchase(ledger, derived_data)
    data = binding(derived_data).model_dump(mode="json")
    if field == "product":
        data["derived_identity"]["product"]["value"] = "other"
    elif field == "format":
        data["derived_identity"]["format"] = "print"
    else:
        data[field] = "other"
    before = tables(ledger)
    with pytest.raises(MottetaError, match="does not match"):
        ledger.bind_identity(record_id, IdentityBinding.model_validate(data))
    assert tables(ledger) == before


def test_binding_rejects_collision_and_non_purchase(ledger, derived_data):
    first = accepted_purchase(ledger, derived_data)
    data = tables(ledger)["acquisitions"][0]
    record = json.loads(data["data"])
    record["request_id"] = "duplicate-manual"
    second = ledger.add(AddRecord.model_validate(record))["record_ids"][0]
    ledger.bind_identity(first, binding(derived_data))
    before = tables(ledger)
    with pytest.raises(MottetaError, match="already bound"):
        ledger.bind_identity(second, binding(derived_data, "collision"))
    with pytest.raises(MottetaError, match="Record not found"):
        ledger.bind_identity("unknown", binding(derived_data, "unknown"))
    assert tables(ledger) == before
    record.update(request_id="ownership", acquisition_kind="ownership_assertion", order_state=None)
    ownership = ledger.add(AddRecord.model_validate(record))["record_ids"][0]
    with pytest.raises(MottetaError, match="does not match"):
        ledger.bind_identity(ownership, binding(derived_data, "non-purchase"))


def test_derived_import_preserves_manual_corrections_and_newer_state(ledger, derived_data):
    first = ledger.import_history(HistoryBatch.model_validate(derived_data))
    record_id = first["record_ids"][0]
    ledger.update(
        record_id,
        Correction(
            schema_version=1,
            request_id="disposed",
            reason="手放したため。",
            fields={"possession_state": "disposed"},
        ),
    )
    fresh = refreshed(derived_data)
    ledger.import_history(HistoryBatch.model_validate(fresh))
    stale = refreshed(derived_data, "stale", "2026-10-30T10:00:00+09:00")
    stale["records"][0]["quantity"] = 8
    ledger.import_history(HistoryBatch.model_validate(stale))
    record = ledger.search("架空")["records"][0]
    assert record["quantity"] == 1 and record["possession_state"] == "disposed"


def test_changed_target_is_reviewed_instead_of_overwritten(ledger, derived_data):
    record_id = accepted_purchase(ledger, derived_data)
    ledger.bind_identity(record_id, binding(derived_data))
    ledger.update(
        record_id,
        Correction(
            schema_version=1,
            request_id="account-fix",
            reason="アカウントを訂正。",
            fields={"account": "other"},
        ),
    )
    result = ledger.import_history(HistoryBatch.model_validate(refreshed(derived_data)))
    assert result["needs_review"] == 1 and result["created"] == result["updated"] == 0
    assert ledger.reviews()["reviews"][0]["payload"]["reason"] == "derived_identity_conflict"
    assert ledger.search("架空")["records"][0]["account"] == "other"


def test_historical_proof_does_not_prevent_explicit_book_correction(ledger, derived_data):
    first = ledger.import_history(HistoryBatch.model_validate(derived_data))
    record_id = first["record_ids"][0]
    corrected_book = deepcopy(derived_data["records"][0]["book"])
    corrected_book["format"] = "print"
    ledger.update(
        record_id,
        Correction(
            schema_version=1,
            request_id="format-fix",
            reason="紙の本だったため訂正。",
            fields={"book": corrected_book},
        ),
    )
    result = ledger.import_history(HistoryBatch.model_validate(refreshed(derived_data)))
    assert result["needs_review"] == 1 and result["created"] == result["updated"] == 0
    assert ledger.search("架空")["records"][0]["book"]["format"] == "print"
    observations = [json.loads(row["payload"]) for row in tables(ledger)["observations"]]
    assert observations[0]["external"]["derived_identity"]["format"] == "digital"


def test_cli_binding_dry_run_and_new_batch(ledger, derived_data, tmp_path):
    record_id = accepted_purchase(ledger, derived_data)
    proposal = binding(derived_data).model_dump(mode="json")
    command = [sys.executable, "-m", "motteta", "--data-dir", str(ledger.db.directory)]
    before = tables(ledger)
    preview = subprocess.run(
        [*command, "bind-identity", record_id, "--input", "-", "--dry-run", "--json"],
        input=json.dumps(proposal),
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert preview.returncode == 0, preview.stdout + preview.stderr
    assert json.loads(preview.stdout)["dry_run"]
    assert tables(ledger) == before
    applied = subprocess.run(
        [*command, "bind-identity", record_id, "--input", "-", "--json"],
        input=json.dumps(proposal),
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert applied.returncode == 0 and not applied.stderr
    fresh_path = tmp_path / "fresh.json"
    fresh_path.write_text(json.dumps(refreshed(derived_data)))
    imported = subprocess.run(
        [*command, "import", str(fresh_path), "--dry-run", "--json"],
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert imported.returncode == 0, imported.stdout + imported.stderr
    result = json.loads(imported.stdout)
    assert result["record_ids"] == [record_id] and result["created"] == result["needs_review"] == 0
    assert ledger.status()["record_count"] == 1
