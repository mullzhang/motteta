"""Check tracked and new project files, including before the first commit."""

import subprocess
import sys

files = subprocess.check_output(
    ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"]
)
paths = sorted(set(p.decode() for p in files.split(b"\0") if p))
if not paths:
    raise SystemExit("No project files found")
raise SystemExit(subprocess.call([sys.executable, "-m", "pre_commit", "run", "--files", *paths]))
