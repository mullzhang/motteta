"""Length-prefixed JSON over stdio. Never writes diagnostic text to stdout."""

import argparse
import json
import sqlite3
import struct
import sys
from pathlib import Path

from pydantic import ValidationError

from motteta.core.errors import MottetaError
from motteta.core.ledger import Ledger
from motteta.core.models import BrowserConfig, NativeRequest
from motteta.storage.database import data_directory

MAX_REQUEST = 64 * 1024
MAX_RESPONSE = 512 * 1024


def read_exact(stream, size: int) -> bytes:
    result = bytearray()
    while len(result) < size:
        chunk = stream.read(size - len(result))
        if not chunk:
            raise MottetaError("truncated_message", "Incomplete native message")
        result.extend(chunk)
    return bytes(result)


def read_message(stream) -> dict | None:
    prefix = stream.read(4)
    if not prefix:
        return None
    if len(prefix) != 4:
        prefix += read_exact(stream, 4 - len(prefix))
    size = struct.unpack("=I", prefix)[0]
    if not 0 < size <= MAX_REQUEST:
        raise MottetaError("message_size", "Invalid request size")
    return json.loads(read_exact(stream, size).decode("utf-8"))


def write_message(stream, value: dict) -> None:
    data = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(data) > MAX_RESPONSE:
        data = b'{"schema_version":1,"result":"error","error":{"code":"response_too_large","message":"Use CLI search for detailed history"}}'
    stream.write(struct.pack("=I", len(data)))
    stream.write(data)
    stream.flush()


def serve(directory: Path, origin: str, input_stream, output_stream) -> int:
    config = BrowserConfig.model_validate_json(
        (directory / "browser.json").read_text(encoding="utf-8")
    )
    if origin != f"chrome-extension://{config.extension_id}/":
        raise MottetaError("forbidden_origin", "Caller is not the registered extension")
    try:
        message = read_message(input_stream)
        if message is None:
            return 0
        request = NativeRequest.model_validate(message)
        ledger = Ledger(directory)
        result = (
            ledger.check(request.candidate) if request.operation == "check" else ledger.status()
        )
        result["request_id"] = request.request_id
    except (ValidationError, MottetaError, ValueError, UnicodeError, sqlite3.Error, OSError) as exc:
        result = {
            "schema_version": 1,
            "result": "error",
            "error": {
                "code": exc.code if isinstance(exc, MottetaError) else "invalid_input",
                "message": str(exc),
            },
        }
    write_message(output_stream, result)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Motteta read-only Native Messaging host")
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("origin")
    args = parser.parse_args()
    try:
        raise SystemExit(
            serve(data_directory(args.data_dir), args.origin, sys.stdin.buffer, sys.stdout.buffer)
        )
    except (OSError, MottetaError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(4) from exc


if __name__ == "__main__":
    main()
