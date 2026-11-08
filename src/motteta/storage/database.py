import os
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

from motteta.core.errors import MottetaError, conflict

SCHEMA_VERSION = 1
APPLICATION_ID = 0x4D4F5454
SCHEMA = """
CREATE TABLE sources (id TEXT PRIMARY KEY, data TEXT NOT NULL);
CREATE TABLE accounts (source_id TEXT NOT NULL REFERENCES sources(id), alias TEXT NOT NULL,
    PRIMARY KEY(source_id, alias));
CREATE TABLE works (id TEXT PRIMARY KEY);
CREATE TABLE editions (id TEXT PRIMARY KEY, data TEXT NOT NULL, work_id TEXT REFERENCES works(id));
CREATE TABLE identifiers (edition_id TEXT NOT NULL REFERENCES editions(id), namespace TEXT NOT NULL,
    scope TEXT NOT NULL, value TEXT NOT NULL, confirmed INTEGER NOT NULL CHECK(confirmed IN (0,1)),
    PRIMARY KEY(edition_id, namespace, scope, value));
CREATE INDEX identifier_lookup ON identifiers(namespace, scope, value);
CREATE TABLE acquisitions (id TEXT PRIMARY KEY, edition_id TEXT NOT NULL REFERENCES editions(id),
    data TEXT NOT NULL, created_at TEXT NOT NULL, observed_at TEXT NOT NULL,
    protected TEXT NOT NULL, merged_into TEXT REFERENCES acquisitions(id));
CREATE TABLE external_refs (key TEXT PRIMARY KEY, record_id TEXT NOT NULL REFERENCES acquisitions(id));
CREATE TABLE requests (id TEXT PRIMARY KEY, payload_hash TEXT NOT NULL, response TEXT NOT NULL);
CREATE TABLE observations (id TEXT PRIMARY KEY, record_id TEXT REFERENCES acquisitions(id),
    payload TEXT NOT NULL, observed_at TEXT NOT NULL);
CREATE TABLE reviews (id TEXT PRIMARY KEY, kind TEXT NOT NULL,
    record_id TEXT REFERENCES acquisitions(id), payload TEXT NOT NULL, created_at TEXT NOT NULL,
    resolution TEXT);
CREATE TABLE corrections (id TEXT PRIMARY KEY, record_id TEXT NOT NULL REFERENCES acquisitions(id),
    fields TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE imports (id TEXT PRIMARY KEY, data TEXT NOT NULL, created_at TEXT NOT NULL);
"""
TABLES = (
    "sources",
    "accounts",
    "works",
    "editions",
    "identifiers",
    "acquisitions",
    "external_refs",
    "requests",
    "observations",
    "reviews",
    "corrections",
    "imports",
)


def data_directory(value: Path | None = None) -> Path:
    if value is not None:
        return value.expanduser().resolve()
    if "MOTTETA_DATA_DIR" in os.environ:
        if not os.environ["MOTTETA_DATA_DIR"].strip():
            raise MottetaError("invalid_configuration", "MOTTETA_DATA_DIR must not be empty")
        return Path(os.environ["MOTTETA_DATA_DIR"]).expanduser().resolve()
    if sys.platform == "darwin":
        return Path.home() / "Library/Application Support/motteta"
    return Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share")) / "motteta"


def configure(conn: sqlite3.Connection) -> sqlite3.Connection:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


def validate_database(conn: sqlite3.Connection) -> None:
    if conn.execute("PRAGMA application_id").fetchone()[0] != APPLICATION_ID:
        raise MottetaError("invalid_database", "This file is not a Motteta ledger")
    if conn.execute("PRAGMA user_version").fetchone()[0] != SCHEMA_VERSION:
        raise MottetaError("schema_version", "Unsupported ledger schema version")


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.execute(f"PRAGMA application_id = {APPLICATION_ID}")
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")


class Database:
    def __init__(self, directory: Path):
        self.directory = directory
        self.path = directory / "ledger.sqlite3"

    def initialize(self) -> dict:
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise conflict("Ledger already exists; initialization will not overwrite it") from exc
        os.close(fd)
        try:
            with sqlite3.connect(self.path) as conn:
                create_schema(conn)
        except Exception:
            self.path.unlink()
            raise
        return {"result": "initialized", "database": str(self.path)}

    @contextmanager
    def connect(self, *, write: bool = False, dry_run: bool = False):
        if not self.path.is_file():
            if not dry_run:
                raise MottetaError("not_initialized", "Run motteta init before using the ledger")
            conn = configure(sqlite3.connect(":memory:"))
            create_schema(conn)
        else:
            conn = configure(
                sqlite3.connect(
                    self.path.as_uri() + ("?mode=rw" if write else "?mode=ro"), uri=True
                )
            )
            validate_database(conn)
        try:
            conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            yield conn
            if write and not dry_run:
                conn.commit()
        finally:
            if conn.in_transaction:
                conn.rollback()
            conn.close()
