"""Install a read-only Native Messaging host, without opening a browser."""

import json
import os
import shlex
import sys
from pathlib import Path

from motteta.core.errors import MottetaError, conflict
from motteta.core.ledger import Ledger
from motteta.core.models import BrowserConfig

HOST_NAME = "com.motteta.host"


def manifest_directory(browser: str) -> Path:
    if browser != "chrome" or sys.platform != "darwin":
        raise MottetaError(
            "unsupported_browser", "Host registration currently supports Chrome on macOS", 2
        )
    return Path.home() / "Library/Application Support/Google/Chrome/NativeMessagingHosts"


def install(directory: Path, browser: str, extension_id: str) -> dict:
    config = BrowserConfig(browser=browser, extension_id=extension_id)
    root = manifest_directory(browser)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    root.mkdir(parents=True, exist_ok=True)
    launcher = directory / "native-host"
    script = (
        "#!/bin/sh\nexec "
        + shlex.quote(sys.executable)
        + " -m motteta.native_host --data-dir "
        + shlex.quote(str(directory))
        + ' "$@"\n'
    )
    launcher.write_text(script, encoding="utf-8")
    launcher.chmod(0o700)
    config_path = directory / "browser.json"
    config_path.write_text(config.model_dump_json() + "\n", encoding="utf-8")
    config_path.chmod(0o600)
    manifest = root / (HOST_NAME + ".json")
    content = {
        "name": HOST_NAME,
        "description": "Motteta local book lookup",
        "path": str(launcher),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{extension_id}/"],
    }
    manifest.write_text(json.dumps(content, indent=2) + "\n", encoding="utf-8")
    return {
        "result": "installed",
        "manifest": str(manifest),
        "extension_id": extension_id,
        "database": str(directory / "ledger.sqlite3"),
    }


def uninstall(directory: Path, browser: str) -> dict:
    manifest = manifest_directory(browser) / (HOST_NAME + ".json")
    launcher = directory / "native-host"
    if manifest.exists():
        content = json.loads(manifest.read_text(encoding="utf-8"))
        if content["path"] != str(launcher):
            raise conflict(
                "Host belongs to a different data directory; use the matching --data-dir"
            )
        manifest.unlink()
    launcher.unlink(missing_ok=True)
    (directory / "browser.json").unlink(missing_ok=True)
    return {"result": "uninstalled", "database_preserved": True}


def doctor(directory: Path) -> dict:
    checks = []
    try:
        status = Ledger(directory).status()
        checks.append({"name": "ledger", "ok": True, "record_count": status["record_count"]})
    except (MottetaError, OSError) as exc:
        checks.append({"name": "ledger", "ok": False, "message": str(exc)})
    config_path = directory / "browser.json"
    if not config_path.exists():
        checks.append({"name": "browser", "ok": False, "message": "Run motteta browser install"})
    else:
        try:
            config = BrowserConfig.model_validate_json(config_path.read_text(encoding="utf-8"))
            manifest = manifest_directory(config.browser) / (HOST_NAME + ".json")
            launcher = directory / "native-host"
            expected_origin = f"chrome-extension://{config.extension_id}/"
            valid = manifest.is_file() and os.access(launcher, os.X_OK)
            if valid:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                valid = (
                    isinstance(data, dict)
                    and data.get("path") == str(launcher)
                    and data.get("allowed_origins") == [expected_origin]
                )
            checks.append(
                {
                    "name": "browser",
                    "ok": valid,
                    "message": "Configuration checked; live browser connection not tested",
                }
            )
        except (OSError, ValueError, MottetaError) as exc:
            checks.append(
                {"name": "browser", "ok": False, "message": f"Invalid browser configuration: {exc}"}
            )
    return {
        "schema_version": 1,
        "result": "ok" if all(c["ok"] for c in checks) else "error",
        "checks": checks,
    }
