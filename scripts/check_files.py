"""Fast file-format checks for pre-commit (only its explicit filenames are read)."""

import json
import sys
import tomllib
from pathlib import Path

import yaml


def main() -> int:
    errors = []
    for name in sys.argv[1:]:
        path = Path(name)
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
            if text and not text.endswith("\n"):
                errors.append(f"{name}: missing final newline")
            for i, line in enumerate(text.splitlines(), 1):
                if line != line.rstrip():
                    errors.append(f"{name}:{i}: trailing whitespace")
            if path.suffix == ".json":
                json.loads(text)
            elif path.suffix in {".yaml", ".yml"}:
                yaml.safe_load(text)
            elif path.suffix == ".toml" or path.name in {"uv.lock", "mise.lock"}:
                tomllib.loads(text)
        except (ValueError, yaml.YAMLError, UnicodeError) as exc:
            errors.append(f"{name}: {exc}")
    for error in errors:
        print(error, file=sys.stderr)
    return bool(errors)


if __name__ == "__main__":
    raise SystemExit(main())
