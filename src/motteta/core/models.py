"""The single source of truth for JSON input contracts."""

import re
from datetime import date, datetime
from typing import Annotated, Literal, Self
from urllib.parse import urlsplit

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    StringConstraints,
    field_validator,
    model_serializer,
    model_validator,
)

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
Format = Literal["print", "digital", "unknown"]
OrderState = Literal["completed", "ordered", "preordered", "cancelled", "returned", "unknown"]
Possession = Literal["owned", "disposed", "gift", "unknown"]


def normalize_isbn(value: str) -> str:
    value = re.sub(r"[-\s]", "", value).upper()
    if re.fullmatch(r"\d{9}[\dX]", value):
        digits = [int(x) if x != "X" else 10 for x in value]
        if sum((10 - i) * x for i, x in enumerate(digits)) % 11:
            raise ValueError("Invalid ISBN-10 check digit")
        prefix = "978" + value[:9]
        return prefix + str(
            (-sum(int(x) * (1 if i % 2 == 0 else 3) for i, x in enumerate(prefix))) % 10
        )
    if re.fullmatch(r"97[89]\d{10}", value):
        if sum(int(x) * (1 if i % 2 == 0 else 3) for i, x in enumerate(value)) % 10:
            raise ValueError("Invalid ISBN-13 check digit")
        return value
    raise ValueError("Expected a valid ISBN-10 or ISBN-13")


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Identifier(Model):
    namespace: Text
    scope: Text
    value: Text

    @model_validator(mode="after")
    def isbn_contract(self) -> Self:
        if self.namespace == "isbn":
            if self.scope != "global":
                raise ValueError("ISBN scope must be global")
            self.value = normalize_isbn(self.value)
        return self


class Book(Model):
    title: Text
    authors: list[Text] = Field(default_factory=list)
    isbn: str | None = None
    identifiers: list[Identifier] = Field(default_factory=list)
    format: Format
    volume: Text | None = None
    edition: Text | None = None
    language: Text | None = None
    edition_id: Text | None = None
    file_formats: list[Literal["pdf", "epub", "mobi", "other"]] = Field(default_factory=list)
    reference_url: str | None = None

    @field_validator("isbn")
    @classmethod
    def valid_isbn(cls, value: str | None) -> str | None:
        return normalize_isbn(value) if value is not None else None

    @field_validator("reference_url")
    @classmethod
    def valid_url(cls, value: str | None) -> str | None:
        if value is not None and urlsplit(value).scheme not in {"http", "https"}:
            raise ValueError("Reference URL must use HTTP or HTTPS")
        return value

    @model_validator(mode="after")
    def file_contract(self) -> Self:
        if self.file_formats and self.format != "digital":
            raise ValueError("File formats require a digital edition")
        if self.isbn and any(
            i.namespace == "isbn" and i.value != self.isbn for i in self.identifiers
        ):
            raise ValueError("Conflicting ISBN identifiers")
        return self

    def all_identifiers(self) -> list[Identifier]:
        ids = list(self.identifiers)
        if self.isbn:
            ids.append(Identifier(namespace="isbn", scope="global", value=self.isbn))
        return list({(i.namespace, i.scope, i.value): i for i in ids}.values())


class Source(Model):
    id: Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]{0,79}$")]
    name: Text
    kind: Literal["online", "physical"]


class Evidence(Model):
    kind: Literal["user_assertion", "purchase_history", "owned_list", "receipt"]
    observed_at: AwareDatetime
    reference: Text | None = None
    note: Text | None = None


class DerivedIdentity(Model):
    scheme: Literal["order_product_format_v1"]
    product: Identifier
    format: Literal["print", "digital"]
    order_complete: Annotated[bool, Field(strict=True)]
    matching_line_count: Annotated[int, Field(strict=True, ge=0)] | None
    observed_at: AwareDatetime
    reference: Text
    note: Text

    def key(self, order_id: str) -> list[str] | None:
        if not self.order_complete or self.matching_line_count != 1:
            return None
        return [
            "derived",
            self.scheme,
            order_id,
            self.product.namespace,
            self.product.scope,
            self.product.value,
            self.format,
        ]


class ExternalRef(Model):
    order_id: Text | None = None
    line_id: Text | None = None
    holding_id: Text | None = None
    derived_identity: DerivedIdentity | None = None

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        data = handler(self)
        # Adding an optional identity must not change existing request hashes.
        if self.derived_identity is None:
            data.pop("derived_identity", None)
        return data

    def key(self) -> list[str] | None:
        if self.holding_id:
            return ["holding", self.holding_id]
        if self.order_id and self.line_id:
            return ["order", self.order_id, self.line_id]
        if self.order_id and self.derived_identity:
            return self.derived_identity.key(self.order_id)
        return None


