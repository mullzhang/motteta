import csv
import hashlib
import io
import json
import os
import sqlite3
import unicodedata
from datetime import UTC, datetime
from difflib import SequenceMatcher
from pathlib import Path
from uuid import uuid4

from motteta.core.errors import MottetaError, conflict
from motteta.core.models import (
    AddRecord,
    Book,
    Candidate,
    Correction,
    DerivedIdentity,
    HistoryBatch,
    IdentityBinding,
    Resolution,
)
from motteta.storage.database import (
    APPLICATION_ID,
    SCHEMA_VERSION,
    TABLES,
    Database,
    configure,
    create_schema,
    validate_database,
)


def encode(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def now() -> str:
    return datetime.now(UTC).isoformat()


def new_id() -> str:
    return str(uuid4())


def normalized(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKC", value).casefold() if c.isalnum())


def known_difference(left: str | None, right: str | None) -> bool:
    return left not in (None, "unknown") and right not in (None, "unknown") and left != right


def book_conflicts(a: Book | Candidate, b: Book) -> bool:
    if a.isbn and b.isbn and a.isbn != b.isbn:
        return True
    for field in ("format", "volume", "edition", "language"):
        left, right = getattr(a, field), getattr(b, field)
        if known_difference(left, right):
            return True
    return False


def identity_complete(a: Candidate, b: Book) -> bool:
    return (
        not book_conflicts(a, b)
        and a.format != "unknown"
        and a.format == b.format
        and all(
            getattr(a, field) is None or getattr(a, field) == getattr(b, field)
            for field in ("volume", "edition", "language")
        )
    )


def response(result: str = "ok") -> dict:
    return {
        "schema_version": 1,
        "result": result,
        "record_ids": [],
        "created": 0,
        "updated": 0,
        "already_exists": 0,
        "needs_review": 0,
        "review_ids": [],
    }


class Ledger:
    def __init__(self, directory: Path):
        self.db = Database(directory)

    @staticmethod
    def _canonical(conn, record_id: str) -> str:
        seen = set()
        while record_id not in seen:
            seen.add(record_id)
            row = conn.execute(
                "SELECT merged_into FROM acquisitions WHERE id=?", (record_id,)
            ).fetchone()
            if row is None:
                raise MottetaError("not_found", "Record not found", 2)
            if row[0] is None:
                return record_id
            record_id = row[0]
        raise MottetaError("invalid_database", "Record merge cycle detected")

    @staticmethod
    def _cached(conn, request_id: str, payload: dict) -> dict | None:
        row = conn.execute("SELECT * FROM requests WHERE id=?", (request_id,)).fetchone()
        if row is None:
            return None
        if row["payload_hash"] != hashlib.sha256(encode(payload).encode()).hexdigest():
            raise conflict("Request ID was already used with different content")
        result = json.loads(row["response"])
        result["record_ids"] = [Ledger._canonical(conn, i) for i in result["record_ids"]]
        result.update(created=0, updated=0, already_exists=len(result["record_ids"]))
        result["review_ids"] = [
            i
            for i in result["review_ids"]
            if conn.execute(
                "SELECT 1 FROM reviews WHERE id=? AND resolution IS NULL", (i,)
            ).fetchone()
        ]
        result["needs_review"] = len(result["review_ids"])
        if (
            result["result"] == "needs_review"
            and not result["needs_review"]
            and result.get("coverage", {}).get("status", "complete") == "complete"
        ):
            result["result"] = "ok"
        result["replayed"] = True
        return result

    @staticmethod
    def _remember(conn, request_id: str, payload: dict, result: dict) -> None:
        conn.execute(
            "INSERT INTO requests VALUES (?,?,?)",
            (
                request_id,
                hashlib.sha256(encode(payload).encode()).hexdigest(),
                encode(result),
            ),
        )

    @staticmethod
    def _source(conn, record: AddRecord) -> None:
        if record.source is None:
            return
        old = conn.execute("SELECT data FROM sources WHERE id=?", (record.source.id,)).fetchone()
        if old and json.loads(old[0])["kind"] != record.source.kind:
            raise conflict("Source ID is already assigned to a different source kind")
        conn.execute(
            "INSERT INTO sources VALUES (?,?) ON CONFLICT(id) DO UPDATE SET data=excluded.data",
            (
                record.source.id,
                record.source.model_dump_json(),
            ),
        )
        if record.account:
            conn.execute(
                "INSERT OR IGNORE INTO accounts VALUES (?,?)", (record.source.id, record.account)
            )

    @staticmethod
    def _review(conn, kind: str, record_id: str | None, payload: dict) -> str:
        existing = conn.execute(
            "SELECT id FROM reviews WHERE kind=? AND record_id IS ? AND payload=? AND resolution IS NULL",
            (kind, record_id, encode(payload)),
        ).fetchone()
        if existing:
            return existing[0]
        review_id = new_id()
        conn.execute(
            "INSERT INTO reviews VALUES (?,?,?,?,?,NULL)",
            (
                review_id,
                kind,
                record_id,
                encode(payload),
                now(),
            ),
        )
        return review_id

    @staticmethod
    def _identifier_sets(conn, ids, *, include_pending: bool = False) -> list[set[str]]:
        found = []
        for identifier in ids:
            current = set(
                row[0]
                for row in conn.execute(
                    "SELECT edition_id FROM identifiers WHERE namespace=? AND scope=? AND value=? AND (confirmed=1 OR ?)",
                    (
                        identifier.namespace,
                        identifier.scope,
                        identifier.value,
                        int(include_pending),
                    ),
                )
            )
            if current:
                found.append(current)
        return found

    def _edition(self, conn, book: Book) -> tuple[str, list[str]]:
        known_sets = self._identifier_sets(conn, book.all_identifiers())
        candidates = set.union(*known_sets) if known_sets else set()
        agreed = set.intersection(*known_sets) if known_sets else set()
        if book.edition_id:
            row = conn.execute(
                "SELECT data FROM editions WHERE id=?", (book.edition_id,)
            ).fetchone()
            if row is None or book_conflicts(book, Book.model_validate_json(row[0])):
                raise conflict("Explicit edition ID is missing or conflicts with the supplied book")
            candidates = {book.edition_id}
            agreed = candidates
        compatible = [
            i
            for i in agreed
            if not book_conflicts(
                book,
                Book.model_validate_json(
                    conn.execute("SELECT data FROM editions WHERE id=?", (i,)).fetchone()[0]
                ),
            )
        ]
        # Unknown formats cannot establish equality between a paper and digital edition.
        compatible = [
            i
            for i in compatible
            if book.format != "unknown"
            and Book.model_validate_json(
                conn.execute("SELECT data FROM editions WHERE id=?", (i,)).fetchone()[0]
            ).format
            == book.format
        ]
        if book.edition_id:
            compatible = [book.edition_id]
        if len(compatible) == 1:
            edition_id = compatible[0]
            stored = json.loads(
                conn.execute("SELECT data FROM editions WHERE id=?", (edition_id,)).fetchone()[0]
            )
            incoming = book.model_dump(mode="json")
            for field in ("isbn", "volume", "edition", "language"):
                if stored[field] is None and incoming[field] is not None:
                    stored[field] = incoming[field]
            conn.execute("UPDATE editions SET data=? WHERE id=?", (encode(stored), edition_id))
        else:
            edition_id = new_id()
            conn.execute(
                "INSERT INTO editions VALUES (?,?,NULL)", (edition_id, book.model_dump_json())
            )
        for identifier in book.all_identifiers():
            conn.execute(
                "INSERT INTO identifiers VALUES (?,?,?,?,?) ON CONFLICT(edition_id,namespace,scope,value) DO UPDATE SET confirmed=MAX(identifiers.confirmed,excluded.confirmed)",
                (
                    edition_id,
                    identifier.namespace,
                    identifier.scope,
                    identifier.value,
                    int(not candidates or bool(compatible)),
                ),
            )
        similar = set(candidates) - {edition_id}
        for row in conn.execute("SELECT id,data FROM editions WHERE id != ?", (edition_id,)):
            other = Book.model_validate_json(row["data"])
            if (
                SequenceMatcher(None, normalized(book.title), normalized(other.title)).ratio()
                >= 0.86
            ):
                similar.add(row["id"])
        return edition_id, sorted(similar)

    @staticmethod
    def _external_key(record: AddRecord) -> str | None:
        if not record.external or record.external.key() is None:
            return None
        return encode([record.source.id, record.account, *record.external.key()])

    @staticmethod
    def _derived_target_matches(conn, row, source_id, account, order_id, identity: DerivedIdentity):
        data = json.loads(row["data"])
        if (
            data["acquisition_kind"] != "purchase"
            or not data["source"]
            or data["source"]["id"] != source_id
            or data["account"] != account
            or not data["external"]
            or data["external"]["order_id"] != order_id
        ):
            return False
        book = Book.model_validate_json(
            conn.execute("SELECT data FROM editions WHERE id=?", (row["edition_id"],)).fetchone()[0]
        )
        return (
            book.format == identity.format
            and conn.execute(
                "SELECT 1 FROM identifiers WHERE edition_id=? AND namespace=? AND scope=? AND value=? AND confirmed=1",
                (
                    row["edition_id"],
                    identity.product.namespace,
                    identity.product.scope,
                    identity.product.value,
                ),
            ).fetchone()
            is not None
        )

    def _derived_candidates(self, conn, record: AddRecord) -> list[str]:
        identity = record.external.derived_identity
        return [
            row["id"]
            for row in conn.execute(
                "SELECT * FROM acquisitions WHERE merged_into IS NULL ORDER BY id"
            )
            if self._derived_target_matches(
                conn, row, record.source.id, record.account, record.external.order_id, identity
            )
        ]

    def _missing_identity(self, conn, record: AddRecord, details: dict) -> dict:
        review = self._review(
            conn, "missing_identity", None, {"record": record.model_dump(mode="json"), **details}
        )
        result = response("needs_review")
        result.update(needs_review=1, review_ids=[review])
        self._remember(conn, record.request_id, record.model_dump(mode="json"), result)
        return result

    def _ingest(self, conn, record: AddRecord, *, history: bool) -> dict:
        payload = record.model_dump(mode="json")
        cached = self._cached(conn, record.request_id, payload)
        if cached is not None:
            return cached
        result = response()
        self._source(conn, record)
        key = self._external_key(record)
        if history and key is None:
            return self._missing_identity(conn, record, {})
        existing = (
            conn.execute("SELECT record_id FROM external_refs WHERE key=?", (key,)).fetchone()
            if key
            else None
        )
        if key and record.external.key()[0] == "derived":
            if existing:
                target_id = self._canonical(conn, existing[0])
                target = conn.execute(
                    "SELECT * FROM acquisitions WHERE id=?", (target_id,)
                ).fetchone()
                if not self._derived_target_matches(
                    conn,
                    target,
                    record.source.id,
                    record.account,
                    record.external.order_id,
                    record.external.derived_identity,
                ):
                    return self._missing_identity(
                        conn,
                        record,
                        {
                            "reason": "derived_identity_conflict",
                            "candidate_record_ids": [target_id],
                        },
                    )
            else:
                candidates = self._derived_candidates(conn, record)
                if candidates:
                    return self._missing_identity(
                        conn,
                        record,
                        {
                            "reason": "derived_identity_not_bound",
                            "candidate_record_ids": candidates,
                        },
                    )
        timestamp = record.observed_at().astimezone(UTC).isoformat()
        # Uniqueness describes this observation, not every later state of the purchase.
        # Keep the proof in the observation audit and the key in external_refs.
        data = record.model_dump(mode="json", exclude={"external": {"derived_identity"}})
        if existing:
            record_id = self._canonical(conn, existing[0])
            old = conn.execute("SELECT * FROM acquisitions WHERE id=?", (record_id,)).fetchone()
            current = json.loads(old["data"])
            protected = json.loads(old["protected"])
            if datetime.fromisoformat(timestamp) < datetime.fromisoformat(old["observed_at"]):
                result["already_exists"] = 1
            elif datetime.fromisoformat(timestamp) == datetime.fromisoformat(
                old["observed_at"]
            ) and any(
                payload[f] != current[f]
                for f in ("order_state", "quantity", "possession_state", "acquired_on")
                if f not in protected
            ):
                review = self._review(
                    conn, "conflicting_observation", record_id, {"record": payload}
                )
                result.update(needs_review=1, review_ids=[review])
            else:
                for field in protected:
                    data[field] = current[field]
                updated_record = AddRecord.model_validate(data)
                edition_id, _ = self._edition(conn, updated_record.book)
                conn.execute(
                    "UPDATE acquisitions SET data=?,edition_id=?,observed_at=? WHERE id=?",
                    (
                        encode(data),
                        edition_id,
                        timestamp,
                        record_id,
                    ),
                )
                result["updated"] = 1
        else:
            edition_id, similar = self._edition(conn, record.book)
            record_id = new_id()
            conn.execute(
                "INSERT INTO acquisitions VALUES (?,?,?,?,?,? ,NULL)",
                (
                    record_id,
                    edition_id,
                    encode(data),
                    now(),
                    timestamp,
                    "[]",
                ),
            )
            if key:
                conn.execute("INSERT INTO external_refs VALUES (?,?)", (key, record_id))
            result["created"] = 1
            if similar:
                review = self._review(
                    conn, "book_identity", record_id, {"candidate_edition_ids": similar}
                )
                result["review_ids"].append(review)
            for other in conn.execute(
                "SELECT id,data FROM acquisitions WHERE edition_id=? AND id!=? AND merged_into IS NULL",
                (edition_id, record_id),
            ):
                other_data = json.loads(other["data"])
                if (record.external is None) != (other_data["external"] is None):
                    review = self._review(
                        conn, "possible_overlap", record_id, {"candidate_record_id": other["id"]}
                    )
                    result["review_ids"].append(review)
            result["needs_review"] = len(result["review_ids"])
        result["record_ids"] = [record_id]
        conn.execute(
            "INSERT INTO observations VALUES (?,?,?,?)",
            (
                new_id(),
                record_id,
                record.model_dump_json(),
                timestamp,
            ),
        )
        if result["needs_review"]:
            result["result"] = "needs_review"
        self._remember(conn, record.request_id, record.model_dump(mode="json"), result)
        return result

    def add(self, record: AddRecord, *, dry_run: bool = False) -> dict:
        with self.db.connect(write=True, dry_run=dry_run) as conn:
            result = self._ingest(conn, record, history=False)
            if dry_run:
                result["dry_run"] = True
            return result

    def import_history(self, batch: HistoryBatch, *, dry_run: bool = False) -> dict:
        payload = batch.model_dump(mode="json")
        with self.db.connect(write=True, dry_run=dry_run) as conn:
            request_id = "history:" + batch.import_id
            cached = self._cached(conn, request_id, payload)
            if cached is not None:
                return cached
            total = response()
            for item in batch.records:
                fields = item.model_dump(mode="json", exclude={"item_id"})
                record = AddRecord.model_validate(
                    {
                        **fields,
                        "schema_version": 1,
                        "request_id": f"history-item:{batch.import_id}:{item.item_id}",
                        "source": batch.source.model_dump(),
                        "account": batch.account,
                    }
                )
                result = self._ingest(conn, record, history=True)
                for field in ("created", "updated", "already_exists", "needs_review"):
                    total[field] += result[field]
                total["record_ids"].extend(result["record_ids"])
                total["review_ids"].extend(result["review_ids"])
            total["coverage"] = batch.coverage.model_dump(mode="json")
            if total["needs_review"] or batch.coverage.status != "complete":
                total["result"] = "needs_review"
            conn.execute(
                "INSERT INTO imports VALUES (?,?,?)", (batch.import_id, encode(payload), now())
            )
            self._remember(conn, request_id, payload, total)
            if dry_run:
                total["dry_run"] = True
            return total

    def _records(self, conn) -> list[dict]:
        records = []
        for row in conn.execute(
            "SELECT a.*,e.data AS book_data,e.work_id FROM acquisitions a JOIN editions e ON e.id=a.edition_id WHERE a.merged_into IS NULL ORDER BY a.created_at,a.id"
        ):
            data = json.loads(row["data"])
            data.update(
                id=row["id"],
                edition_id=row["edition_id"],
                work_id=row["work_id"],
                created_at=row["created_at"],
                observed_at=row["observed_at"],
            )
            # Preserve record-specific formats and evidence while exposing the canonical edition.
            data["book"]["edition_id"] = row["edition_id"]
            data["acquired_on_precision"] = (
                {4: "year", 7: "month", 10: "day"}.get(len(data["acquired_on"]))
                if data["acquired_on"]
                else None
            )
            records.append(data)
        return records

    def search(self, term: str) -> dict:
        with self.db.connect() as conn:
            term = normalized(term)
            matches = []
            for record in self._records(conn):
                book = Book.model_validate(record["book"])
                text = " ".join(
                    [book.title, *book.authors, *[i.value for i in book.all_identifiers()]]
                )
                if term in normalized(text):
                    matches.append(record)
            return {"schema_version": 1, "result": "ok", "records": matches}

    @staticmethod
    def _status(conn) -> dict:
        groups = {}
        for row in conn.execute("SELECT data FROM imports ORDER BY created_at,id"):
            data = json.loads(row[0])
            key = (data["source"]["id"], data["account"])
            item = groups.setdefault(
                key,
                {
                    "source": data["source"],
                    "account": data["account"],
                    "last_attempt": None,
                    "last_complete": None,
                    "confirmed_ranges": [],
                },
            )
            if item["last_attempt"] is None or datetime.fromisoformat(
                data["observed_at"]
            ) > datetime.fromisoformat(item["last_attempt"]["observed_at"]):
                item["last_attempt"] = {
                    "observed_at": data["observed_at"],
                    "coverage": data["coverage"],
                }
            if data["coverage"]["status"] == "complete":
                if item["last_complete"] is None or datetime.fromisoformat(
                    data["observed_at"]
                ) > datetime.fromisoformat(item["last_complete"]):
                    item["last_complete"] = data["observed_at"]
                interval = {
                    "requested_start": data["coverage"]["requested_start"],
                    "requested_end": data["coverage"]["requested_end"],
                }
                if interval not in item["confirmed_ranges"]:
                    item["confirmed_ranges"].append(interval)
        return {
            "schema_version": 1,
            "result": "ok",
            "sources": list(groups.values()),
            "unresolved_reviews": conn.execute(
                "SELECT count(*) FROM reviews WHERE resolution IS NULL"
            ).fetchone()[0],
            "record_count": conn.execute(
                "SELECT count(*) FROM acquisitions WHERE merged_into IS NULL"
            ).fetchone()[0],
        }

    def status(self) -> dict:
        with self.db.connect() as conn:
            return self._status(conn)

    def check(self, candidate: Candidate) -> dict:
        with self.db.connect() as conn:
            known_sets = self._identifier_sets(conn, candidate.all_identifiers())
            all_sets = self._identifier_sets(
                conn, candidate.all_identifiers(), include_pending=True
            )
            exact_ids = set.union(*all_sets) if all_sets else set()
            all_agreed = set.intersection(*all_sets) if all_sets else set()
            confirmed_agreed = set.intersection(*known_sets) if known_sets else set()
            agreed = all_agreed & confirmed_agreed
            conflicting_identifiers = bool(all_sets and not agreed)
            matches = []
            records = [
                record
                for record in self._records(conn)
                if not known_difference(
                    candidate.volume, Book.model_validate(record["book"]).volume
                )
            ]
            # A contradicted volume cannot establish a match or a work relationship.
            agreed.intersection_update(record["edition_id"] for record in records)
            compatible = {
                r["edition_id"]
                for r in records
                if r["edition_id"] in all_agreed
                and identity_complete(candidate, Book.model_validate(r["book"]))
            }
            eligible = compatible & confirmed_agreed
            anchors = (
                eligible if len(compatible) == 1 else agreed if len(all_agreed) == 1 else set()
            )
            work_ids = {
                row[0]
                for eid in anchors
                for row in conn.execute(
                    "SELECT work_id FROM editions WHERE id=? AND work_id IS NOT NULL", (eid,)
                )
            }
            for record in records:
                book = Book.model_validate(record["book"])
                kind = None
                if record["edition_id"] in exact_ids:
                    kind = (
                        "exact"
                        if len(compatible) == 1
                        and record["edition_id"] in eligible
                        and identity_complete(candidate, book)
                        else "possible"
                    )
                    if (
                        kind == "possible"
                        and not conflicting_identifiers
                        and record["work_id"] in work_ids
                        and candidate.format != "unknown"
                        and candidate.format != book.format
                    ):
                        kind = "related"
                elif not conflicting_identifiers and record["work_id"] in work_ids:
                    kind = "related"
                elif (
                    candidate.title
                    and SequenceMatcher(
                        None, normalized(candidate.title), normalized(book.title)
                    ).ratio()
                    >= 0.86
                ):
                    kind = "possible"
                if kind:
                    matches.append(
                        {
                            "kind": kind,
                            "reason": {
                                "exact": "identifier_and_format",
                                "related": "confirmed_work",
                                "possible": "identity_needs_confirmation",
                            }[kind],
                            "record": record,
                        }
                    )
            result = (
                "matches"
                if matches
                else "no_match"
                if candidate.all_identifiers()
                else "unidentified"
            )
            labels = {
                "matches": "記録あり",
                "no_match": "記録なし",
                "unidentified": "確認できません",
            }
            label = (
                "同じ本の可能性あり"
                if matches and all(match["kind"] == "possible" for match in matches)
                else labels[result]
            )
            return {
                "schema_version": 1,
                "result": result,
                "label": label,
                "matches": matches,
                "freshness": self._status(conn),
            }

    def _bind_identity(self, conn, record_id: str, binding: IdentityBinding) -> dict:
        record_id = self._canonical(conn, record_id)
        row = conn.execute("SELECT * FROM acquisitions WHERE id=?", (record_id,)).fetchone()
        if not self._derived_target_matches(
            conn,
            row,
            binding.source_id,
            binding.account,
            binding.order_id,
            binding.derived_identity,
        ):
            raise conflict(
                "Identity does not match the purchase's source, account, order, product and format"
            )
        key = encode(
            [binding.source_id, binding.account, *binding.derived_identity.key(binding.order_id)]
        )
        existing = conn.execute(
            "SELECT record_id FROM external_refs WHERE key=?", (key,)
        ).fetchone()
        if existing and self._canonical(conn, existing[0]) != record_id:
            raise conflict("External identity is already bound to another purchase")
        if not existing:
            conn.execute("INSERT INTO external_refs VALUES (?,?)", (key, record_id))
        conn.execute(
            "INSERT INTO observations VALUES (?,?,?,?)",
            (
                new_id(),
                record_id,
                encode(
                    {
                        "operation": "bind_identity",
                        "record_id": record_id,
                        **binding.model_dump(mode="json"),
                    }
                ),
                binding.derived_identity.observed_at.astimezone(UTC).isoformat(),
            ),
        )
        result = response()
        result.update(
            record_ids=[record_id],
            updated=int(not existing),
            already_exists=int(bool(existing)),
            external_key=key,
        )
        return result

    def bind_identity(
        self, record_id: str, binding: IdentityBinding, *, dry_run: bool = False
    ) -> dict:
        payload = {
            "operation": "bind_identity",
            "record_id": record_id,
            **binding.model_dump(mode="json"),
        }
        with self.db.connect(write=True, dry_run=dry_run) as conn:
            result = self._cached(conn, binding.request_id, payload)
            if result is None:
                result = self._bind_identity(conn, record_id, binding)
                self._remember(conn, binding.request_id, payload, result)
            if dry_run:
                result["dry_run"] = True
            return result

    def update(self, record_id: str, correction: Correction) -> dict:
        payload = {
            "operation": "update",
            "record_id": record_id,
            **correction.model_dump(mode="json"),
        }
        with self.db.connect(write=True) as conn:
            cached = self._cached(conn, correction.request_id, payload)
            if cached is not None:
                return cached
            record_id = self._canonical(conn, record_id)
            row = conn.execute("SELECT * FROM acquisitions WHERE id=?", (record_id,)).fetchone()
            data = {**json.loads(row["data"]), **correction.fields}
            updated = AddRecord.model_validate(data)
            self._source(conn, updated)
            edition_id, _ = self._edition(conn, updated.book)
            protected = sorted(set(json.loads(row["protected"])) | correction.fields.keys())
            conn.execute(
                "UPDATE acquisitions SET data=?,edition_id=?,protected=? WHERE id=?",
                (updated.model_dump_json(), edition_id, encode(protected), record_id),
            )
            conn.execute(
                "INSERT INTO corrections VALUES (?,?,?,?,?)",
                (new_id(), record_id, encode(correction.fields), correction.reason, now()),
            )
            result = response()
            result.update(record_ids=[record_id], updated=1)
            self._remember(conn, correction.request_id, payload, result)
            return result

    def reviews(self) -> dict:
        with self.db.connect() as conn:
            return {
                "schema_version": 1,
                "result": "ok",
                "reviews": [
                    {**dict(row), "payload": json.loads(row["payload"])}
                    for row in conn.execute(
                        "SELECT * FROM reviews WHERE resolution IS NULL ORDER BY created_at,id"
                    )
                ],
            }

    def resolve(self, review_id: str, resolution: Resolution) -> dict:
        payload = {
            "operation": "resolve",
            "review_id": review_id,
            **resolution.model_dump(mode="json"),
        }
        with self.db.connect(write=True) as conn:
            cached = self._cached(conn, resolution.request_id, payload)
            if cached is not None:
                return cached
            review = conn.execute("SELECT * FROM reviews WHERE id=?", (review_id,)).fetchone()
            if review is None:
                raise MottetaError("not_found", "Review not found", 2)
            if review["resolution"]:
                raise conflict("Review is already resolved")
            result = response()
            if resolution.action == "accept_record":
                if review["kind"] != "missing_identity":
                    raise conflict("Only a missing-identity review can accept a new record")
                fields = json.loads(review["payload"])["record"]
                fields["request_id"] = "accepted:" + resolution.request_id
                record = AddRecord.model_validate(fields)
                if (
                    record.external
                    and record.external.key()
                    and record.external.key()[0] == "derived"
                    and self._derived_candidates(conn, record)
                ):
                    raise conflict(
                        "An existing purchase matches this derived identity; use same_acquisition to link it"
                    )
                result = self._ingest(conn, record, history=False)
            elif resolution.action == "same_acquisition" and review["kind"] == "missing_identity":
                if not resolution.target_record_id:
                    raise MottetaError("invalid_resolution", "A target record ID is required", 2)
                record = AddRecord.model_validate(json.loads(review["payload"])["record"])
                if (
                    not record.external
                    or not record.external.key()
                    or record.external.key()[0] != "derived"
                ):
                    raise conflict(
                        "Linking a missing-identity review requires a verified derived identity"
                    )
                binding = IdentityBinding(
                    schema_version=1,
                    request_id=resolution.request_id,
                    reason=resolution.reason,
                    source_id=record.source.id,
                    account=record.account,
                    order_id=record.external.order_id,
                    derived_identity=record.external.derived_identity,
                )
                result = self._bind_identity(conn, resolution.target_record_id, binding)
            elif resolution.action != "keep_separate":
                if not review["record_id"] or not resolution.target_record_id:
                    raise MottetaError(
                        "invalid_resolution", "This resolution requires two existing records", 2
                    )
                current = self._canonical(conn, review["record_id"])
                target = self._canonical(conn, resolution.target_record_id)
                a = conn.execute("SELECT * FROM acquisitions WHERE id=?", (current,)).fetchone()
                b = conn.execute("SELECT * FROM acquisitions WHERE id=?", (target,)).fetchone()
                if current == target:
                    raise conflict("A record cannot be merged with itself")
                if resolution.action == "same_acquisition":
                    if json.loads(a["data"])["quantity"] != json.loads(b["data"])["quantity"]:
                        raise conflict(
                            "Quantities differ; correct them before merging the acquisitions"
                        )
                    conn.execute(
                        "UPDATE acquisitions SET merged_into=? WHERE id=?", (target, current)
                    )
                    conn.execute(
                        "UPDATE external_refs SET record_id=? WHERE record_id=?", (target, current)
                    )
                    target_data = json.loads(b["data"])
                    protected = set(json.loads(b["protected"]))
                    if target_data["possession_state"] != "unknown" and any(
                        e["kind"] == "user_assertion" for e in target_data["evidence"]
                    ):
                        protected.add("possession_state")
                    conn.execute(
                        "UPDATE acquisitions SET protected=? WHERE id=?",
                        (encode(sorted(protected)), target),
                    )
                    result["record_ids"] = [target]
                elif resolution.action == "same_edition":
                    self._merge_editions(conn, a["edition_id"], b["edition_id"])
                    result["record_ids"] = [current, target]
                else:
                    editions = [a["edition_id"], b["edition_id"]]
                    work_ids = [
                        r[0]
                        for eid in editions
                        for r in conn.execute(
                            "SELECT work_id FROM editions WHERE id=? AND work_id IS NOT NULL",
                            (eid,),
                        )
                    ]
                    work_id = work_ids[0] if work_ids else new_id()
                    conn.execute("INSERT OR IGNORE INTO works VALUES (?)", (work_id,))
                    for old_work in work_ids:
                        conn.execute(
                            "UPDATE editions SET work_id=? WHERE work_id=?", (work_id, old_work)
                        )
                    for eid in editions:
                        conn.execute("UPDATE editions SET work_id=? WHERE id=?", (work_id, eid))
                    result["record_ids"] = [current, target]
            conn.execute(
                "UPDATE reviews SET resolution=? WHERE id=?",
                (resolution.model_dump_json(), review_id),
            )
            self._remember(conn, resolution.request_id, payload, result)
            return result

    @staticmethod
    def _merge_editions(conn, old_id: str, target_id: str) -> None:
        if old_id == target_id:
            return
        target = json.loads(
            conn.execute("SELECT data FROM editions WHERE id=?", (target_id,)).fetchone()[0]
        )
        target["edition_id"] = target_id
        for row in conn.execute(
            "SELECT * FROM identifiers WHERE edition_id=?", (old_id,)
        ).fetchall():
            conn.execute(
                "INSERT OR IGNORE INTO identifiers VALUES (?,?,?,?,1)",
                (target_id, row["namespace"], row["scope"], row["value"]),
            )
        for row in conn.execute(
            "SELECT id,data,protected FROM acquisitions WHERE edition_id=?", (old_id,)
        ).fetchall():
            data = json.loads(row["data"])
            data["book"] = target
            protected = sorted(set(json.loads(row["protected"])) | {"book"})
            conn.execute(
                "UPDATE acquisitions SET edition_id=?,data=?,protected=? WHERE id=?",
                (target_id, encode(data), encode(protected), row["id"]),
            )
        conn.execute("DELETE FROM identifiers WHERE edition_id=?", (old_id,))
        conn.execute("UPDATE identifiers SET confirmed=1 WHERE edition_id=?", (target_id,))
        conn.execute("DELETE FROM editions WHERE id=?", (old_id,))

    def export(self, format: str) -> str:
        with self.db.connect() as conn:
            if format == "json":
                return encode(
                    {
                        "schema_version": SCHEMA_VERSION,
                        "exported_at": now(),
                        "tables": {
                            t: [dict(row) for row in conn.execute(f"SELECT * FROM {t}")]
                            for t in TABLES
                        },
                    }
                )
            if format != "csv":
                raise MottetaError("invalid_format", "Expected json or csv", 2)
            output = io.StringIO()
            fields = [
                "id",
                "title",
                "format",
                "source",
                "acquired_on",
                "quantity",
                "order_state",
                "possession_state",
            ]
            writer = csv.DictWriter(output, fieldnames=fields)
            writer.writeheader()
            for record in self._records(conn):
                values = {k: record[k] for k in fields if k in record}
                values.update(
                    title=record["book"]["title"],
                    format=record["book"]["format"],
                    source=record["source"]["name"] if record["source"] else "",
                )
                # Spreadsheet applications can execute formula-like CSV cells.
                writer.writerow(
                    {
                        k: "'" + v
                        if isinstance(v, str) and v.startswith(("=", "+", "-", "@", "\t", "\r"))
                        else v
                        for k, v in values.items()
                    }
                )
            return output.getvalue()

    def backup(self, output: Path) -> dict:
        with self.db.connect() as source:
            self._copy_database(source, output)
        return {"result": "backed_up", "output": str(output.resolve())}

    @staticmethod
    def _copy_database(source, output: Path) -> None:
        output = output.expanduser().resolve()
        fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        try:
            with sqlite3.connect(output) as dest:
                source.backup(dest)
                if dest.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise MottetaError("invalid_database", "Backup integrity check failed")
                validate_database(dest)
        except Exception:
            output.unlink()
            raise

    @staticmethod
    def restore(input_path: Path, output: Path, format: str = "sqlite") -> dict:
        if format == "sqlite":
            source = configure(
                sqlite3.connect(input_path.resolve().as_uri() + "?mode=ro", uri=True)
            )
            try:
                validate_database(source)
                if source.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                    raise MottetaError("invalid_database", "Source integrity check failed")
                Ledger._copy_database(source, output)
            finally:
                source.close()
        elif format == "json":
            data = json.loads(input_path.read_text(encoding="utf-8"))
            if (
                not isinstance(data, dict)
                or set(data) != {"schema_version", "exported_at", "tables"}
                or data["schema_version"] != SCHEMA_VERSION
                or not isinstance(data["tables"], dict)
                or set(data["tables"]) != set(TABLES)
            ):
                raise MottetaError("invalid_export", "Unsupported export structure", 2)
            with sqlite3.connect(":memory:") as source:
                create_schema(source)
                source.execute("PRAGMA foreign_keys=OFF")
                for table in TABLES:
                    columns = [r[1] for r in source.execute(f"PRAGMA table_info({table})")]
                    if not isinstance(data["tables"][table], list):
                        raise MottetaError("invalid_export", "Expected a list of exported rows", 2)
                    for row in data["tables"][table]:
                        if not isinstance(row, dict) or set(row) != set(columns):
                            raise MottetaError("invalid_export", "Export columns do not match", 2)
                        source.execute(
                            f"INSERT INTO {table} ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
                            [row[c] for c in columns],
                        )
                source.commit()
                if source.execute("PRAGMA foreign_key_check").fetchall():
                    raise MottetaError("invalid_export", "Export contains broken references", 2)
                Ledger._copy_database(source, output)
        else:
            raise MottetaError("invalid_format", "Expected sqlite or json", 2)
        return {
            "result": "restored",
            "output": str(output.resolve()),
            "application_id": APPLICATION_ID,
        }
