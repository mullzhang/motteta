import pytest

from motteta.core.models import AddRecord, Candidate, Resolution

PRODUCT = {"namespace": "example-books", "scope": "books.example.invalid", "value": "book-1"}
OTHER_PRODUCT = {
    "namespace": "another-store",
    "scope": "another.example.invalid",
    "value": "book-2",
}


@pytest.mark.parametrize("lookup", ["isbn", "product", "title"])
@pytest.mark.parametrize("owned_volume,target_volume", [("1", "2"), ("上", "下")])
def test_known_different_volume_is_excluded_from_every_lookup(
    ledger, record_data, lookup, owned_volume, target_volume
):
    record_data["book"].update(
        title=f"架空の技術書シリーズ {owned_volume}", volume=owned_volume, identifiers=[PRODUCT]
    )
    ledger.add(AddRecord.model_validate(record_data))
    fields = {"schema_version": 1, "format": "print", "volume": target_volume}
    if lookup == "isbn":
        fields["isbn"] = record_data["book"]["isbn"]
    elif lookup == "product":
        fields["identifiers"] = [PRODUCT]
    else:
        fields.update(title=f"架空の技術書シリーズ {target_volume}", identifiers=[OTHER_PRODUCT])
    result = ledger.check(Candidate.model_validate(fields))
    assert result["matches"] == []
    assert result["result"] == "no_match" and result["label"] == "記録なし"


@pytest.mark.parametrize("owned_volume,target_volume", [("1", None), (None, "2"), (None, None)])
def test_missing_volume_keeps_title_candidate(ledger, record_data, owned_volume, target_volume):
    record_data["book"]["volume"] = owned_volume
    record_id = ledger.add(AddRecord.model_validate(record_data))["record_ids"][0]
    result = ledger.check(
        Candidate(
            schema_version=1,
            title=record_data["book"]["title"],
            format="print",
            identifiers=[OTHER_PRODUCT],
            volume=target_volume,
        )
    )
    assert result["label"] == "同じ本の可能性あり"
    assert [(match["record"]["id"], match["kind"]) for match in result["matches"]] == [
        (record_id, "possible")
    ]


def test_paper_and_digital_difference_keeps_unconfirmed_work_candidate(ledger, record_data):
    record_data["book"].update(format="digital", isbn=None, volume="1")
    record_id = ledger.add(AddRecord.model_validate(record_data))["record_ids"][0]
    result = ledger.check(
        Candidate(
            schema_version=1,
            title=record_data["book"]["title"],
            format="print",
            isbn="9780000000002",
            identifiers=[OTHER_PRODUCT],
            volume="1",
        )
    )
    assert result["label"] == "同じ本の可能性あり"
    assert [(match["record"]["id"], match["kind"]) for match in result["matches"]] == [
        (record_id, "possible")
    ]


@pytest.mark.parametrize("digital_volume", ["1", "2"])
def test_confirmed_work_cannot_override_a_known_volume_conflict(
    ledger, record_data, digital_volume
):
    record_data["book"].update(title="架空の技術書シリーズ 第1巻", volume="1")
    print_id = ledger.add(AddRecord.model_validate(record_data))["record_ids"][0]
    record_data["request_id"] = "digital-book"
    record_data["book"].update(
        title=f"架空の技術書シリーズ 第{digital_volume}巻",
        format="digital",
        isbn="9780000000019",
        volume=digital_volume,
    )
    added = ledger.add(AddRecord.model_validate(record_data))
    digital_id = added["record_ids"][0]
    review_id = next(
        review["id"] for review in ledger.reviews()["reviews"] if review["record_id"] == digital_id
    )
    ledger.resolve(
        review_id,
        Resolution(
            schema_version=1,
            request_id="link-work",
            action="same_work",
            target_record_id=print_id,
            reason="検証用に作品の関係を登録。",
        ),
    )
    result = ledger.check(
        Candidate(schema_version=1, format="print", isbn="9780000000002", volume="1")
    )
    matches = {match["record"]["id"]: match["kind"] for match in result["matches"]}
    assert result["label"] == "記録あり" and matches[print_id] == "exact"
    if digital_volume == "1":
        assert matches[digital_id] == "related"
    else:
        assert digital_id not in matches
        # An ISBN belonging to a contradictory volume must not establish a work match.
        contradicted = ledger.check(
            Candidate(schema_version=1, format="print", isbn="9780000000002", volume="2")
        )
        assert contradicted["matches"] == [] and contradicted["result"] == "no_match"