class Record(Model):
    book: Book
    acquisition_kind: Literal["purchase", "ownership_assertion"]
    quantity: Annotated[int, Field(strict=True, gt=0)]
    acquired_on: str | None = None
    order_state: OrderState | None
    possession_state: Possession
    external: ExternalRef | None = None
    evidence: Annotated[list[Evidence], Field(min_length=1)]

    @field_validator("acquired_on")
    @classmethod
    def valid_date(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not re.fullmatch(r"\d{4}(-\d{2}){0,2}", value):
            raise ValueError("Date must be YYYY, YYYY-MM, or YYYY-MM-DD")
        date.fromisoformat(value + {4: "-01-01", 7: "-01", 10: ""}[len(value)])
        return value

    @model_validator(mode="after")
    def state_contract(self) -> Self:
        if self.acquisition_kind == "ownership_assertion" and self.order_state is not None:
            raise ValueError("Ownership assertions have no order state")
        if self.acquisition_kind == "purchase" and self.order_state is None:
            raise ValueError("Purchases require an explicit order state, including unknown")
        if self.order_state in {"cancelled", "returned"} and self.possession_state == "owned":
            raise ValueError("Cancelled or returned purchases cannot assert current ownership")
        if self.external and self.external.derived_identity:
            identity = self.external.derived_identity
            if self.acquisition_kind != "purchase" or not self.external.order_id:
                raise ValueError("Derived identity requires a purchase and an order ID")
            if (
                identity.format != self.book.format
                or identity.product not in self.book.all_identifiers()
            ):
                raise ValueError("Derived identity must match the book's product and format")
            history = [e for e in self.evidence if e.kind == "purchase_history"]
            if (
                not history
                or identity.observed_at != max(e.observed_at for e in history)
                or not any(
                    e.observed_at == identity.observed_at and e.reference == identity.reference
                    for e in history
                )
            ):
                raise ValueError(
                    "Derived identity requires fresh matching purchase-history evidence"
                )
        return self

    def observed_at(self) -> datetime:
        return max(e.observed_at for e in self.evidence)


class AddRecord(Record):
    schema_version: Literal[1]
    request_id: Text
    source: Source | None = None
    account: Text | None = None

    @model_validator(mode="after")
    def source_contract(self) -> Self:
        if self.external and (not self.source or not self.account):
            raise ValueError("External records require source and account")
        return self


class HistoryItem(Record):
    item_id: Text


class Coverage(Model):
    requested_start: date
    requested_end: date
    checked_start: date | None = None
    checked_end: date | None = None
    status: Literal["complete", "partial", "failed"]
    visited: list[Text] = Field(default_factory=list)
    unverified: list[Text] = Field(default_factory=list)
    resume: dict[str, JsonValue] | None = None

    @model_validator(mode="after")
    def range_contract(self) -> Self:
        if self.requested_start > self.requested_end:
            raise ValueError("Requested date range is reversed")
        if (self.checked_start is None) != (self.checked_end is None):
            raise ValueError("Checked range requires both endpoints")
        if self.checked_start is not None and not (
            self.requested_start <= self.checked_start <= self.checked_end <= self.requested_end
        ):
            raise ValueError("Checked range must be within requested range")
        if self.status == "complete" and (
            self.checked_start != self.requested_start
            or self.checked_end != self.requested_end
            or self.unverified
            or self.resume is not None
        ):
            raise ValueError("Complete coverage requires the entire range without unresolved gaps")
        return self


class HistoryBatch(Model):
    schema_version: Literal[1]
    import_id: Text
    source: Source
    account: Text
    observed_at: AwareDatetime
    records: list[HistoryItem]
    coverage: Coverage

    @model_validator(mode="after")
    def unique_items(self) -> Self:
        ids = [r.item_id for r in self.records]
        if len(set(ids)) != len(ids):
            raise ValueError("History item IDs must be unique within an import")
        if any(r.observed_at() > self.observed_at for r in self.records):
            raise ValueError("Evidence cannot be newer than the import observation")
        for record in self.records:
            external = record.external
            if (
                not external
                or not external.derived_identity
                or not external.derived_identity.key(external.order_id)
            ):
                continue
            identity = external.derived_identity
            matches = [
                other
                for other in self.records
                if other.external
                and other.external.order_id == external.order_id
                and other.book.format == identity.format
                and identity.product in other.book.all_identifiers()
            ]
            if len(matches) > 1:
                raise ValueError("Derived identity is ambiguous within this order")
        return self


class Candidate(Model):
    schema_version: Literal[1]
    title: Text | None = None
    authors: list[Text] = Field(default_factory=list)
    isbn: str | None = None
    identifiers: list[Identifier] = Field(default_factory=list)
    format: Format
    volume: Text | None = None
    edition: Text | None = None
    language: Text | None = None
    url: str | None = None

    _isbn = field_validator("isbn")(Book.valid_isbn.__func__)

    def all_identifiers(self) -> list[Identifier]:
        ids = list(self.identifiers)
        if self.isbn:
            ids.append(Identifier(namespace="isbn", scope="global", value=self.isbn))
        return ids


class Correction(Model):
    schema_version: Literal[1]
    request_id: Text
    reason: Text
    fields: dict[str, JsonValue]

    @field_validator("fields")
    @classmethod
    def allowed_fields(cls, value: dict) -> dict:
        allowed = {
            "book",
            "source",
            "account",
            "acquisition_kind",
            "quantity",
            "acquired_on",
            "order_state",
            "possession_state",
        }
        if not value or value.keys() - allowed:
            raise ValueError("Correction contains no fields or unsupported fields")
        return value


class IdentityBinding(Model):
    schema_version: Literal[1]
    request_id: Text
    reason: Text
    source_id: Text
    account: Text
    order_id: Text
    derived_identity: DerivedIdentity

    @model_validator(mode="after")
    def verified_identity(self) -> Self:
        if self.derived_identity.key(self.order_id) is None:
            raise ValueError("Binding requires a complete order with exactly one matching line")
        return self


class Resolution(Model):
    schema_version: Literal[1]
    request_id: Text
    action: Literal[
        "same_work", "same_edition", "same_acquisition", "keep_separate", "accept_record"
    ]
    target_record_id: Text | None = None
    reason: Text


class NativeRequest(Model):
    schema_version: Literal[1]
    request_id: Text
    operation: Literal["check", "status"]
    candidate: Candidate | None = None

    @model_validator(mode="after")
    def operation_contract(self) -> Self:
        if (self.operation == "check") != (self.candidate is not None):
            raise ValueError("Only check requires a candidate")
        return self


class BrowserConfig(Model):
    browser: Literal["chrome"]
    extension_id: Annotated[str, StringConstraints(pattern=r"^[a-p]{32}$")]
