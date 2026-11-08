"""Generate published JSON Schemas from the same models used by the CLI."""

import argparse
import json
from pathlib import Path

from motteta.core.models import (
    AddRecord,
    Candidate,
    Correction,
    HistoryBatch,
    IdentityBinding,
    NativeRequest,
    Resolution,
)

ROOT = Path(__file__).resolve().parents[1]
MODELS = {
    "add-record": AddRecord,
    "candidate": Candidate,
    "correction": Correction,
    "history-batch": HistoryBatch,
    "identity-binding": IdentityBinding,
    "native-request": NativeRequest,
    "resolution": Resolution,
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    directory = ROOT / "schemas"
    if not args.check:
        directory.mkdir(exist_ok=True)
    for name, model in MODELS.items():
        path = directory / f"{name}.schema.json"
        expected = json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n"
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != expected:
                raise SystemExit(f"Schema out of date: {path.relative_to(ROOT)}")
        else:
            path.write_text(expected, encoding="utf-8")


if __name__ == "__main__":
    main()
