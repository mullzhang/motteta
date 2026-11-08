---
name: motteta-register
description: Register or correct a book purchase or ownership assertion in the local Motteta ledger from a user's request. Use for physical bookstores and any ebook store, rather than bulk account history.
---

# Register a book with Motteta

Use the installed `motteta` CLI. In a development checkout use `uv run --locked motteta`.
Read [the input contract](../../../docs/contracts.md), the matching example in `examples/`, and `schemas/add-record.schema.json` before preparing JSON.

- Accept a book title or product URL as the starting point. ISBN is optional; do not require it or ask the user to look it up.
- Use Codex's available search or browser tools to verify needed bibliographic information from the supplied URL or a title search. Prefer publisher or reliable catalog/product records, and retain the consulted URLs as references or evidence.
- Track browser work tabs and close all of them before the final report, including product, metadata, search, and retry tabs, whether registration succeeds, stops, or fails. Leave unrelated pre-existing tabs alone. Save references in the record rather than leaving tabs open. Verify closure using the tab list; if a tab cannot be closed, report which one and why.
- Keep the actual seller separate from a metadata reference URL. A new seller is source data, not an application code change.
- Record only facts stated by the user or established by evidence. Do not choose an ISBN, volume, edition, or format from title similarity alone. Leave unverified items null or `unknown` according to the contract and register the known information; missing ISBNs or other optional metadata must not block registration.
- Existing ownership is `ownership_assertion`, not a purchase made on the registration date.
- Generate one request ID per user intent and save the input outside the repository. Reuse the same ID and identical JSON after interruption. A real additional purchase requires a new request ID.
- Execute `motteta add --input <file> --json`. Use `--dry-run` when validation without saving is requested or useful.
- Read both the JSON response and exit code. Code 3 means review or conflict remains; report its review IDs without claiming all identity questions are resolved.
- Correct an existing record with `update`, a new request ID, and a reason. Do not modify an already executed add request.

A user request to register a known book authorizes local registration without a separate confirmation step. Keep uncertain identity visible and use review when needed. Do not make purchases or modify orders on the seller's site.
