"""Package only the built extension, without developer files or user data."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / "extension/dist"
destination = ROOT / "dist"
destination.mkdir(exist_ok=True)
with ZipFile(destination / "motteta-extension.zip", "w", ZIP_DEFLATED) as archive:
    for path in sorted(source.iterdir()):
        if path.is_file():
            archive.write(path, path.name)
