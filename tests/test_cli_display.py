import json
import os
import subprocess
import sys
from copy import deepcopy

import pytest

from motteta.core.models import AddRecord, Resolution


def cli(directory, *args, width=80):
    return subprocess.run(
        [sys.executable, "-m", "motteta", "--data-dir", str(directory), *args],
        capture_output=True,
        text=True,
        timeout=10,
        env={**os.environ, "COLUMNS": str(width), "NO_COLOR": "1"},
    )


@pytest.mark.parametrize("width", [40, 80, 120])
def test_list_is_readable_and_preserves_long_literal_titles(ledger, record_data, width):
    title = "[red]架空の技術書[/red] " + "長い書名の続き" * 8 + " 決定的な末尾"
    record_data["book"]["title"] = title
    ledger.add(AddRecord.model_validate(record_data))
    before = ledger.export("json")
    result = cli(ledger.db.directory, "list", width=width)
    assert result.returncode == 0, result.stderr
    assert "Title" in result.stdout and "Format" in result.stdout
    assert "Source" in result.stdout and "Acquired" in result.stdout
    assert "架空書店" in result.stdout and "Print" in result.stdout
    assert "Unknown" in result.stdout and "1 record" in result.stdout
    assert "決定的な末尾" in "".join(result.stdout.split())
    assert "[red]" in result.stdout and "[/red]" in "".join(result.stdout.split())
    assert "…" not in result.stdout and "\x1b" not in result.stdout
    assert not result.stderr
    assert json.loads(ledger.export("json"))["tables"] == json.loads(before)["tables"]


def test_list_json_and_search_json_keep_complete_unstyled_records(ledger, record_data):
    record_id = ledger.add(AddRecord.model_validate(record_data))["record_ids"][0]
    for args in (("list", "--json"), ("--json", "list"), ("search", "架空", "--json")):
        result = cli(ledger.db.directory, *args)
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["schema_version"] == 1 and payload["result"] == "ok"
        assert [record["id"] for record in payload["records"]] == [record_id]
        assert payload["records"][0]["book"]["title"] == record_data["book"]["title"]
        assert "\x1b" not in result.stdout and not result.stderr


def test_search_returns_a_table_for_matching_books(ledger, record_data):
    ledger.add(AddRecord.model_validate(record_data))
    second = deepcopy(record_data)
    second["request_id"] = "second-book"
    second["book"].update(title="別の電子書籍", authors=["別の著者"], isbn=None, format="digital")
    ledger.add(AddRecord.model_validate(second))
    result = cli(ledger.db.directory, "search", "別の著者")
    assert result.returncode == 0
    assert "別の電子書籍" in result.stdout and "Digital" in result.stdout
    assert "架空の技術書" not in result.stdout and "1 record" in result.stdout


@pytest.mark.parametrize("args", [("list",), ("search", "存在しない本")])
def test_empty_results_use_a_plain_message(ledger, args):
    result = cli(ledger.db.directory, *args)
    assert result.returncode == 0
    assert result.stdout.strip() == "No matching books."
    assert not result.stderr


def test_show_displays_full_details_and_json(ledger, record_data):
    record_data["book"].update(format="digital", file_formats=["pdf", "epub"])
    record_id = ledger.add(AddRecord.model_validate(record_data))["record_ids"][0]
    result = cli(ledger.db.directory, "show", record_id)
    assert result.returncode == 0, result.stderr
    for text in (
        "架空の技術書",
        "架空の著者",
        "Digital",
        "PDF, EPUB",
        "Ownership assertion",
        "Owned",
        "Quantity",
        "N/A",
        "Unknown",
        record_id,
    ):
        assert text in result.stdout
    assert "Record ID" in result.stdout and "schema_version" not in result.stdout
    assert "\x1b" not in result.stdout and not result.stderr
    machine = cli(ledger.db.directory, "show", record_id, "--json")
    assert machine.returncode == 0
    assert json.loads(machine.stdout)["record"] == ledger.search("")["records"][0]


def test_show_follows_a_merged_purchase(ledger, record, history):
    target_id = ledger.add(record)["record_ids"][0]
    imported_id = ledger.import_history(history)["record_ids"][0]
    review = next(
        item for item in ledger.reviews()["reviews"] if item["kind"] == "possible_overlap"
    )
    ledger.resolve(
        review["id"],
        Resolution(
            schema_version=1,
            request_id="merge-for-show",
            action="same_acquisition",
            target_record_id=target_id,
            reason="同じ入手を統合する試験",
        ),
    )
    result = cli(ledger.db.directory, "show", imported_id, "--json")
    assert result.returncode == 0
    assert json.loads(result.stdout)["record"]["id"] == target_id


def test_missing_record_and_missing_ledger_have_structured_errors(ledger, tmp_path):
    result = cli(ledger.db.directory, "show", "missing", "--json")
    assert result.returncode == 2
    assert json.loads(result.stdout)["error"]["code"] == "not_found"
    assert not result.stderr
    human = cli(ledger.db.directory, "show", "missing")
    assert human.returncode == 2 and not human.stdout
    assert "not_found" in human.stderr
    directory = tmp_path / "not-initialized"
    missing = cli(directory, "list", "--json")
    assert missing.returncode == 4
    assert json.loads(missing.stdout)["error"]["code"] == "not_initialized"
    assert not directory.exists()
