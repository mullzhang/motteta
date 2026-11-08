import io
import json
import struct
import subprocess
import sys

import pytest

from motteta import browser
from motteta.core.errors import MottetaError
from motteta.native_host import MAX_REQUEST, read_message, serve, write_message


def cli(directory, *args, input=None):
    return subprocess.run(
        [sys.executable, "-m", "motteta", "--data-dir", str(directory), *args],
        input=json.dumps(input) if input is not None else None,
        text=True,
        capture_output=True,
        timeout=10,
    )


def test_cli_json_errors_do_not_pollute_stdout(tmp_path):
    for args, data in [
        (["add", "--json"], None),
        (["add", "--input", "-", "--json"], {"bad": "input"}),
        (["--not-an-option", "--json"], None),
        (
            ["check", "--input", "-", "--json"],
            {"schema_version": 1, "format": "print", "isbn": "invalid"},
        ),
    ]:
        result = cli(tmp_path, *args, input=data)
        assert result.returncode == 2, result.stderr
        assert json.loads(result.stdout)["error"]["code"] == "invalid_input"
        assert not result.stderr
        assert "Traceback" not in result.stdout


def test_cli_end_to_end_with_stdin(tmp_path, record_data):
    assert cli(tmp_path, "init", "--json").returncode == 0
    added = cli(tmp_path, "add", "--input", "-", "--json", input=record_data)
    assert added.returncode == 0, added.stderr
    record_id = json.loads(added.stdout)["record_ids"][0]
    assert cli(tmp_path, "add", "--input", "-", "--json", input=record_data).returncode == 0
    result = cli(
        tmp_path,
        "check",
        "--input",
        "-",
        "--json",
        input={"schema_version": 1, "format": "print", "isbn": "9780000000002"},
    )
    assert json.loads(result.stdout)["matches"][0]["record"]["id"] == record_id
    correction = {
        "schema_version": 1,
        "request_id": "correct-1",
        "reason": "Sold the book",
        "fields": {"possession_state": "disposed"},
    }
    assert (
        cli(tmp_path, "update", record_id, "--input", "-", "--json", input=correction).returncode
        == 0
    )
    exported = cli(tmp_path, "export", "--format", "json")
    assert len(json.loads(exported.stdout)["tables"]["acquisitions"]) == 1
    assert cli(tmp_path, "init", "--json").returncode == 3


def test_cli_version_help_and_doctor(tmp_path):
    assert cli(tmp_path, "--version").stdout.strip() == "0.1.0"
    assert "browser" in cli(tmp_path, "--help").stdout
    result = cli(tmp_path, "doctor", "--json")
    assert result.returncode == 4
    assert json.loads(result.stdout)["checks"][0]["ok"] is False
    assert not (tmp_path / "ledger.sqlite3").exists()
    assert (
        cli(
            tmp_path,
            "browser",
            "install",
            "--browser",
            "firefox",
            "--extension-id",
            "a" * 32,
            "--json",
        ).returncode
        == 2
    )


def framed(value):
    output = io.BytesIO()
    write_message(output, value)
    output.seek(0)
    return output


def test_native_protocol_and_origin_are_read_only(ledger, record):
    ledger.add(record)
    directory = ledger.db.directory
    (directory / "browser.json").write_text(
        json.dumps({"extension_id": "a" * 32, "browser": "chrome"})
    )
    before = json.loads(ledger.export("json"))["tables"]
    request = {
        "schema_version": 1,
        "request_id": "native-1",
        "operation": "check",
        "candidate": {"schema_version": 1, "isbn": "9780000000002", "format": "print"},
    }
    output = io.BytesIO()
    assert serve(directory, "chrome-extension://" + "a" * 32 + "/", framed(request), output) == 0
    output.seek(0)
    result = read_message(output)
    assert result["request_id"] == "native-1"
    assert result["matches"][0]["kind"] == "exact"
    assert json.loads(ledger.export("json"))["tables"] == before
    with pytest.raises(MottetaError, match="Caller"):
        serve(directory, "https://www.amazon.co.jp", framed(request), io.BytesIO())
    request["operation"] = "delete_database"
    output = io.BytesIO()
    serve(directory, "chrome-extension://" + "a" * 32 + "/", framed(request), output)
    output.seek(0)
    assert read_message(output)["result"] == "error"
    assert json.loads(ledger.export("json"))["tables"] == before


@pytest.mark.parametrize(
    "wire",
    [
        b"\x02",
        struct.pack("=I", MAX_REQUEST + 1),
        struct.pack("=I", 10) + b"{}",
        struct.pack("=I", 1) + b"\xff",
    ],
)
def test_native_rejects_broken_frames(wire):
    with pytest.raises((MottetaError, ValueError)):
        read_message(io.BytesIO(wire))


def test_installation_in_temporary_manifest_directory(ledger, tmp_path, monkeypatch):
    root = tmp_path / "manifests"
    monkeypatch.setattr(browser, "manifest_directory", lambda _: root)
    result = browser.install(ledger.db.directory, "chrome", "a" * 32)
    manifest = json.loads((root / (browser.HOST_NAME + ".json")).read_text())
    assert manifest["allowed_origins"] == ["chrome-extension://" + "a" * 32 + "/"]
    assert result["database"] == str(ledger.db.path)
    assert browser.doctor(ledger.db.directory)["result"] == "ok"
    assert browser.uninstall(ledger.db.directory, "chrome")["database_preserved"]
    assert ledger.db.path.exists()


def test_doctor_reports_corrupted_configuration(ledger):
    (ledger.db.directory / "browser.json").write_text('{"browser":"chrome"}')
    result = browser.doctor(ledger.db.directory)
    assert result["result"] == "error"
    assert result["checks"][-1]["ok"] is False
    assert "Invalid browser configuration" in result["checks"][-1]["message"]
